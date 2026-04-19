package com.example.backend.controller;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.server.ResponseStatusException;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.ObjectMapper;
import tools.jackson.databind.node.ObjectNode;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;
import java.time.Instant;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;

@RestController
@RequestMapping("/api/crew")
@CrossOrigin(origins = {
        "http://localhost:4200",
        "http://127.0.0.1:4200",
        "http://localhost:5173",
        "http://127.0.0.1:5173"
})
public class CrewController {

    private final String crewServiceUrl;
    private final int timeoutSeconds;
    private final long cacheTtlMillis;

    private final ObjectMapper objectMapper;
    private final HttpClient httpClient = HttpClient.newBuilder()
            .connectTimeout(Duration.ofSeconds(10))
            .build();

    // In-memory cache: eventId -> (expiresAt, payload)
    private final Map<String, CacheEntry> cache = new ConcurrentHashMap<>();

    public CrewController(
            ObjectMapper objectMapper,
            @Value("${crew.service.url:http://localhost:8001}") String crewServiceUrl,
            @Value("${crew.service.timeout-seconds:180}") int timeoutSeconds,
            @Value("${crew.service.cache-ttl-seconds:3600}") long cacheTtlSeconds) {
        this.objectMapper = objectMapper;
        this.crewServiceUrl = crewServiceUrl;
        this.timeoutSeconds = timeoutSeconds;
        this.cacheTtlMillis = cacheTtlSeconds * 1000L;
    }

    @PostMapping(value = "/analyze", consumes = MediaType.APPLICATION_JSON_VALUE,
            produces = MediaType.APPLICATION_JSON_VALUE)
    public JsonNode analyze(@RequestBody JsonNode body) {
        String eventId = null;
        if (body.has("eventId")) {
            JsonNode idNode = body.get("eventId");
            if (!idNode.isNull()) {
                eventId = idNode.asText();
            }
        }

        if (eventId != null && !eventId.isBlank()) {
            CacheEntry hit = cache.get(eventId);
            if (hit != null && hit.expiresAt > System.currentTimeMillis()) {
                return hit.payload;
            }
        }

        try {
            String payload = objectMapper.writeValueAsString(body);

            HttpRequest request = HttpRequest.newBuilder()
                    .uri(URI.create(crewServiceUrl + "/analyze"))
                    .timeout(Duration.ofSeconds(timeoutSeconds))
                    .header("Content-Type", "application/json")
                    .POST(HttpRequest.BodyPublishers.ofString(payload))
                    .build();

            HttpResponse<String> response = httpClient.send(
                    request, HttpResponse.BodyHandlers.ofString());

            if (response.statusCode() < 200 || response.statusCode() >= 300) {
                throw new ResponseStatusException(
                        HttpStatus.BAD_GATEWAY,
                        "CrewAI service returned " + response.statusCode());
            }

            JsonNode result = objectMapper.readTree(response.body());

            if (eventId != null && !eventId.isBlank() && !result.has("error")) {
                cache.put(eventId, new CacheEntry(
                        System.currentTimeMillis() + cacheTtlMillis, result));
            }

            return result;

        } catch (ResponseStatusException rse) {
            throw rse;
        } catch (java.net.ConnectException ce) {
            ObjectNode err = objectMapper.createObjectNode();
            err.put("error", "crew_unavailable");
            err.put("message", "CrewAI servisi çalışmıyor. 'cd crew && uvicorn api:app --port 8001' ile başlatın.");
            return err;
        } catch (java.net.http.HttpTimeoutException te) {
            ObjectNode err = objectMapper.createObjectNode();
            err.put("error", "crew_timeout");
            err.put("message", "Crew analizi " + timeoutSeconds + " saniye içinde tamamlanmadı. Tekrar deneyin.");
            return err;
        } catch (Exception e) {
            throw new ResponseStatusException(
                    HttpStatus.INTERNAL_SERVER_ERROR,
                    "Crew analizi başarısız: " + e.getMessage());
        }
    }

    @GetMapping("/health")
    public JsonNode health() {
        ObjectNode result = objectMapper.createObjectNode();
        try {
            HttpRequest request = HttpRequest.newBuilder()
                    .uri(URI.create(crewServiceUrl + "/health"))
                    .timeout(Duration.ofSeconds(5))
                    .GET()
                    .build();

            HttpResponse<String> response = httpClient.send(
                    request, HttpResponse.BodyHandlers.ofString());

            result.put("crewApiStatus", response.statusCode() == 200 ? "up" : "error");
            result.put("crewApiCode", response.statusCode());
            result.put("crewServiceUrl", crewServiceUrl);
            result.put("cacheSize", cache.size());
            return result;

        } catch (Exception e) {
            result.put("crewApiStatus", "down");
            result.put("crewServiceUrl", crewServiceUrl);
            result.put("message", e.getMessage());
            result.put("cacheSize", cache.size());
            return result;
        }
    }

    @DeleteMapping("/cache")
    public JsonNode clearCache() {
        int size = cache.size();
        cache.clear();
        ObjectNode result = objectMapper.createObjectNode();
        result.put("cleared", size);
        result.put("at", Instant.now().toString());
        return result;
    }

    private static final class CacheEntry {
        final long expiresAt;
        final JsonNode payload;
        CacheEntry(long expiresAt, JsonNode payload) {
            this.expiresAt = expiresAt;
            this.payload = payload;
        }
    }
}
