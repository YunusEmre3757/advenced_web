package com.example.backend.safety;

import com.example.backend.auth.User;
import com.example.backend.auth.UserRepository;
import com.example.backend.graph.GraphClient;
import com.example.backend.notification.NotificationDelivery;
import com.example.backend.notification.NotificationDeliveryRepository;
import com.example.backend.notification.PushoverClient;
import com.example.backend.notification.PushoverClient.PushoverResult;
import com.example.backend.notification.ResendClient;
import com.example.backend.notification.ResendClient.ResendResult;
import com.example.backend.profile.FamilyMember;
import com.example.backend.profile.FamilyMemberRepository;
import com.example.backend.safety.SafetyDtos.*;
import com.fasterxml.jackson.databind.JsonNode;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.server.ResponseStatusException;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.ArrayList;
import java.util.HexFormat;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.UUID;

@Service
public class SafetyService {

    private static final String CHANNEL_PUSHOVER = "PUSHOVER";
    private static final String CHANNEL_EMAIL = "EMAIL";
    private static final String EVENT_PREFIX = "safety:";

    private final UserRepository users;
    private final SafetyCheckinRepository checkins;
    private final FamilyMemberRepository familyMembers;
    private final NotificationDeliveryRepository deliveries;
    private final PushoverClient pushover;
    private final ResendClient resend;
    private final GraphClient graphClient;

    public SafetyService(
            UserRepository users,
            SafetyCheckinRepository checkins,
            FamilyMemberRepository familyMembers,
            NotificationDeliveryRepository deliveries,
            PushoverClient pushover,
            ResendClient resend,
            GraphClient graphClient
    ) {
        this.users = users;
        this.checkins = checkins;
        this.familyMembers = familyMembers;
        this.deliveries = deliveries;
        this.pushover = pushover;
        this.resend = resend;
        this.graphClient = graphClient;
    }

    @Transactional
    public CheckinResponse checkIn(UUID userId, CheckinRequest req) {
        User user = users.findById(userId).orElseThrow(() ->
                new ResponseStatusException(HttpStatus.UNAUTHORIZED, "user not found"));

        SafetyCheckin checkin = checkins.save(SafetyCheckin.builder()
                .user(user)
                .status(req.status().name())
                .eventId(req.eventId())
                .note(req.note())
                .latitude(req.latitude())
                .longitude(req.longitude())
                .build());

        List<FamilyFanoutResult> fanout = notifyFamily(user, checkin, req);
        return new CheckinResponse(CheckinView.of(checkin), fanout);
    }

    @Transactional(readOnly = true)
    public CheckinView latest(UUID userId) {
        return checkins.findFirstByUserIdOrderByCreatedAtDesc(userId)
                .map(CheckinView::of)
                .orElse(null);
    }

    @Transactional(readOnly = true)
    public List<CheckinView> history(UUID userId) {
        return checkins.findByUserIdOrderByCreatedAtDesc(userId).stream()
                .map(CheckinView::of)
                .toList();
    }

    private List<FamilyFanoutResult> notifyFamily(User user, SafetyCheckin checkin, CheckinRequest req) {
        List<FamilyMember> family = familyMembers.findByUserIdOrderByCreatedAtAsc(user.getId());
        if (family.isEmpty()) return List.of();

        String name = user.getDisplayName() != null ? user.getDisplayName() : user.getEmail();
        String fallbackTitle = switch (req.status()) {
            case SAFE -> name + " guvende";
            case NEEDS_HELP -> "YARDIM GEREKIYOR: " + name;
            case UNKNOWN -> "Durum bilinmiyor: " + name;
        };
        StringBuilder body = new StringBuilder();
        body.append(name);
        switch (req.status()) {
            case SAFE -> body.append(" guvende oldugunu bildirdi.");
            case NEEDS_HELP -> body.append(" yardim istedi. Lutfen ulasmaya calisin.");
            case UNKNOWN -> body.append(" durumunu \"bilinmiyor\" olarak isaretledi.");
        }
        if (req.note() != null && !req.note().isBlank()) {
            body.append(" Not: ").append(req.note());
        }
        if (req.latitude() != null && req.longitude() != null) {
            body.append(String.format(java.util.Locale.US, " Konum: %.4f, %.4f.",
                    req.latitude(), req.longitude()));
        }
        String fallbackMessage = body.toString();
        SafeCheckPlan graphPlan = planWithGraph(user, checkin, req, family);
        String title = graphPlan != null && !isBlank(graphPlan.title()) ? graphPlan.title() : fallbackTitle;
        String message = graphPlan != null && !isBlank(graphPlan.body()) ? graphPlan.body() : fallbackMessage;
        String html = "<p>" + message + "</p>";
        String eventId = EVENT_PREFIX + checkin.getId();

        List<FamilyFanoutResult> results = new ArrayList<>();
        for (FamilyMember member : family) {
            if (!member.isNotify()) continue;

            if (!isBlank(member.getPushoverKey())) {
                PushoverResult r = pushover.send(member.getPushoverKey(), title, message);
                saveDelivery(user, eventId, CHANNEL_PUSHOVER, member.getName(),
                        hash(member.getPushoverKey()), r.status(), r.message());
                results.add(new FamilyFanoutResult(member.getName(), CHANNEL_PUSHOVER,
                        r.status(), r.message()));
            }

            if (!isBlank(member.getEmail())) {
                ResendResult r = resend.send(member.getEmail(), title, message, html);
                saveDelivery(user, eventId, CHANNEL_EMAIL, member.getName(),
                        hash(member.getEmail()), r.status(), r.message());
                results.add(new FamilyFanoutResult(member.getName(), CHANNEL_EMAIL,
                        r.status(), r.message()));
            }
        }
        return results;
    }

    private SafeCheckPlan planWithGraph(
            User user,
            SafetyCheckin checkin,
            CheckinRequest req,
            List<FamilyMember> family
    ) {
        try {
            Map<String, Object> userPayload = new LinkedHashMap<>();
            userPayload.put("id", user.getId().toString());
            userPayload.put("email", user.getEmail());
            userPayload.put("displayName", user.getDisplayName());

            Map<String, Object> checkinPayload = new LinkedHashMap<>();
            checkinPayload.put("id", checkin.getId().toString());
            checkinPayload.put("status", req.status().name());
            checkinPayload.put("eventId", req.eventId());
            checkinPayload.put("note", req.note());
            checkinPayload.put("latitude", req.latitude());
            checkinPayload.put("longitude", req.longitude());

            List<Map<String, Object>> familyPayload = family.stream().map(member -> {
                Map<String, Object> row = new LinkedHashMap<>();
                row.put("name", member.getName());
                row.put("relationship", member.getRelationship());
                row.put("email", member.getEmail());
                row.put("pushoverKey", !isBlank(member.getPushoverKey()) ? "available" : null);
                row.put("notify", member.isNotify());
                return row;
            }).toList();

            JsonNode response = graphClient.postJsonNode("/graph/safe-check", Map.of(
                    "user", userPayload,
                    "checkin", checkinPayload,
                    "family", familyPayload
            ));
            return new SafeCheckPlan(
                    response.path("title").asText(""),
                    response.path("body").asText(""),
                    response.path("summary").asText("")
            );
        } catch (Exception ignored) {
            return null;
        }
    }

    private void saveDelivery(
            User user, String eventId, String channel,
            String recipientLabel, String keyHash, String status, String message
    ) {
        if (deliveries.existsByUserIdAndEventIdAndChannelAndRecipientKeyHash(
                user.getId(), eventId, channel, keyHash)) {
            return;
        }
        deliveries.save(NotificationDelivery.builder()
                .user(user)
                .eventId(eventId)
                .channel(channel)
                .recipientType("FAMILY")
                .recipientLabel(recipientLabel)
                .recipientKeyHash(keyHash)
                .status(status)
                .providerMessage(message)
                .build());
    }

    private boolean isBlank(String value) {
        return value == null || value.trim().isEmpty();
    }

    private String hash(String value) {
        try {
            MessageDigest digest = MessageDigest.getInstance("SHA-256");
            return HexFormat.of().formatHex(digest.digest(value.getBytes(StandardCharsets.UTF_8)));
        } catch (NoSuchAlgorithmException ex) {
            throw new IllegalStateException("SHA-256 is not available", ex);
        }
    }

    private record SafeCheckPlan(String title, String body, String summary) {
    }
}
