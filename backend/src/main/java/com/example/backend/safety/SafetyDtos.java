package com.example.backend.safety;

import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;

import java.time.OffsetDateTime;
import java.util.List;
import java.util.UUID;

public final class SafetyDtos {

    private SafetyDtos() {
    }

    public enum Status {
        SAFE,
        NEEDS_HELP,
        UNKNOWN
    }

    public record CheckinRequest(
            @NotNull Status status,
            @Size(max = 120) String eventId,
            @Size(max = 500) String note,
            Double latitude,
            Double longitude
    ) {
    }

    public record CheckinView(
            UUID id,
            Status status,
            String eventId,
            String note,
            Double latitude,
            Double longitude,
            OffsetDateTime createdAt
    ) {
        public static CheckinView of(SafetyCheckin checkin) {
            Status parsed;
            try {
                parsed = Status.valueOf(checkin.getStatus());
            } catch (IllegalArgumentException ex) {
                parsed = Status.UNKNOWN;
            }
            return new CheckinView(
                    checkin.getId(),
                    parsed,
                    checkin.getEventId(),
                    checkin.getNote(),
                    checkin.getLatitude(),
                    checkin.getLongitude(),
                    checkin.getCreatedAt()
            );
        }
    }

    public record FamilyFanoutResult(
            String recipientLabel,
            String channel,
            String status,
            String message
    ) {
    }

    public record CheckinResponse(
            CheckinView checkin,
            List<FamilyFanoutResult> familyNotifications
    ) {
    }
}
