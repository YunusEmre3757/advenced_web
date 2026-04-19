package com.example.backend.geocode;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.web.server.ResponseStatusException;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.ObjectMapper;

import java.net.URI;
import java.net.URLEncoder;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.Optional;

@Service
public class GeocodeService {

    private final ObjectMapper objectMapper;
    private final HttpClient http = HttpClient.newBuilder()
            .connectTimeout(Duration.ofSeconds(8))
            .followRedirects(HttpClient.Redirect.NORMAL)
            .build();
    private final String nominatimBaseUrl;
    private final String userAgent;
    private final int timeoutSeconds;

    public GeocodeService(
            ObjectMapper objectMapper,
            @Value("${geocode.nominatim.base-url:https://nominatim.openstreetmap.org}") String nominatimBaseUrl,
            @Value("${geocode.nominatim.user-agent:SeismicCommand/1.0 (contact: local-dev)}") String userAgent,
            @Value("${geocode.nominatim.timeout-seconds:12}") int timeoutSeconds
    ) {
        this.objectMapper = objectMapper;
        this.nominatimBaseUrl = nominatimBaseUrl;
        this.userAgent = userAgent;
        this.timeoutSeconds = timeoutSeconds;
    }

    public Optional<GeocodeResult> searchOne(String query) {
        String normalized = query == null ? "" : query.trim();
        if (normalized.length() < 5) {
            return Optional.empty();
        }

        String encodedQuery = URLEncoder.encode(normalized, StandardCharsets.UTF_8);
        String url = nominatimBaseUrl
                + "/search?q=" + encodedQuery
                + "&format=jsonv2&limit=1&addressdetails=1&countrycodes=tr";

        HttpRequest request = HttpRequest.newBuilder()
                .uri(URI.create(url))
                .timeout(Duration.ofSeconds(timeoutSeconds))
                .header("Accept", "application/json")
                .header("Accept-Language", "tr,en;q=0.8")
                .header("User-Agent", userAgent)
                .GET()
                .build();

        try {
            HttpResponse<String> response = http.send(request, HttpResponse.BodyHandlers.ofString());
            if (response.statusCode() < 200 || response.statusCode() >= 300) {
                throw new ResponseStatusException(HttpStatus.BAD_GATEWAY,
                        "Adres arama servisi " + response.statusCode() + " dondu.");
            }

            JsonNode root = objectMapper.readTree(response.body());
            if (!root.isArray() || root.isEmpty()) {
                return Optional.empty();
            }

            JsonNode first = root.get(0);
            double lat = first.path("lat").asDouble(Double.NaN);
            double lon = first.path("lon").asDouble(Double.NaN);
            String displayName = first.path("display_name").asText(normalized);
            if (Double.isNaN(lat) || Double.isNaN(lon)) {
                return Optional.empty();
            }

            return Optional.of(new GeocodeResult(lat, lon, displayName));
        } catch (ResponseStatusException ex) {
            throw ex;
        } catch (java.net.http.HttpTimeoutException ex) {
            throw new ResponseStatusException(HttpStatus.GATEWAY_TIMEOUT,
                    "Adres arama zaman asimina ugradi.");
        } catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
            throw new ResponseStatusException(HttpStatus.INTERNAL_SERVER_ERROR,
                    "Adres arama islemi kesildi.");
        } catch (Exception ex) {
            throw new ResponseStatusException(HttpStatus.BAD_GATEWAY,
                    "Adres arama servisine baglanilamadi: " + ex.getMessage());
        }
    }
}
