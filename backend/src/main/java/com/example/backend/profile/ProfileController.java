package com.example.backend.profile;

import com.example.backend.profile.ProfileDtos.*;
import com.example.backend.notification.NotificationDtos.NotificationPreferenceRequest;
import com.example.backend.notification.NotificationDtos.NotificationPreferenceView;
import jakarta.validation.Valid;
import org.springframework.http.HttpStatus;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.server.ResponseStatusException;

import java.util.List;
import java.util.UUID;

@RestController
@RequestMapping("/api/profile")
public class ProfileController {

    private final ProfileService profile;

    public ProfileController(ProfileService profile) {
        this.profile = profile;
    }

    @GetMapping("/notification-preferences")
    public NotificationPreferenceView getNotificationPreference(@AuthenticationPrincipal UUID userId) {
        return profile.getNotificationPreference(requireUserId(userId));
    }

    @PutMapping("/notification-preferences")
    public NotificationPreferenceView updateNotificationPreference(
            @AuthenticationPrincipal UUID userId,
            @Valid @RequestBody NotificationPreferenceRequest req
    ) {
        return profile.updateNotificationPreference(requireUserId(userId), req);
    }

    @GetMapping("/locations")
    public List<LocationView> listLocations(@AuthenticationPrincipal UUID userId) {
        return profile.listLocations(requireUserId(userId));
    }

    @PostMapping("/locations")
    @ResponseStatus(HttpStatus.CREATED)
    public LocationView createLocation(
            @AuthenticationPrincipal UUID userId,
            @Valid @RequestBody LocationRequest req
    ) {
        return profile.createLocation(requireUserId(userId), req);
    }

    @PutMapping("/locations/{locationId}")
    public LocationView updateLocation(
            @AuthenticationPrincipal UUID userId,
            @PathVariable UUID locationId,
            @Valid @RequestBody LocationRequest req
    ) {
        return profile.updateLocation(requireUserId(userId), locationId, req);
    }

    @DeleteMapping("/locations/{locationId}")
    @ResponseStatus(HttpStatus.NO_CONTENT)
    public void deleteLocation(@AuthenticationPrincipal UUID userId, @PathVariable UUID locationId) {
        profile.deleteLocation(requireUserId(userId), locationId);
    }

    @GetMapping("/family-members")
    public List<FamilyMemberView> listFamilyMembers(@AuthenticationPrincipal UUID userId) {
        return profile.listFamilyMembers(requireUserId(userId));
    }

    @PostMapping("/family-members")
    @ResponseStatus(HttpStatus.CREATED)
    public FamilyMemberView createFamilyMember(
            @AuthenticationPrincipal UUID userId,
            @Valid @RequestBody FamilyMemberRequest req
    ) {
        return profile.createFamilyMember(requireUserId(userId), req);
    }

    @PutMapping("/family-members/{memberId}")
    public FamilyMemberView updateFamilyMember(
            @AuthenticationPrincipal UUID userId,
            @PathVariable UUID memberId,
            @Valid @RequestBody FamilyMemberRequest req
    ) {
        return profile.updateFamilyMember(requireUserId(userId), memberId, req);
    }

    @DeleteMapping("/family-members/{memberId}")
    @ResponseStatus(HttpStatus.NO_CONTENT)
    public void deleteFamilyMember(@AuthenticationPrincipal UUID userId, @PathVariable UUID memberId) {
        profile.deleteFamilyMember(requireUserId(userId), memberId);
    }

    @GetMapping("/past-experiences")
    public List<PastExperienceView> listPastExperiences(@AuthenticationPrincipal UUID userId) {
        return profile.listPastExperiences(requireUserId(userId));
    }

    @PostMapping("/past-experiences")
    @ResponseStatus(HttpStatus.CREATED)
    public PastExperienceView createPastExperience(
            @AuthenticationPrincipal UUID userId,
            @Valid @RequestBody PastExperienceRequest req
    ) {
        return profile.createPastExperience(requireUserId(userId), req);
    }

    @PutMapping("/past-experiences/{experienceId}")
    public PastExperienceView updatePastExperience(
            @AuthenticationPrincipal UUID userId,
            @PathVariable UUID experienceId,
            @Valid @RequestBody PastExperienceRequest req
    ) {
        return profile.updatePastExperience(requireUserId(userId), experienceId, req);
    }

    @DeleteMapping("/past-experiences/{experienceId}")
    @ResponseStatus(HttpStatus.NO_CONTENT)
    public void deletePastExperience(@AuthenticationPrincipal UUID userId, @PathVariable UUID experienceId) {
        profile.deletePastExperience(requireUserId(userId), experienceId);
    }

    private UUID requireUserId(UUID userId) {
        if (userId == null) {
            throw new ResponseStatusException(HttpStatus.UNAUTHORIZED, "not authenticated");
        }
        return userId;
    }
}
