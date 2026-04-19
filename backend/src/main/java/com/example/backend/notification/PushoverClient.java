package com.example.backend.notification;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;

import java.io.IOException;
import java.net.URI;
import java.net.URLEncoder;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.List;

@Service
public class PushoverClient {

    private final HttpClient http = HttpClient.newBuilder()
            .connectTimeout(Duration.ofSeconds(8))
            .build();

    @Value("${pushover.api-url:https://api.pushover.net/1/messages.json}")
    private String apiUrl;

    @Value("${pushover.app-token:}")
    private String appToken;

    public PushoverResult send(String userKey, String title, String message) {
        if (isBlank(userKey)) {
            return new PushoverResult(false, "SKIPPED", "missing user key");
        }
        if (isBlank(appToken)) {
            return new PushoverResult(true, "DRY_RUN", "PUSHOVER_APP_TOKEN is not configured");
        }

        String body = form(List.of(
                new Param("token", appToken),
                new Param("user", userKey),
                new Param("title", title),
                new Param("message", message),
                new Param("priority", "0")
        ));

        HttpRequest request = HttpRequest.newBuilder()
                .uri(URI.create(apiUrl))
                .timeout(Duration.ofSeconds(12))
                .header("Content-Type", "application/x-www-form-urlencoded")
                .POST(HttpRequest.BodyPublishers.ofString(body))
                .build();

        try {
            HttpResponse<String> response = http.send(request, HttpResponse.BodyHandlers.ofString());
            if (response.statusCode() >= 200 && response.statusCode() < 300) {
                return new PushoverResult(true, "SENT", "Pushover accepted message");
            }
            return new PushoverResult(false, "FAILED", "Pushover returned " + response.statusCode());
        } catch (IOException ex) {
            return new PushoverResult(false, "FAILED", ex.getMessage());
        } catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
            return new PushoverResult(false, "FAILED", "interrupted");
        }
    }

    private String form(List<Param> params) {
        StringBuilder out = new StringBuilder();
        for (Param param : params) {
            if (!out.isEmpty()) {
                out.append('&');
            }
            out.append(encode(param.name())).append('=').append(encode(param.value()));
        }
        return out.toString();
    }

    private String encode(String value) {
        return URLEncoder.encode(value == null ? "" : value, StandardCharsets.UTF_8);
    }

    private boolean isBlank(String value) {
        return value == null || value.trim().isEmpty();
    }

    private record Param(String name, String value) {
    }

    public record PushoverResult(boolean delivered, String status, String message) {
    }
}
