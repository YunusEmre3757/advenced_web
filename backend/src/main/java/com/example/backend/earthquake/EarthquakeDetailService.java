package com.example.backend.earthquake;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.web.server.ResponseStatusException;

import java.net.URI;
import java.net.URLEncoder;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.time.Instant;
import java.time.temporal.ChronoUnit;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;

@Service
public class EarthquakeDetailService {

    private static final double EARTH_RADIUS_KM = 6371.0;

    private final EarthquakeService earthquakeService;
    private final ObjectMapper mapper = new ObjectMapper();
    private final HttpClient http = HttpClient.newBuilder()
            .followRedirects(HttpClient.Redirect.NORMAL)
            .connectTimeout(Duration.ofSeconds(10))
            .build();

    @Value("${earthquake.usgs.fdsn-url:https://earthquake.usgs.gov/fdsnws/event/1/query}")
    private String usgsFdsnUrl;

    @Value("${earthquake.detail.aftershock-radius-km:75.0}")
    private double aftershockRadiusKm;

    @Value("${earthquake.detail.aftershock-window-hours:72}")
    private int aftershockWindowHours;

    @Value("${earthquake.detail.similar-radius-km:150.0}")
    private double similarRadiusKm;

    @Value("${earthquake.detail.similar-magnitude-delta:0.8}")
    private double similarMagnitudeDelta;

    @Value("${earthquake.detail.similar-years:25}")
    private int similarYears;

    public EarthquakeDetailService(EarthquakeService earthquakeService) {
        this.earthquakeService = earthquakeService;
    }

    public EarthquakeDto findById(String eventId) {
        List<EarthquakeDto> pool = earthquakeService.fetchRecentTurkeyEarthquakes(168, 0.0, 500);
        return pool.stream()
                .filter(e -> e.id().equals(eventId))
                .findFirst()
                .orElseThrow(() -> new ResponseStatusException(HttpStatus.NOT_FOUND, "Olay bulunamadi: " + eventId));
    }

    public List<EarthquakeDto> aftershocks(EarthquakeDto base, int limit) {
        List<EarthquakeDto> pool = earthquakeService.fetchRecentTurkeyEarthquakes(
                Math.max(aftershockWindowHours, 24), 0.0, 500);
        Instant windowEnd = base.time().plus(aftershockWindowHours, ChronoUnit.HOURS);
        List<EarthquakeDto> out = new ArrayList<>();
        for (EarthquakeDto e : pool) {
            if (e.id().equals(base.id())) continue;
            if (!e.time().isAfter(base.time())) continue;
            if (e.time().isAfter(windowEnd)) continue;
            if (haversineKm(base.latitude(), base.longitude(), e.latitude(), e.longitude()) > aftershockRadiusKm) continue;
            out.add(e);
        }
        out.sort(Comparator.comparing(EarthquakeDto::time));
        if (out.size() > limit) return new ArrayList<>(out.subList(0, limit));
        return out;
    }

    public List<EarthquakeDetailDto.HistoricalMatch> similarHistorical(EarthquakeDto base, int limit) {
        Instant endTime = base.time().minus(1, ChronoUnit.DAYS);
        Instant startTime = endTime.minus(similarYears * 365L, ChronoUnit.DAYS);
        double minMag = Math.max(base.magnitude() - similarMagnitudeDelta, 3.0);
        double maxMag = base.magnitude() + similarMagnitudeDelta;

        StringBuilder url = new StringBuilder(usgsFdsnUrl);
        url.append("?format=geojson")
                .append("&starttime=").append(startTime.toString())
                .append("&endtime=").append(endTime.toString())
                .append("&latitude=").append(base.latitude())
                .append("&longitude=").append(base.longitude())
                .append("&maxradiuskm=").append(similarRadiusKm)
                .append("&minmagnitude=").append(minMag)
                .append("&maxmagnitude=").append(maxMag)
                .append("&orderby=magnitude")
                .append("&limit=").append(Math.max(limit * 3, 30));

        try {
            HttpRequest req = HttpRequest.newBuilder()
                    .uri(URI.create(url.toString()))
                    .timeout(Duration.ofSeconds(15))
                    .header("Accept", "application/json")
                    .header("User-Agent", "DepremRehberim/1.0")
                    .GET()
                    .build();
            HttpResponse<String> res = http.send(req, HttpResponse.BodyHandlers.ofString(StandardCharsets.UTF_8));
            if (res.statusCode() < 200 || res.statusCode() >= 300) {
                return List.of();
            }
            JsonNode root = mapper.readTree(res.body());
            JsonNode features = root.path("features");
            List<EarthquakeDetailDto.HistoricalMatch> matches = new ArrayList<>();
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
                    double distanceKm = haversineKm(base.latitude(), base.longitude(), lat, lon);
                    double magDelta = Math.abs(mag - base.magnitude());
                    matches.add(new EarthquakeDetailDto.HistoricalMatch(
                            id,
                            Instant.ofEpochMilli(timeMs),
                            place,
                            mag,
                            lat,
                            lon,
                            depth,
                            distanceKm,
                            magDelta
                    ));
                }
            }
            matches.sort(Comparator
                    .comparingDouble(EarthquakeDetailDto.HistoricalMatch::magnitudeDelta)
                    .thenComparingDouble(EarthquakeDetailDto.HistoricalMatch::distanceKm));
            if (matches.size() > limit) return new ArrayList<>(matches.subList(0, limit));
            return matches;
        } catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
            return List.of();
        } catch (Exception ex) {
            return List.of();
        }
    }

    public EarthquakeDetailDto.DyfiSummary dyfi(EarthquakeDto base) {
        Instant start = base.time().minus(5, ChronoUnit.MINUTES);
        Instant end = base.time().plus(5, ChronoUnit.MINUTES);
        String url = usgsFdsnUrl + "?format=geojson"
                + "&starttime=" + start
                + "&endtime=" + end
                + "&latitude=" + base.latitude()
                + "&longitude=" + base.longitude()
                + "&maxradiuskm=50"
                + "&producttype=dyfi"
                + "&limit=1";
        try {
            HttpRequest req = HttpRequest.newBuilder()
                    .uri(URI.create(url))
                    .timeout(Duration.ofSeconds(10))
                    .header("Accept", "application/json")
                    .header("User-Agent", "DepremRehberim/1.0")
                    .GET()
                    .build();
            HttpResponse<String> res = http.send(req, HttpResponse.BodyHandlers.ofString(StandardCharsets.UTF_8));
            if (res.statusCode() < 200 || res.statusCode() >= 300) return null;
            JsonNode root = mapper.readTree(res.body());
            JsonNode feature = root.path("features").path(0);
            if (feature.isMissingNode()) return null;
            JsonNode props = feature.path("properties");
            Integer responses = props.has("felt") && !props.path("felt").isNull()
                    ? props.path("felt").asInt() : null;
            Double cdi = props.has("cdi") && !props.path("cdi").isNull()
                    ? props.path("cdi").asDouble() : null;
            String detailUrl = props.path("url").asText(null);
            if (responses == null && cdi == null) return null;
            return new EarthquakeDetailDto.DyfiSummary(responses, cdi, detailUrl);
        } catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
            return null;
        } catch (Exception ex) {
            return null;
        }
    }

    private double haversineKm(double lat1, double lon1, double lat2, double lon2) {
        double dLat = Math.toRadians(lat2 - lat1);
        double dLon = Math.toRadians(lon2 - lon1);
        double a = Math.sin(dLat / 2) * Math.sin(dLat / 2)
                + Math.cos(Math.toRadians(lat1)) * Math.cos(Math.toRadians(lat2))
                * Math.sin(dLon / 2) * Math.sin(dLon / 2);
        return EARTH_RADIUS_KM * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
    }

    @SuppressWarnings("unused")
    private static String urlEncode(String s) {
        return URLEncoder.encode(s, StandardCharsets.UTF_8);
    }
}
