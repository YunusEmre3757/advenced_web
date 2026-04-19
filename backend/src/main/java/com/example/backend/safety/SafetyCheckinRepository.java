package com.example.backend.safety;

import org.springframework.data.jpa.repository.JpaRepository;

import java.util.List;
import java.util.Optional;
import java.util.UUID;

public interface SafetyCheckinRepository extends JpaRepository<SafetyCheckin, UUID> {
    Optional<SafetyCheckin> findFirstByUserIdOrderByCreatedAtDesc(UUID userId);

    List<SafetyCheckin> findByUserIdOrderByCreatedAtDesc(UUID userId);
}
