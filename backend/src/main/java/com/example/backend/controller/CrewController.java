package com.example.backend.controller;

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

@RestController
@RequestMapping("/api/crew")
@CrossOrigin(origins = {
        "http://localhost:4200",
        "http://127.0.0.1:4200",
        "http://localhost:5173",
        "http://127.0.0.1:5173"
})
public class CrewController {

    private static final String CREW_API_URL = "http://localhost:8002/analyze";
    private static final int TIMEOUT_SECONDS = 180; // crew pipeline ~1-2 min

    private final ObjectMapper objectMapper;
    private final HttpClient httpClient = HttpClient.newBuilder()
            .connectTimeout(Duration.ofSeconds(10))
            .build();

    public CrewController(ObjectMapper objectMapper) {
        this.objectMapper = objectMapper;
    }

    /**
     * POST /api/crew/analyze
     * Forwards the earthquake event to the Python CrewAI FastAPI service
     * and returns the structured multi-agent analysis result.
     *
     * Body: { eventId, location, magnitude, depthKm, latitude, longitude, hours?, minMagnitude? }
     */
    @PostMapping(value = "/analyze", consumes = MediaType.APPLICATION_JSON_VALUE,
            produces = MediaType.APPLICATION_JSON_VALUE)
    public JsonNode analyze(@RequestBody JsonNode body) {
        try {
            String payload = objectMapper.writeValueAsString(body);

            HttpRequest request = HttpRequest.newBuilder()
                    .uri(URI.create(CREW_API_URL))
                    .timeout(Duration.ofSeconds(TIMEOUT_SECONDS))
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

            return objectMapper.readTree(response.body());

        } catch (ResponseStatusException rse) {
            throw rse;
        } catch (java.net.ConnectException ce) {
            // FastAPI not running — return a helpful error JSON
            ObjectNode err = objectMapper.createObjectNode();
            err.put("error", "crew_unavailable");
            err.put("message", "CrewAI servisi çalışmıyor. 'cd crew && uvicorn api:app --port 8001' ile başlatın.");
            return err;
        } catch (Exception e) {
            throw new ResponseStatusException(
                    HttpStatus.INTERNAL_SERVER_ERROR,
                    "Crew analizi başarısız: " + e.getMessage());
        }
    }

    /**
     * GET /api/crew/health
     * Checks whether the Python CrewAI service is reachable.
     */
    @GetMapping("/health")
    public JsonNode health() {
        try {
            HttpRequest request = HttpRequest.newBuilder()
                    .uri(URI.create("http://localhost:8002/health"))
                    .timeout(Duration.ofSeconds(5))
                    .GET()
                    .build();

            HttpResponse<String> response = httpClient.send(
                    request, HttpResponse.BodyHandlers.ofString());

            ObjectNode result = objectMapper.createObjectNode();
            result.put("crewApiStatus", response.statusCode() == 200 ? "up" : "error");
            result.put("crewApiCode", response.statusCode());
            return result;

        } catch (Exception e) {
            ObjectNode result = objectMapper.createObjectNode();
            result.put("crewApiStatus", "down");
            result.put("message", e.getMessage());
            return result;
        }
    }
}
