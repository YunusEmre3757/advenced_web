package com.example.backend.profile;

import jakarta.validation.constraints.*;

import java.time.LocalDate;
import java.util.UUID;

public final class ProfileDtos {

    private ProfileDtos() {
    }

    public record LocationRequest(
            @NotBlank @Size(max = 80) String label,
            @Size(max = 80) String city,
            @Size(max = 80) String district,
            @DecimalMin("-90.0") @DecimalMax("90.0") double latitude,
            @DecimalMin("-180.0") @DecimalMax("180.0") double longitude,
            @DecimalMin("1.0") @DecimalMax("500.0") double radiusKm,
            boolean primaryLocation
    ) {
    }

    public record LocationView(
            UUID id,
            String label,
            String city,
            String district,
            double latitude,
            double longitude,
            double radiusKm,
            boolean primaryLocation
    ) {
        static LocationView of(UserLocation location) {
            return new LocationView(
                    location.getId(),
                    location.getLabel(),
                    location.getCity(),
                    location.getDistrict(),
                    location.getLatitude(),
                    location.getLongitude(),
                    location.getRadiusKm(),
                    location.isPrimaryLocation()
            );
        }
    }

    public record FamilyMemberRequest(
            @NotBlank @Size(max = 120) String name,
            @Size(max = 80) String relationship,
            @Size(max = 40) String phone,
            @Email @Size(max = 255) String email,
            @Size(max = 80) String pushoverKey,
            boolean notifyEnabled
    ) {
    }

    public record FamilyMemberView(
            UUID id,
            String name,
            String relationship,
            String phone,
            String email,
            String pushoverKey,
            boolean notifyEnabled
    ) {
        static FamilyMemberView of(FamilyMember member) {
            return new FamilyMemberView(
                    member.getId(),
                    member.getName(),
                    member.getRelationship(),
                    member.getPhone(),
                    member.getEmail(),
                    member.getPushoverKey(),
                    member.isNotify()
            );
        }
    }

    public record PastExperienceRequest(
            @NotBlank @Size(max = 140) String title,
            LocalDate eventDate,
            @Size(max = 160) String location,
            @DecimalMin("0.0") @DecimalMax("10.0") Double magnitude,
            @Size(max = 80) String emotionalImpact,
            @Size(max = 4000) String notes
    ) {
    }

    public record PastExperienceView(
            UUID id,
            String title,
            LocalDate eventDate,
            String location,
            Double magnitude,
            String emotionalImpact,
            String notes
    ) {
        static PastExperienceView of(PastExperience experience) {
            return new PastExperienceView(
                    experience.getId(),
                    experience.getTitle(),
                    experience.getEventDate(),
                    experience.getLocation(),
                    experience.getMagnitude(),
                    experience.getEmotionalImpact(),
                    experience.getNotes()
            );
        }
    }
}
