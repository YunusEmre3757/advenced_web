package com.example.backend.earthquake;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.time.Instant;
import java.time.temporal.ChronoUnit;
import java.util.ArrayList;
import java.util.List;

@Service
public class HistoricalEarthquakeService {

    private final ObjectMapper mapper = new ObjectMapper();
    private final HttpClient http = HttpClient.newBuilder()
            .followRedirects(HttpClient.Redirect.NORMAL)
            .connectTimeout(Duration.ofSeconds(10))
            .build();

    @Value("${earthquake.usgs.fdsn-url:https://earthquake.usgs.gov/fdsnws/event/1/query}")
    private String usgsFdsnUrl;

    @Value("${earthquake.turkey.min-lat:35.0}")
    private double minLat;
    @Value("${earthquake.turkey.max-lat:43.0}")
    private double maxLat;
    @Value("${earthquake.turkey.min-lon:25.0}")
    private double minLon;
    @Value("${earthquake.turkey.max-lon:45.0}")
    private double maxLon;

    private volatile List<HistoricalEvent> cache = List.of();
    private volatile Instant cacheExpires = Instant.EPOCH;
    private volatile CacheKey cacheKey = null;

    public List<HistoricalEvent> fetch(int years, double minMagnitude) {
        CacheKey key = new CacheKey(years, minMagnitude);
        Instant now = Instant.now();
        if (cacheKey != null && cacheKey.equals(key) && now.isBefore(cacheExpires) && !cache.isEmpty()) {
            return cache;
        }
        Instant end = Instant.now();
        Instant start = end.minus(years * 365L, ChronoUnit.DAYS);
        String url = usgsFdsnUrl + "?format=geojson"
                + "&starttime=" + start
                + "&endtime=" + end
                + "&minlatitude=" + minLat
                + "&maxlatitude=" + maxLat
                + "&minlongitude=" + minLon
                + "&maxlongitude=" + maxLon
                + "&minmagnitude=" + minMagnitude
                + "&orderby=time-asc"
                + "&limit=20000";
        try {
            HttpRequest req = HttpRequest.newBuilder()
                    .uri(URI.create(url))
                    .timeout(Duration.ofSeconds(25))
                    .header("Accept", "application/json")
                    .header("User-Agent", "DepremRehberim/1.0")
                    .GET()
                    .build();
            HttpResponse<String> res = http.send(req, HttpResponse.BodyHandlers.ofString(StandardCharsets.UTF_8));
            if (res.statusCode() < 200 || res.statusCode() >= 300) return cache;
            JsonNode root = mapper.readTree(res.body());
            JsonNode features = root.path("features");
            List<HistoricalEvent> out = new ArrayList<>();
            if (features.isArray()) {
                for (JsonNode f : features) {
                    JsonNode props = f.path("properties");
                    JsonNode coords = f.path("geometry").path("coordinates");
                    if (!coords.isArray() || coords.size() < 2) continue;
                    double lon = coords.get(0).asDouble();
                    double lat = coords.get(1).asDouble();
                    double depth = coords.size() > 2 ? coords.get(2).asDouble() : 0.0;
                    double mag = props.path("mag").asDouble();
                    long timeMs = props.path("time").asLong();
                    String place = props.path("place").asText("");
                    String id = f.path("id").asText("");
                    out.add(new HistoricalEvent(id, Instant.ofEpochMilli(timeMs), place, mag, lat, lon, depth));
                }
            }
            cache = out;
            cacheKey = key;
            cacheExpires = now.plusSeconds(3600);
            return out;
        } catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
            return cache;
        } catch (Exception ex) {
            return cache;
        }
    }

    public List<SeismicGap> computeGaps(List<HistoricalEvent> events, int gridSize, int silentYears, double gapMagnitude) {
        double latStep = (maxLat - minLat) / gridSize;
        double lonStep = (maxLon - minLon) / gridSize;
        Instant cutoff = Instant.now().minus(silentYears * 365L, ChronoUnit.DAYS);

        List<SeismicGap> gaps = new ArrayList<>();
        for (int i = 0; i < gridSize; i++) {
            for (int j = 0; j < gridSize; j++) {
                double cellMinLat = minLat + i * latStep;
                double cellMaxLat = cellMinLat + latStep;
                double cellMinLon = minLon + j * lonStep;
                double cellMaxLon = cellMinLon + lonStep;

                boolean hadBigOlder = false;
                boolean recentBig = false;
                for (HistoricalEvent e : events) {
                    if (e.latitude() < cellMinLat || e.latitude() >= cellMaxLat) continue;
                    if (e.longitude() < cellMinLon || e.longitude() >= cellMaxLon) continue;
                    if (e.magnitude() < gapMagnitude) continue;
                    if (e.time().isBefore(cutoff)) {
                        hadBigOlder = true;
                    } else {
                        recentBig = true;
                    }
                }
                if (hadBigOlder && !recentBig) {
                    gaps.add(new SeismicGap(
                            (cellMinLat + cellMaxLat) / 2,
                            (cellMinLon + cellMaxLon) / 2,
                            latStep,
                            lonStep,
                            silentYears,
                            gapMagnitude
                    ));
                }
            }
        }
        return gaps;
    }

    public record HistoricalEvent(
            String id,
            Instant time,
            String place,
            double magnitude,
            double latitude,
            double longitude,
            double depthKm
    ) {
    }

    public record SeismicGap(
            double centerLat,
            double centerLon,
            double latSpan,
            double lonSpan,
            int silentYears,
            double magnitudeThreshold
    ) {
    }

    private record CacheKey(int years, double minMagnitude) {
    }
}
