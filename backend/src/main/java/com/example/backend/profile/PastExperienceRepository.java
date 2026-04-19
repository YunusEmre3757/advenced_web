package com.example.backend.profile;

import org.springframework.data.jpa.repository.JpaRepository;

import java.util.List;
import java.util.Optional;
import java.util.UUID;

public interface PastExperienceRepository extends JpaRepository<PastExperience, UUID> {
    List<PastExperience> findByUserIdOrderByEventDateDescCreatedAtDesc(UUID userId);
    Optional<PastExperience> findByIdAndUserId(UUID id, UUID userId);
}
