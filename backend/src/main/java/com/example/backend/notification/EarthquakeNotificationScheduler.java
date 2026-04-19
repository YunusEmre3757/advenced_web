package com.example.backend.notification;

import com.example.backend.graph.GraphClient;
import com.example.backend.auth.User;
import com.example.backend.earthquake.EarthquakeDto;
import com.example.backend.earthquake.EarthquakeService;
import com.example.backend.notification.PushoverClient.PushoverResult;
import com.example.backend.notification.ResendClient.ResendResult;
import com.example.backend.profile.FamilyMember;
import com.example.backend.profile.FamilyMemberRepository;
import com.example.backend.profile.UserLocation;
import com.example.backend.profile.UserLocationRepository;
import com.fasterxml.jackson.databind.JsonNode;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.time.ZoneId;
import java.time.format.DateTimeFormatter;
import java.util.ArrayList;
import java.util.HexFormat;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.UUID;
import java.util.stream.Collectors;

@Service
public class EarthquakeNotificationScheduler {

    private static final String CHANNEL_PUSHOVER = "PUSHOVER";
    private static final String CHANNEL_EMAIL = "EMAIL";
    private static final ZoneId TURKEY_ZONE = ZoneId.of("Europe/Istanbul");
    private static final DateTimeFormatter TIME_FORMAT = DateTimeFormatter.ofPattern("dd.MM HH:mm").withZone(TURKEY_ZONE);

    private final EarthquakeService earthquakes;
    private final UserLocationRepository locations;
    private final FamilyMemberRepository familyMembers;
    private final NotificationPreferenceRepository preferences;
    private final NotificationDeliveryRepository deliveries;
    private final PushoverClient pushover;
    private final ResendClient resend;
    private final GraphClient graphClient;

    @Value("${notifications.earthquake.enabled:true}")
    private boolean enabled;

    @Value("${notifications.earthquake.lookback-hours:2}")
    private int lookbackHours;

    @Value("${notifications.earthquake.fetch-limit:100}")
    private int fetchLimit;

    @Value("${notifications.earthquake.graph-routing.enabled:true}")
    private boolean graphRoutingEnabled;

    public EarthquakeNotificationScheduler(
            EarthquakeService earthquakes,
            UserLocationRepository locations,
            FamilyMemberRepository familyMembers,
            NotificationPreferenceRepository preferences,
            NotificationDeliveryRepository deliveries,
            PushoverClient pushover,
            ResendClient resend,
            GraphClient graphClient
    ) {
        this.earthquakes = earthquakes;
        this.locations = locations;
        this.familyMembers = familyMembers;
        this.preferences = preferences;
        this.deliveries = deliveries;
        this.pushover = pushover;
        this.resend = resend;
        this.graphClient = graphClient;
    }

    @Scheduled(
            fixedDelayString = "${notifications.earthquake.scan-interval-ms:30000}",
            initialDelayString = "${notifications.earthquake.initial-delay-ms:15000}"
    )
    @Transactional
    public void scanAndNotify() {
        if (!enabled) {
            return;
        }

        List<NotificationPreference> activePreferences =
                preferences.findByPushoverEnabledTrueOrEmailEnabledTrue();
        if (activePreferences.isEmpty()) {
            return;
        }

        List<EarthquakeDto> recent = earthquakes.fetchRecentTurkeyEarthquakes(
                Math.max(1, lookbackHours),
                1.0,
                Math.max(1, fetchLimit)
        );

        for (NotificationPreference preference : activePreferences) {
            scanUser(preference, recent);
        }
    }

    private void scanUser(NotificationPreference preference, List<EarthquakeDto> earthquakes) {
        User user = preference.getUser();
        UUID userId = user.getId();
        List<UserLocation> userLocations = locations.findByUserIdOrderByPrimaryLocationDescCreatedAtAsc(userId);
        if (userLocations.isEmpty()) {
            return;
        }

        List<Recipient> recipients = recipientsFor(preference);
        if (recipients.isEmpty()) {
            return;
        }

        for (EarthquakeDto earthquake : earthquakes) {
            if (earthquake.magnitude() < preference.getMinMagnitude()) {
                continue;
            }
            UserLocation matchedLocation = firstMatchedLocation(userLocations, earthquake);
            if (matchedLocation == null) {
                continue;
            }
            notifyRecipients(user, preference, matchedLocation, earthquake, recipients);
        }
    }

    private List<Recipient> recipientsFor(NotificationPreference preference) {
        List<Recipient> recipients = new ArrayList<>();
        if (preference.isPushoverEnabled() && !isBlank(preference.getPushoverUserKey())) {
            recipients.add(new Recipient(
                    CHANNEL_PUSHOVER, "USER", "Hesabim", preference.getPushoverUserKey()));
        }
        if (preference.isEmailEnabled() && !isBlank(preference.getEmailAddress())) {
            recipients.add(new Recipient(
                    CHANNEL_EMAIL, "USER", "Hesabim", preference.getEmailAddress()));
        }
        if (preference.isNotifyFamilyMembers()) {
            List<FamilyMember> family =
                    familyMembers.findByUserIdOrderByCreatedAtAsc(preference.getUser().getId())
                            .stream()
                            .filter(FamilyMember::isNotify)
                            .toList();
            if (preference.isPushoverEnabled()) {
                family.stream()
                        .filter(member -> !isBlank(member.getPushoverKey()))
                        .map(member -> new Recipient(
                                CHANNEL_PUSHOVER, "FAMILY", member.getName(), member.getPushoverKey()))
                        .forEach(recipients::add);
            }
            if (preference.isEmailEnabled()) {
                family.stream()
                        .filter(member -> !isBlank(member.getEmail()))
                        .map(member -> new Recipient(
                                CHANNEL_EMAIL, "FAMILY", member.getName(), member.getEmail()))
                        .forEach(recipients::add);
            }
        }
        return recipients;
    }

    private UserLocation firstMatchedLocation(List<UserLocation> userLocations, EarthquakeDto earthquake) {
        for (UserLocation location : userLocations) {
            double distance = haversineKm(
                    location.getLatitude(),
                    location.getLongitude(),
                    earthquake.latitude(),
                    earthquake.longitude()
            );
            if (distance <= location.getRadiusKm()) {
                return location;
            }
        }
        return null;
    }

    private void notifyRecipients(
            User user,
            NotificationPreference preference,
            UserLocation location,
            EarthquakeDto earthquake,
            List<Recipient> recipients
    ) {
        GraphRoutePlan graphPlan = routeWithGraph(user, location, earthquake, recipients);
        if (graphPlan != null && graphPlan.suppress()) {
            return;
        }

        String fallbackTitle = "Deprem uyarisi: M" + oneDecimal(earthquake.magnitude());
        String fallbackMessage = earthquake.location() + " bolgesinde M" + oneDecimal(earthquake.magnitude()) +
                " deprem kaydedildi. Izlenen konum: " + location.getLabel() +
                " (" + oneDecimal(location.getRadiusKm()) + " km). Saat: " + TIME_FORMAT.format(earthquake.time()) + ".";
        String title = graphPlan != null && !isBlank(graphPlan.title()) ? graphPlan.title() : fallbackTitle;
        String message = graphPlan != null && !isBlank(graphPlan.body()) ? graphPlan.body() : fallbackMessage;

        String htmlBody = "<p>" + message + "</p>";
        for (Recipient recipient : recipients) {
            if (graphPlan != null && !graphPlan.allows(recipient.channel())) {
                continue;
            }
            String keyHash = hash(recipient.address());
            if (deliveries.existsByUserIdAndEventIdAndChannelAndRecipientKeyHash(
                    user.getId(),
                    earthquake.id(),
                    recipient.channel(),
                    keyHash
            )) {
                continue;
            }

            String status;
            String providerMessage;
            if (CHANNEL_EMAIL.equals(recipient.channel())) {
                ResendResult result = resend.send(recipient.address(), title, message, htmlBody);
                status = result.status();
                providerMessage = result.message();
            } else {
                PushoverResult result = pushover.send(recipient.address(), title, message);
                status = result.status();
                providerMessage = result.message();
            }

            deliveries.save(NotificationDelivery.builder()
                    .user(user)
                    .eventId(earthquake.id())
                    .channel(recipient.channel())
                    .recipientType(recipient.type())
                    .recipientLabel(recipient.label())
                    .recipientKeyHash(keyHash)
                    .status(status)
                    .providerMessage(graphPlan != null && !isBlank(graphPlan.reason())
                            ? providerMessage + " | graph=" + graphPlan.reason()
                            : providerMessage)
                    .build());
        }
    }

    private GraphRoutePlan routeWithGraph(
            User user,
            UserLocation location,
            EarthquakeDto earthquake,
            List<Recipient> recipients
    ) {
        if (!graphRoutingEnabled) {
            return null;
        }
        try {
            Map<String, Object> event = new LinkedHashMap<>();
            event.put("eventId", earthquake.id());
            event.put("magnitude", earthquake.magnitude());
            event.put("depthKm", earthquake.depthKm());
            event.put("latitude", earthquake.latitude());
            event.put("longitude", earthquake.longitude());
            event.put("location", earthquake.location());
            event.put("time", earthquake.time().toString());

            boolean hasPushover = recipients.stream().anyMatch(r -> CHANNEL_PUSHOVER.equals(r.channel()));
            boolean hasEmail = recipients.stream().anyMatch(r -> CHANNEL_EMAIL.equals(r.channel()));
            Map<String, Object> profile = new LinkedHashMap<>();
            profile.put("userId", user.getId().toString());
            profile.put("displayName", user.getDisplayName() != null ? user.getDisplayName() : user.getEmail());
            profile.put("latitude", location.getLatitude());
            profile.put("longitude", location.getLongitude());
            if (hasPushover) profile.put("pushoverKey", "available");
            if (hasEmail) profile.put("email", "available");

            JsonNode response = graphClient.postJsonNode("/graph/notify-route", Map.of(
                    "event", event,
                    "users", List.of(profile)
            ));
            JsonNode firstPlan = response.path("plans").path(0);
            if (firstPlan.isMissingNode()) {
                return null;
            }
            Set<String> channels = new java.util.HashSet<>();
            JsonNode channelNode = firstPlan.path("channels");
            if (channelNode.isArray()) {
                channelNode.forEach(c -> channels.add(c.asText("").toLowerCase(java.util.Locale.ROOT)));
            }
            return new GraphRoutePlan(
                    firstPlan.path("suppress").asBoolean(false),
                    firstPlan.path("title").asText(""),
                    firstPlan.path("body").asText(""),
                    firstPlan.path("reason").asText(""),
                    channels
            );
        } catch (Exception ignored) {
            return null;
        }
    }

    private double haversineKm(double lat1, double lon1, double lat2, double lon2) {
        double earthRadiusKm = 6371.0;
        double dLat = Math.toRadians(lat2 - lat1);
        double dLon = Math.toRadians(lon2 - lon1);
        double a = Math.sin(dLat / 2) * Math.sin(dLat / 2)
                + Math.cos(Math.toRadians(lat1)) * Math.cos(Math.toRadians(lat2))
                * Math.sin(dLon / 2) * Math.sin(dLon / 2);
        return earthRadiusKm * (2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a)));
    }

    private String hash(String value) {
        try {
            MessageDigest digest = MessageDigest.getInstance("SHA-256");
            return HexFormat.of().formatHex(digest.digest(value.getBytes(StandardCharsets.UTF_8)));
        } catch (NoSuchAlgorithmException ex) {
            throw new IllegalStateException("SHA-256 is not available", ex);
        }
    }

    private String oneDecimal(double value) {
        return String.format(java.util.Locale.US, "%.1f", value);
    }

    private boolean isBlank(String value) {
        return value == null || value.trim().isEmpty();
    }

    private record Recipient(String channel, String type, String label, String address) {
    }

    private record GraphRoutePlan(
            boolean suppress,
            String title,
            String body,
            String reason,
            Set<String> channels
    ) {
        boolean allows(String channel) {
            if (channels == null || channels.isEmpty()) return true;
            return channels.contains(channel.toLowerCase(java.util.Locale.ROOT));
        }
    }
}
