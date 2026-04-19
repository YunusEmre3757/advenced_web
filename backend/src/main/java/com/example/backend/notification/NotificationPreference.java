package com.example.backend.notification;

import com.example.backend.auth.User;
import jakarta.persistence.*;
import lombok.*;

import java.time.OffsetDateTime;
import java.util.UUID;

@Entity
@Table(name = "notification_preferences", schema = "app")
@Getter
@Setter
@NoArgsConstructor
@AllArgsConstructor
@Builder
public class NotificationPreference {

    @Id
    @GeneratedValue
    @Column(columnDefinition = "uuid")
    private UUID id;

    @OneToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "user_id", nullable = false, unique = true)
    private User user;

    @Column(name = "pushover_enabled", nullable = false)
    private boolean pushoverEnabled;

    @Column(name = "pushover_user_key", length = 80)
    private String pushoverUserKey;

    @Column(name = "min_magnitude", nullable = false)
    private double minMagnitude;

    @Column(name = "notify_family_members", nullable = false)
    private boolean notifyFamilyMembers;

    @Column(name = "email_enabled", nullable = false)
    private boolean emailEnabled;

    @Column(name = "email_address", length = 255)
    private String emailAddress;

    @Column(name = "created_at", nullable = false, updatable = false)
    private OffsetDateTime createdAt;

    @Column(name = "updated_at", nullable = false)
    private OffsetDateTime updatedAt;

    @PrePersist
    void onCreate() {
        OffsetDateTime now = OffsetDateTime.now();
        if (createdAt == null) createdAt = now;
        updatedAt = now;
        if (minMagnitude <= 0) minMagnitude = 3.0;
    }

    @PreUpdate
    void onUpdate() {
        updatedAt = OffsetDateTime.now();
    }
}
