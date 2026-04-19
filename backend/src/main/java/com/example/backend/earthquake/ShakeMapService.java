package com.example.backend.earthquake;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.stereotype.Service;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;

/**
 * Fetches USGS ShakeMap product data for a given event.
 *
 * ShakeMap is available for M≥3.5 earthquakes with sufficient station coverage.
 * Returns null gracefully when no ShakeMap exists (small or offshore events).
 *
 * Fields returned:
 *   maxMmi       — maximum Modified Mercalli Intensity (1–10 scale)
 *   maxPga       — peak ground acceleration in g (e.g. 0.15 = 15% g)
 *   maxPgv       — peak ground velocity in cm/s
 *   maxPsa03     — spectral acceleration at 0.3s (short-period structures)
 *   maxPsa10     — spectral acceleration at 1.0s (mid-rise structures)
 *   maxPsa30     — spectral acceleration at 3.0s (tall structures)
 *   mapStatus    — "automatic" or "reviewed"
 *   reviewStatus — "automatic" or "reviewed"
 *   processTime  — ISO timestamp of last ShakeMap processing
 *   shakeMapUrl  — direct link to USGS ShakeMap page
 *   intensityMapUrl — URL of intensity overlay image (for display)
 */
@Service
public class ShakeMapService {

    private static final String USGS_DETAIL_URL =
            "https://earthquake.usgs.gov/earthquakes/feed/v1.0/detail/%s.geojson";
    private static final String SHAKEMAP_PAGE_URL =
            "https://earthquake.usgs.gov/earthquakes/eventpage/%s/shakemap/intensity";

    private final ObjectMapper mapper = new ObjectMapper();
    private final HttpClient http = HttpClient.newBuilder()
            .followRedirects(HttpClient.Redirect.NORMAL)
            .connectTimeout(Duration.ofSeconds(10))
            .build();

    // Cache: eventId → ShakeMapDto (null means "no shakemap exists")
    private final Map<String, ShakeMapDto> cache = new ConcurrentHashMap<>();
    private static final int CACHE_MAX = 200;

    public record ShakeMapDto(
            Double maxMmi,
            Double maxPga,
            Double maxPgv,
            Double maxPsa03,
            Double maxPsa10,
            Double maxPsa30,
            String mapStatus,
            String reviewStatus,
            String processTime,
            String shakeMapUrl,
            String intensityMapUrl
    ) {}

    public ShakeMapDto fetchShakeMap(String eventId) {
        if (cache.containsKey(eventId)) {
            return cache.get(eventId);
        }

        String url = String.format(USGS_DETAIL_URL, eventId);
        try {
            HttpRequest req = HttpRequest.newBuilder()
                    .uri(URI.create(url))
                    .timeout(Duration.ofSeconds(15))
                    .header("Accept", "application/json")
                    .header("User-Agent", "DepremRehberim/1.0")
                    .GET()
                    .build();

            HttpResponse<String> res = http.send(req, HttpResponse.BodyHandlers.ofString(StandardCharsets.UTF_8));
            if (res.statusCode() < 200 || res.statusCode() >= 300) {
                return cacheAndReturn(eventId, null);
            }

            JsonNode root = mapper.readTree(res.body());
            JsonNode products = root.path("properties").path("products");
            JsonNode shakeMapArr = products.path("shakemap");

            if (shakeMapArr.isMissingNode() || !shakeMapArr.isArray() || shakeMapArr.isEmpty()) {
                return cacheAndReturn(eventId, null);
            }

            // Use the first (most recent) ShakeMap product
            JsonNode sm = shakeMapArr.get(0);
            JsonNode props = sm.path("properties");

            Double maxMmi    = doubleOrNull(props, "maxmmi");
            Double maxPga    = doubleOrNull(props, "maxpga");
            Double maxPgv    = doubleOrNull(props, "maxpgv");
            Double maxPsa03  = doubleOrNull(props, "maxpsa03");
            Double maxPsa10  = doubleOrNull(props, "maxpsa10");
            Double maxPsa30  = doubleOrNull(props, "maxpsa30");
            String mapStatus = textOrNull(props, "map-status");
            String reviewStatus = textOrNull(props, "review-status");
            String processTime  = textOrNull(props, "process-timestamp");

            // Intensity overlay image URL from contents
            JsonNode contents = sm.path("contents");
            String intensityMapUrl = extractIntensityUrl(contents);
            String shakeMapUrl = String.format(SHAKEMAP_PAGE_URL, eventId);

            ShakeMapDto dto = new ShakeMapDto(
                    maxMmi, maxPga, maxPgv, maxPsa03, maxPsa10, maxPsa30,
                    mapStatus, reviewStatus, processTime,
                    shakeMapUrl, intensityMapUrl
            );
            return cacheAndReturn(eventId, dto);

        } catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
            return null;
        } catch (Exception ex) {
            return null;
        }
    }

    private String extractIntensityUrl(JsonNode contents) {
        // Try preferred intensity image formats in order
        String[] candidates = {
            "download/intensity.jpg",
            "download/intensity.png",
            "download/pga.jpg",
            "download/pga.png",
        };
        for (String key : candidates) {
            JsonNode node = contents.path(key);
            if (!node.isMissingNode()) {
                String url = node.path("url").asText(null);
                if (url != null && !url.isBlank()) return url;
            }
        }
        return null;
    }

    private Double doubleOrNull(JsonNode node, String field) {
        JsonNode v = node.path(field);
        if (v.isMissingNode() || v.isNull()) return null;
        try { return Double.parseDouble(v.asText()); } catch (Exception e) { return null; }
    }

    private String textOrNull(JsonNode node, String field) {
        JsonNode v = node.path(field);
        if (v.isMissingNode() || v.isNull()) return null;
        String s = v.asText("").trim();
        return s.isEmpty() ? null : s;
    }

    private ShakeMapDto cacheAndReturn(String eventId, ShakeMapDto dto) {
        if (cache.size() < CACHE_MAX) {
            cache.put(eventId, dto);
        }
        return dto;
    }
}
