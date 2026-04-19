package com.example.backend.safety;

import com.example.backend.safety.SafetyDtos.*;
import jakarta.validation.Valid;
import org.springframework.http.HttpStatus;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.server.ResponseStatusException;

import java.util.List;
import java.util.UUID;

@RestController
@RequestMapping("/api/safety")
public class SafetyController {

    private final SafetyService safety;

    public SafetyController(SafetyService safety) {
        this.safety = safety;
    }

    @PostMapping("/check-in")
    @ResponseStatus(HttpStatus.CREATED)
    public CheckinResponse checkIn(
            @AuthenticationPrincipal UUID userId,
            @Valid @RequestBody CheckinRequest req
    ) {
        return safety.checkIn(requireUserId(userId), req);
    }

    @GetMapping("/latest")
    public CheckinView latest(@AuthenticationPrincipal UUID userId) {
        CheckinView view = safety.latest(requireUserId(userId));
        if (view == null) {
            throw new ResponseStatusException(HttpStatus.NOT_FOUND, "no check-in yet");
        }
        return view;
    }

    @GetMapping("/history")
    public List<CheckinView> history(@AuthenticationPrincipal UUID userId) {
        return safety.history(requireUserId(userId));
    }

    private UUID requireUserId(UUID userId) {
        if (userId == null) {
            throw new ResponseStatusException(HttpStatus.UNAUTHORIZED, "not authenticated");
        }
        return userId;
    }
}
