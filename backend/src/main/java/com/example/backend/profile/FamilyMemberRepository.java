package com.example.backend.profile;

import org.springframework.data.jpa.repository.JpaRepository;

import java.util.List;
import java.util.Optional;
import java.util.UUID;

public interface FamilyMemberRepository extends JpaRepository<FamilyMember, UUID> {
    List<FamilyMember> findByUserIdOrderByCreatedAtAsc(UUID userId);
    Optional<FamilyMember> findByIdAndUserId(UUID id, UUID userId);
}
