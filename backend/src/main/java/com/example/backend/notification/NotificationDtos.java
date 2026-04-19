package com.example.backend.notification;

import jakarta.validation.constraints.DecimalMax;
import jakarta.validation.constraints.DecimalMin;
import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.Size;

import java.util.UUID;

public final class NotificationDtos {

    private NotificationDtos() {
    }

    public record NotificationPreferenceRequest(
            boolean pushoverEnabled,
            @Size(max = 80) String pushoverUserKey,
            @DecimalMin("1.0") @DecimalMax("9.0") double minMagnitude,
            boolean notifyFamilyMembers,
            boolean emailEnabled,
            @Email @Size(max = 255) String emailAddress
    ) {
    }

    public record NotificationPreferenceView(
            UUID id,
            boolean pushoverEnabled,
            String pushoverUserKey,
            double minMagnitude,
            boolean notifyFamilyMembers,
            boolean emailEnabled,
            String emailAddress
    ) {
        public static NotificationPreferenceView of(NotificationPreference preference) {
            return new NotificationPreferenceView(
                    preference.getId(),
                    preference.isPushoverEnabled(),
                    preference.getPushoverUserKey(),
                    preference.getMinMagnitude(),
                    preference.isNotifyFamilyMembers(),
                    preference.isEmailEnabled(),
                    preference.getEmailAddress()
            );
        }
    }
}
