package com.example.backend.notification;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;

import java.io.IOException;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.List;
import java.util.Map;

/**
 * Minimal Resend (resend.com) REST client. Sends transactional emails.
 * Without a configured API key, every call is recorded as DRY_RUN so
 * local development never hits the network.
 */
@Service
public class ResendClient {

    private final HttpClient http = HttpClient.newBuilder()
            .connectTimeout(Duration.ofSeconds(8))
            .build();
    private final ObjectMapper json = new ObjectMapper();

    @Value("${resend.api-url:https://api.resend.com/emails}")
    private String apiUrl;

    @Value("${resend.api-key:}")
    private String apiKey;

    @Value("${resend.from-address:Seismic Command <onboarding@resend.dev>}")
    private String fromAddress;

    public ResendResult send(String toAddress, String subject, String plainBody, String htmlBody) {
        if (isBlank(toAddress)) {
            return new ResendResult(false, "SKIPPED", "missing email address");
        }
        if (isBlank(apiKey)) {
            return new ResendResult(true, "DRY_RUN", "RESEND_API_KEY is not configured");
        }

        String payload;
        try {
            payload = json.writeValueAsString(Map.of(
                    "from", fromAddress,
                    "to", List.of(toAddress),
                    "subject", subject,
                    "text", plainBody,
                    "html", htmlBody == null ? plainBody : htmlBody
            ));
        } catch (JsonProcessingException ex) {
            return new ResendResult(false, "FAILED", "payload serialisation failed: " + ex.getMessage());
        }

        HttpRequest request = HttpRequest.newBuilder()
                .uri(URI.create(apiUrl))
                .timeout(Duration.ofSeconds(12))
                .header("Authorization", "Bearer " + apiKey)
                .header("Content-Type", "application/json")
                .POST(HttpRequest.BodyPublishers.ofString(payload, StandardCharsets.UTF_8))
                .build();

        try {
            HttpResponse<String> response = http.send(request, HttpResponse.BodyHandlers.ofString());
            if (response.statusCode() >= 200 && response.statusCode() < 300) {
                return new ResendResult(true, "SENT", "Resend accepted message");
            }
            return new ResendResult(false, "FAILED", "Resend returned " + response.statusCode());
        } catch (IOException ex) {
            return new ResendResult(false, "FAILED", ex.getMessage());
        } catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
            return new ResendResult(false, "FAILED", "interrupted");
        }
    }

    private boolean isBlank(String value) {
        return value == null || value.trim().isEmpty();
    }

    public record ResendResult(boolean delivered, String status, String message) {
    }
}
