package com.example.backend.auth;

import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

import java.util.UUID;

public final class AuthDtos {

    private AuthDtos() {}

    public record RegisterRequest(
            @Email @NotBlank String email,
            @NotBlank @Size(min = 8, max = 100) String password,
            @Size(max = 120) String displayName) {}

    public record LoginRequest(
            @Email @NotBlank String email,
            @NotBlank String password) {}

    public record AuthResponse(
            String token,
            long expiresInMinutes,
            UserView user) {}

    public record UserView(
            UUID id,
            String email,
            String displayName,
            boolean emailVerified) {
        public static UserView of(User u) {
            return new UserView(u.getId(), u.getEmail(), u.getDisplayName(), u.isEmailVerified());
        }
    }
}
