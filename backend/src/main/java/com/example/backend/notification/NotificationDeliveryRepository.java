package com.example.backend.notification;

import org.springframework.data.jpa.repository.JpaRepository;

import java.util.UUID;

public interface NotificationDeliveryRepository extends JpaRepository<NotificationDelivery, UUID> {
    boolean existsByUserIdAndEventIdAndChannelAndRecipientKeyHash(
            UUID userId,
            String eventId,
            String channel,
            String recipientKeyHash
    );
}
