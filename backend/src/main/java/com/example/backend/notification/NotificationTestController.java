package com.example.backend.notification;

import com.example.backend.auth.User;
import com.example.backend.auth.UserRepository;
import com.example.backend.notification.PushoverClient.PushoverResult;
import com.example.backend.notification.ResendClient.ResendResult;
import org.springframework.http.HttpStatus;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.time.Instant;
import java.util.ArrayList;
import java.util.HexFormat;
import java.util.List;
import java.util.UUID;

@RestController
@RequestMapping("/api/notifications")
public class NotificationTestController {

    private static final String CHANNEL_PUSHOVER = "PUSHOVER";
    private static final String CHANNEL_EMAIL = "EMAIL";
    private static final String TEST_EVENT_PREFIX = "test:";

    private final UserRepository users;
    private final NotificationPreferenceRepository preferences;
    private final NotificationDeliveryRepository deliveries;
    private final PushoverClient pushover;
    private final ResendClient resend;

    public NotificationTestController(
            UserRepository users,
            NotificationPreferenceRepository preferences,
            NotificationDeliveryRepository deliveries,
            PushoverClient pushover,
            ResendClient resend
    ) {
        this.users = users;
        this.preferences = preferences;
        this.deliveries = deliveries;
        this.pushover = pushover;
        this.resend = resend;
    }

    @PostMapping("/test")
    @Transactional
    public TestResponse sendTest(@AuthenticationPrincipal UUID userId) {
        if (userId == null) {
            throw new ResponseStatusException(HttpStatus.UNAUTHORIZED, "not authenticated");
        }
        User user = users.findById(userId).orElseThrow(() ->
                new ResponseStatusException(HttpStatus.UNAUTHORIZED, "user not found"));

        NotificationPreference pref = preferences.findByUserId(userId).orElseThrow(() ->
                new ResponseStatusException(HttpStatus.BAD_REQUEST,
                        "Notification preferences not set. Enable a channel on the profile page first."));

        boolean anyChannelReady =
                (pref.isPushoverEnabled() && notBlank(pref.getPushoverUserKey()))
                        || (pref.isEmailEnabled() && notBlank(pref.getEmailAddress()));
        if (!anyChannelReady) {
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST,
                    "No channel is enabled or addresses are missing.");
        }

        String eventId = TEST_EVENT_PREFIX + UUID.randomUUID();
        String title = "Test bildirimi";
        String message = "Seismic Command — bildirim kanalı çalışıyor. Bu mesaj sadece test amaçlıdır.";
        String html = "<p>" + message + "</p>";
        Instant now = Instant.now();

        List<ChannelResult> results = new ArrayList<>();

        if (pref.isPushoverEnabled() && notBlank(pref.getPushoverUserKey())) {
            PushoverResult r = pushover.send(pref.getPushoverUserKey(), title, message);
            deliveries.save(delivery(user, eventId, CHANNEL_PUSHOVER,
                    hash(pref.getPushoverUserKey()), r.status(), r.message()));
            results.add(new ChannelResult(CHANNEL_PUSHOVER, r.delivered(), r.status(), r.message()));
        }

        if (pref.isEmailEnabled() && notBlank(pref.getEmailAddress())) {
            ResendResult r = resend.send(pref.getEmailAddress(), title, message, html);
            deliveries.save(delivery(user, eventId, CHANNEL_EMAIL,
                    hash(pref.getEmailAddress()), r.status(), r.message()));
            results.add(new ChannelResult(CHANNEL_EMAIL, r.delivered(), r.status(), r.message()));
        }

        boolean overallDelivered = results.stream().anyMatch(ChannelResult::delivered);
        return new TestResponse(overallDelivered, eventId, now, results);
    }

    private NotificationDelivery delivery(
            User user, String eventId, String channel, String keyHash, String status, String msg
    ) {
        return NotificationDelivery.builder()
                .user(user)
                .eventId(eventId)
                .channel(channel)
                .recipientType("USER")
                .recipientLabel("Test")
                .recipientKeyHash(keyHash)
                .status(status)
                .providerMessage(msg)
                .build();
    }

    private boolean notBlank(String value) {
        return value != null && !value.trim().isEmpty();
    }

    private String hash(String value) {
        try {
            MessageDigest digest = MessageDigest.getInstance("SHA-256");
            return HexFormat.of().formatHex(digest.digest(value.getBytes(StandardCharsets.UTF_8)));
        } catch (NoSuchAlgorithmException ex) {
            throw new IllegalStateException("SHA-256 is not available", ex);
        }
    }

    public record ChannelResult(String channel, boolean delivered, String status, String message) {
    }

    public record TestResponse(
            boolean delivered,
            String eventId,
            Instant sentAt,
            List<ChannelResult> results
    ) {
    }
}
