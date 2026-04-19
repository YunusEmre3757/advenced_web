package com.example.backend.auth;

import com.example.backend.auth.AuthDtos.AuthResponse;
import com.example.backend.auth.AuthDtos.LoginRequest;
import com.example.backend.auth.AuthDtos.RegisterRequest;
import com.example.backend.auth.AuthDtos.UserView;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.HttpStatus;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.server.ResponseStatusException;

@Service
public class AuthService {

    private final UserRepository users;
    private final PasswordEncoder encoder;
    private final JwtService jwt;
    private final long expirationMinutes;

    public AuthService(
            UserRepository users,
            PasswordEncoder encoder,
            JwtService jwt,
            @Value("${security.jwt.expiration-minutes}") long expirationMinutes) {
        this.users = users;
        this.encoder = encoder;
        this.jwt = jwt;
        this.expirationMinutes = expirationMinutes;
    }

    @Transactional
    public AuthResponse register(RegisterRequest req) {
        String email = req.email().trim().toLowerCase();
        if (users.existsByEmailIgnoreCase(email)) {
            throw new ResponseStatusException(HttpStatus.CONFLICT, "email already registered");
        }
        User user = User.builder()
                .email(email)
                .passwordHash(encoder.encode(req.password()))
                .displayName(req.displayName())
                .emailVerified(false)
                .build();
        users.save(user);
        return respond(user);
    }

    @Transactional(readOnly = true)
    public AuthResponse login(LoginRequest req) {
        String email = req.email().trim().toLowerCase();
        User user = users.findByEmailIgnoreCase(email)
                .orElseThrow(() -> new ResponseStatusException(
                        HttpStatus.UNAUTHORIZED, "invalid credentials"));
        if (!encoder.matches(req.password(), user.getPasswordHash())) {
            throw new ResponseStatusException(HttpStatus.UNAUTHORIZED, "invalid credentials");
        }
        return respond(user);
    }

    private AuthResponse respond(User user) {
        return new AuthResponse(jwt.issue(user), expirationMinutes, UserView.of(user));
    }
}
