package com.example.backend.notification;

import com.example.backend.auth.User;
import jakarta.persistence.*;
import lombok.*;

import java.time.OffsetDateTime;
import java.util.UUID;

@Entity
@Table(name = "notification_deliveries", schema = "app")
@Getter
@Setter
@NoArgsConstructor
@AllArgsConstructor
@Builder
public class NotificationDelivery {

    @Id
    @GeneratedValue
    @Column(columnDefinition = "uuid")
    private UUID id;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "user_id", nullable = false)
    private User user;

    @Column(name = "event_id", nullable = false, length = 120)
    private String eventId;

    @Column(nullable = false, length = 40)
    private String channel;

    @Column(name = "recipient_type", nullable = false, length = 40)
    private String recipientType;

    @Column(name = "recipient_label", length = 160)
    private String recipientLabel;

    @Column(name = "recipient_key_hash", nullable = false, length = 96)
    private String recipientKeyHash;

    @Column(nullable = false, length = 40)
    private String status;

    @Column(name = "provider_message", length = 500)
    private String providerMessage;

    @Column(name = "created_at", nullable = false, updatable = false)
    private OffsetDateTime createdAt;

    @PrePersist
    void onCreate() {
        if (createdAt == null) {
            createdAt = OffsetDateTime.now();
        }
    }
}
