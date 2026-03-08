package com.example.backend.earthquake;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.web.server.ResponseStatusException;

import java.io.IOException;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.Charset;
import java.time.Instant;
import java.time.LocalDateTime;
import java.time.ZoneId;
import java.time.temporal.ChronoUnit;
import java.time.format.DateTimeFormatter;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

@Service
public class EarthquakeService {

    private static final Pattern KANDILLI_LINE_PATTERN = Pattern.compile(
            "^(\\d{4}\\.\\d{2}\\.\\d{2})\\s+(\\d{2}:\\d{2}:\\d{2})\\s+" +
                    "(-?\\d+(?:\\.\\d+)?)\\s+(-?\\d+(?:\\.\\d+)?)\\s+(-?\\d+(?:\\.\\d+)?)\\s+" +
                    "([\\d.-]+)\\s+([\\d.-]+)\\s+([\\d.-]+)\\s+(.*)$"
    );
    private static final DateTimeFormatter KANDILLI_TIME_FORMAT =
            DateTimeFormatter.ofPattern("yyyy.MM.dd HH:mm:ss");
    private static final ZoneId TURKEY_ZONE = ZoneId.of("Europe/Istanbul");
    private static final Charset KANDILLI_CHARSET = Charset.forName("windows-1254");

    private final HttpClient httpClient = HttpClient.newBuilder()
            .followRedirects(HttpClient.Redirect.NORMAL)
            .build();
    private volatile CacheKey cacheKey = null;
    private volatile Instant cacheExpiresAt = Instant.EPOCH;
    private volatile List<EarthquakeDto> cachedData = List.of();

    @Value("${earthquake.kandilli.base-url:http://www.koeri.boun.edu.tr/scripts/lst9.asp}")
    private String kandilliBaseUrl;

    @Value("${earthquake.turkey.min-lat:35.0}")
    private double minLatitude;

    @Value("${earthquake.turkey.max-lat:43.0}")
    private double maxLatitude;

    @Value("${earthquake.turkey.min-lon:25.0}")
    private double minLongitude;

    @Value("${earthquake.turkey.max-lon:45.0}")
    private double maxLongitude;

    public List<EarthquakeDto> fetchRecentTurkeyEarthquakes(int hours, double minMagnitude, int limit) {
        CacheKey currentKey = new CacheKey(hours, minMagnitude, limit);
        Instant now = Instant.now();
        if (cacheKey != null && cacheKey.equals(currentKey) && now.isBefore(cacheExpiresAt) && !cachedData.isEmpty()) {
            return cachedData;
        }

        Instant start = Instant.now().truncatedTo(ChronoUnit.SECONDS).minus(hours, ChronoUnit.HOURS);

        String alternateUrl = swapScheme(kandilliBaseUrl);
        List<String> candidateUrls = new ArrayList<>();
        candidateUrls.add(kandilliBaseUrl);
        if (alternateUrl != null && !alternateUrl.equals(kandilliBaseUrl)) {
            candidateUrls.add(alternateUrl);
        }

        ResponseStatusException lastStatusError = null;
        IOException lastIoError = null;
        try {
            for (String url : candidateUrls) {
                HttpRequest request = HttpRequest.newBuilder()
                        .uri(URI.create(url))
                        .timeout(java.time.Duration.ofSeconds(20))
                        .header("Accept", "text/plain, text/html")
                        .header("User-Agent", "DepremRehberim/1.0 (+https://localhost)")
                        .header("Accept-Language", "tr-TR,tr;q=0.9,en-US;q=0.8,en;q=0.7")
                        .GET()
                        .build();

                try {
                    HttpResponse<byte[]> response = httpClient.send(request, HttpResponse.BodyHandlers.ofByteArray());
                    if (response.statusCode() < 200 || response.statusCode() >= 300) {
                        lastStatusError = new ResponseStatusException(
                                HttpStatus.BAD_GATEWAY,
                                "Kandilli service returned " + response.statusCode()
                        );
                        continue;
                    }

                    String content = new String(response.body(), KANDILLI_CHARSET);
                    List<EarthquakeDto> data = parseKandilli(content, start, minMagnitude, limit);
                    if (data.isEmpty()) {
                        lastStatusError = new ResponseStatusException(
                                HttpStatus.BAD_GATEWAY,
                                "Kandilli returned empty or unparseable data"
                        );
                        continue;
                    }
                    cachedData = data;
                    cacheKey = currentKey;
                    cacheExpiresAt = now.plusSeconds(30);
                    return data;
                } catch (IOException ioEx) {
                    lastIoError = ioEx;
                }
            }
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            throw new ResponseStatusException(
                    HttpStatus.SERVICE_UNAVAILABLE,
                    "Kandilli request interrupted",
                    e
            );
        }

        if (lastStatusError != null) {
            throw lastStatusError;
        }

        throw new ResponseStatusException(
                HttpStatus.SERVICE_UNAVAILABLE,
                "Could not connect to Kandilli service",
                lastIoError
        );
    }

    private List<EarthquakeDto> parseKandilli(String content, Instant start, double minMagnitude, int limit) {
        String normalized = content.replace("&nbsp;", " ");
        String[] lines = normalized.split("\\r?\\n");
        List<EarthquakeDto> earthquakes = new ArrayList<>();

        for (String rawLine : lines) {
            String line = rawLine.trim();
            Matcher matcher = KANDILLI_LINE_PATTERN.matcher(line);
            if (!matcher.matches()) {
                continue;
            }

            double latitude = parseDoubleSafe(matcher.group(3));
            double longitude = parseDoubleSafe(matcher.group(4));
            double depth = parseDoubleSafe(matcher.group(5));

            double md = parseMagnitudeSafe(matcher.group(6));
            double ml = parseMagnitudeSafe(matcher.group(7));
            double mw = parseMagnitudeSafe(matcher.group(8));
            double magnitude = pickMagnitude(mw, ml, md);

            if (!isInsideTurkey(latitude, longitude) || magnitude < minMagnitude) {
                continue;
            }

            String location = matcher.group(9).replaceAll("\\s{2,}", " ").trim();
            LocalDateTime localDateTime = LocalDateTime.parse(
                    matcher.group(1) + " " + matcher.group(2),
                    KANDILLI_TIME_FORMAT
            );
            Instant time = localDateTime.atZone(TURKEY_ZONE).toInstant();
            if (time.isBefore(start)) {
                continue;
            }

            String id = matcher.group(1).replace(".", "") + "-" +
                    matcher.group(2).replace(":", "") + "-" +
                    Math.round(latitude * 1000) + "-" + Math.round(longitude * 1000);

            earthquakes.add(new EarthquakeDto(
                    id,
                    time,
                    location,
                    latitude,
                    longitude,
                    magnitude,
                    depth
            ));
        }

        earthquakes.sort(Comparator.comparing(EarthquakeDto::time).reversed());
        if (earthquakes.size() > limit) {
            return new ArrayList<>(earthquakes.subList(0, limit));
        }
        return earthquakes;
    }

    private double pickMagnitude(double mw, double ml, double md) {
        if (mw >= 0) return mw;
        if (ml >= 0) return ml;
        if (md >= 0) return md;
        return 0.0;
    }

    private double parseMagnitudeSafe(String value) {
        if (value == null) return -1;
        String cleaned = value.trim();
        if (cleaned.isEmpty() || cleaned.equals("-.-")) return -1;
        return parseDoubleSafe(cleaned);
    }

    private double parseDoubleSafe(String value) {
        try {
            return Double.parseDouble(value.trim().replace(",", "."));
        } catch (Exception ex) {
            return 0.0;
        }
    }

    private boolean isInsideTurkey(double latitude, double longitude) {
        return latitude >= minLatitude && latitude <= maxLatitude &&
                longitude >= minLongitude && longitude <= maxLongitude;
    }

    private String swapScheme(String url) {
        if (url == null) return null;
        if (url.startsWith("https://")) return "http://" + url.substring("https://".length());
        if (url.startsWith("http://")) return "https://" + url.substring("http://".length());
        return null;
    }

    private record CacheKey(int hours, double minMagnitude, int limit) {
    }
}
