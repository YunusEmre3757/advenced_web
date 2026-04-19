package com.example.backend.graph;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.stereotype.Component;
import org.springframework.web.servlet.mvc.method.annotation.SseEmitter;
import org.springframework.web.server.ResponseStatusException;

import java.net.URI;
import java.net.URLEncoder;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.io.BufferedReader;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.Map;
import java.util.concurrent.CompletableFuture;

@Component
public class GraphClient {

    private final ObjectMapper mapper = new ObjectMapper();
    private final HttpClient http = HttpClient.newBuilder()
            .version(HttpClient.Version.HTTP_1_1)
            .connectTimeout(Duration.ofSeconds(5))
            .build();

    @Value("${graph.service.url:http://localhost:8002}")
    private String baseUrl;

    @Value("${graph.service.timeout-seconds:60}")
    private int timeoutSeconds;

    public Object postJson(String path, Map<String, Object> body) {
        return mapper.convertValue(postJsonNode(path, body), Object.class);
    }

    public JsonNode postJsonNode(String path, Map<String, Object> body) {
        try {
            String json = mapper.writeValueAsString(body);
            HttpRequest req = HttpRequest.newBuilder()
                    .uri(URI.create(baseUrl + path))
                    .version(HttpClient.Version.HTTP_1_1)
                    .timeout(Duration.ofSeconds(timeoutSeconds))
                    .header("Content-Type", "application/json")
                    .POST(HttpRequest.BodyPublishers.ofString(json, StandardCharsets.UTF_8))
                    .build();
            HttpResponse<String> res = http.send(req, HttpResponse.BodyHandlers.ofString(StandardCharsets.UTF_8));
            if (res.statusCode() < 200 || res.statusCode() >= 300) {
                throw new ResponseStatusException(HttpStatus.BAD_GATEWAY,
                        "Graph service returned " + res.statusCode() + ": " + res.body());
            }
            return mapper.readTree(res.body());
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            throw new ResponseStatusException(HttpStatus.SERVICE_UNAVAILABLE, "Graph call interrupted", e);
        } catch (ResponseStatusException e) {
            throw e;
        } catch (Exception e) {
            throw new ResponseStatusException(HttpStatus.SERVICE_UNAVAILABLE,
                    "Graph service unreachable: " + e.getMessage(), e);
        }
    }

    public SseEmitter streamChat(String question, String sessionId, Double latitude, Double longitude) {
        SseEmitter emitter = new SseEmitter(Duration.ofSeconds(timeoutSeconds).toMillis() + 10_000);
        CompletableFuture.runAsync(() -> {
            StringBuilder path = new StringBuilder("/graph/chat/stream?question=")
                    .append(encode(question))
                    .append("&sessionId=")
                    .append(encode(sessionId == null || sessionId.isBlank() ? "default" : sessionId));
            if (latitude != null && longitude != null) {
                path.append("&latitude=").append(latitude).append("&longitude=").append(longitude);
            }
            try {
                HttpRequest req = HttpRequest.newBuilder()
                        .uri(URI.create(baseUrl + path))
                        .version(HttpClient.Version.HTTP_1_1)
                        .timeout(Duration.ofSeconds(timeoutSeconds))
                        .header("Accept", MediaType.TEXT_EVENT_STREAM_VALUE)
                        .GET()
                        .build();
                HttpResponse<InputStream> res = http.send(req, HttpResponse.BodyHandlers.ofInputStream());
                if (res.statusCode() < 200 || res.statusCode() >= 300) {
                    emitter.completeWithError(new ResponseStatusException(
                            HttpStatus.BAD_GATEWAY, "Graph stream returned " + res.statusCode()));
                    return;
                }

                try (BufferedReader reader = new BufferedReader(
                        new InputStreamReader(res.body(), StandardCharsets.UTF_8))) {
                    String eventName = "message";
                    String line;
                    while ((line = reader.readLine()) != null) {
                        if (line.startsWith("event:")) {
                            eventName = line.substring("event:".length()).trim();
                        } else if (line.startsWith("data:")) {
                            String data = line.substring("data:".length()).trim();
                            emitter.send(SseEmitter.event().name(eventName).data(data));
                        }
                    }
                }
                emitter.complete();
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
                emitter.completeWithError(e);
            } catch (Exception e) {
                emitter.completeWithError(e);
            }
        });
        return emitter;
    }

    private String encode(String value) {
        return URLEncoder.encode(value, StandardCharsets.UTF_8);
    }
}
