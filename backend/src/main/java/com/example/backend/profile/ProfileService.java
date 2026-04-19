package com.example.backend.profile;

import com.example.backend.auth.User;
import com.example.backend.auth.UserRepository;
import com.example.backend.notification.NotificationPreference;
import com.example.backend.notification.NotificationPreferenceRepository;
import com.example.backend.notification.NotificationDtos.NotificationPreferenceRequest;
import com.example.backend.notification.NotificationDtos.NotificationPreferenceView;
import com.example.backend.profile.ProfileDtos.*;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.server.ResponseStatusException;

import java.util.List;
import java.util.UUID;

@Service
public class ProfileService {

    private final UserRepository users;
    private final UserLocationRepository locations;
    private final FamilyMemberRepository familyMembers;
    private final PastExperienceRepository experiences;
    private final NotificationPreferenceRepository notificationPreferences;

    public ProfileService(
            UserRepository users,
            UserLocationRepository locations,
            FamilyMemberRepository familyMembers,
            PastExperienceRepository experiences,
            NotificationPreferenceRepository notificationPreferences
    ) {
        this.users = users;
        this.locations = locations;
        this.familyMembers = familyMembers;
        this.experiences = experiences;
        this.notificationPreferences = notificationPreferences;
    }

    public List<LocationView> listLocations(UUID userId) {
        return locations.findByUserIdOrderByPrimaryLocationDescCreatedAtAsc(userId)
                .stream()
                .map(LocationView::of)
                .toList();
    }

    @Transactional
    public NotificationPreferenceView getNotificationPreference(UUID userId) {
        NotificationPreference preference = notificationPreferences.findByUserId(userId)
                .orElseGet(() -> notificationPreferences.save(NotificationPreference.builder()
                        .user(requireUser(userId))
                        .pushoverEnabled(false)
                        .pushoverUserKey(null)
                        .minMagnitude(3.0)
                        .notifyFamilyMembers(true)
                        .build()));
        return NotificationPreferenceView.of(preference);
    }

    @Transactional
    public NotificationPreferenceView updateNotificationPreference(UUID userId, NotificationPreferenceRequest req) {
        NotificationPreference preference = notificationPreferences.findByUserId(userId)
                .orElseGet(() -> NotificationPreference.builder()
                        .user(requireUser(userId))
                        .build());
        preference.setPushoverEnabled(req.pushoverEnabled());
        preference.setPushoverUserKey(clean(req.pushoverUserKey()));
        preference.setMinMagnitude(req.minMagnitude());
        preference.setNotifyFamilyMembers(req.notifyFamilyMembers());
        preference.setEmailEnabled(req.emailEnabled());
        preference.setEmailAddress(clean(req.emailAddress()));
        return NotificationPreferenceView.of(notificationPreferences.save(preference));
    }

    @Transactional
    public LocationView createLocation(UUID userId, LocationRequest req) {
        User user = requireUser(userId);
        if (req.primaryLocation()) {
            clearPrimaryLocations(userId, null);
        }
        UserLocation location = UserLocation.builder()
                .user(user)
                .label(clean(req.label()))
                .city(clean(req.city()))
                .district(clean(req.district()))
                .latitude(req.latitude())
                .longitude(req.longitude())
                .radiusKm(req.radiusKm())
                .primaryLocation(req.primaryLocation())
                .build();
        return LocationView.of(locations.save(location));
    }

    @Transactional
    public LocationView updateLocation(UUID userId, UUID locationId, LocationRequest req) {
        UserLocation location = locations.findByIdAndUserId(locationId, userId)
                .orElseThrow(() -> notFound("location not found"));
        if (req.primaryLocation()) {
            clearPrimaryLocations(userId, locationId);
        }
        location.setLabel(clean(req.label()));
        location.setCity(clean(req.city()));
        location.setDistrict(clean(req.district()));
        location.setLatitude(req.latitude());
        location.setLongitude(req.longitude());
        location.setRadiusKm(req.radiusKm());
        location.setPrimaryLocation(req.primaryLocation());
        return LocationView.of(location);
    }

    @Transactional
    public void deleteLocation(UUID userId, UUID locationId) {
        UserLocation location = locations.findByIdAndUserId(locationId, userId)
                .orElseThrow(() -> notFound("location not found"));
        locations.delete(location);
    }

    public List<FamilyMemberView> listFamilyMembers(UUID userId) {
        return familyMembers.findByUserIdOrderByCreatedAtAsc(userId)
                .stream()
                .map(FamilyMemberView::of)
                .toList();
    }

    @Transactional
    public FamilyMemberView createFamilyMember(UUID userId, FamilyMemberRequest req) {
        User user = requireUser(userId);
        FamilyMember member = FamilyMember.builder()
                .user(user)
                .name(clean(req.name()))
                .relationship(clean(req.relationship()))
                .phone(clean(req.phone()))
                .email(clean(req.email()))
                .pushoverKey(clean(req.pushoverKey()))
                .notify(req.notifyEnabled())
                .build();
        return FamilyMemberView.of(familyMembers.save(member));
    }

    @Transactional
    public FamilyMemberView updateFamilyMember(UUID userId, UUID memberId, FamilyMemberRequest req) {
        FamilyMember member = familyMembers.findByIdAndUserId(memberId, userId)
                .orElseThrow(() -> notFound("family member not found"));
        member.setName(clean(req.name()));
        member.setRelationship(clean(req.relationship()));
        member.setPhone(clean(req.phone()));
        member.setEmail(clean(req.email()));
        member.setPushoverKey(clean(req.pushoverKey()));
        member.setNotify(req.notifyEnabled());
        return FamilyMemberView.of(member);
    }

    @Transactional
    public void deleteFamilyMember(UUID userId, UUID memberId) {
        FamilyMember member = familyMembers.findByIdAndUserId(memberId, userId)
                .orElseThrow(() -> notFound("family member not found"));
        familyMembers.delete(member);
    }

    public List<PastExperienceView> listPastExperiences(UUID userId) {
        return experiences.findByUserIdOrderByEventDateDescCreatedAtDesc(userId)
                .stream()
                .map(PastExperienceView::of)
                .toList();
    }

    @Transactional
    public PastExperienceView createPastExperience(UUID userId, PastExperienceRequest req) {
        User user = requireUser(userId);
        PastExperience experience = PastExperience.builder()
                .user(user)
                .title(clean(req.title()))
                .eventDate(req.eventDate())
                .location(clean(req.location()))
                .magnitude(req.magnitude())
                .emotionalImpact(clean(req.emotionalImpact()))
                .notes(clean(req.notes()))
                .build();
        return PastExperienceView.of(experiences.save(experience));
    }

    @Transactional
    public PastExperienceView updatePastExperience(UUID userId, UUID experienceId, PastExperienceRequest req) {
        PastExperience experience = experiences.findByIdAndUserId(experienceId, userId)
                .orElseThrow(() -> notFound("past experience not found"));
        experience.setTitle(clean(req.title()));
        experience.setEventDate(req.eventDate());
        experience.setLocation(clean(req.location()));
        experience.setMagnitude(req.magnitude());
        experience.setEmotionalImpact(clean(req.emotionalImpact()));
        experience.setNotes(clean(req.notes()));
        return PastExperienceView.of(experience);
    }

    @Transactional
    public void deletePastExperience(UUID userId, UUID experienceId) {
        PastExperience experience = experiences.findByIdAndUserId(experienceId, userId)
                .orElseThrow(() -> notFound("past experience not found"));
        experiences.delete(experience);
    }

    private User requireUser(UUID userId) {
        return users.findById(userId)
                .orElseThrow(() -> new ResponseStatusException(HttpStatus.UNAUTHORIZED, "user not found"));
    }

    private void clearPrimaryLocations(UUID userId, UUID exceptLocationId) {
        locations.findByUserIdOrderByPrimaryLocationDescCreatedAtAsc(userId).forEach(location -> {
            if (!location.getId().equals(exceptLocationId)) {
                location.setPrimaryLocation(false);
            }
        });
    }

    private ResponseStatusException notFound(String message) {
        return new ResponseStatusException(HttpStatus.NOT_FOUND, message);
    }

    private String clean(String value) {
        if (value == null) {
            return null;
        }
        String trimmed = value.trim();
        return trimmed.isEmpty() ? null : trimmed;
    }
}
