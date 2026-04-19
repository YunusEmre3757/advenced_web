package com.example.backend.profile;

import org.springframework.data.jpa.repository.JpaRepository;

import java.util.List;
import java.util.Optional;
import java.util.UUID;

public interface UserLocationRepository extends JpaRepository<UserLocation, UUID> {
    List<UserLocation> findByUserIdOrderByPrimaryLocationDescCreatedAtAsc(UUID userId);
    Optional<UserLocation> findByIdAndUserId(UUID id, UUID userId);
}
