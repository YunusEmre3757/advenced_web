package com.example.backend.ai;

import com.example.backend.earthquake.EarthquakeDto;
import com.example.backend.earthquake.EarthquakeService;
import com.example.backend.fault.FaultLineService;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.web.server.ResponseStatusException;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.ObjectMapper;
import tools.jackson.databind.node.ArrayNode;
import tools.jackson.databind.node.ObjectNode;

import java.io.IOException;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;
import java.time.ZoneId;
import java.time.format.DateTimeFormatter;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Locale;
import java.util.Optional;

@Service
public class GroqAiService {

    private static final ZoneId TURKEY_ZONE = ZoneId.of("Europe/Istanbul");
    private static final DateTimeFormatter TIME_FMT = DateTimeFormatter.ofPattern("dd.MM.yyyy HH:mm", Locale.US);

    private final ObjectMapper objectMapper;
    private final EarthquakeService earthquakeService;
    private final FaultLineService faultLineService;
    private final HttpClient httpClient = HttpClient.newBuilder().build();

    @Value("${ai.groq.api-url:https://api.groq.com/openai/v1/chat/completions}")
    private String groqApiUrl;

    @Value("${ai.groq.model:llama-3.3-70b-versatile}")
    private String groqModel;

    @Value("${ai.groq.api-key:}")
    private String groqApiKey;

    @Value("${ai.groq.timeout-seconds:25}")
    private int groqTimeoutSeconds;

    @Value("${ai.groq.temperature:0.2}")
    private double groqTemperature;

    @Value("${ai.groq.max-tokens:700}")
    private int groqMaxTokens;

    public GroqAiService(
            ObjectMapper objectMapper,
            EarthquakeService earthquakeService,
            FaultLineService faultLineService
    ) {
        this.objectMapper = objectMapper;
        this.earthquakeService = earthquakeService;
        this.faultLineService = faultLineService;
    }

    public AiChatResponse chat(AiChatRequest request) {
        if (request == null || request.question() == null || request.question().isBlank()) {
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "question is required");
        }

        int hours = clampInt(nvl(request.hours(), 24), 1, 168);
        double minMagnitude = clamp(nvl(request.minMagnitude(), 1.0), 0.0, 10.0);
        int limit = clampInt(nvl(request.limit(), 250), 1, 500);

        List<EarthquakeDto> recent = earthquakeService.fetchRecentTurkeyEarthquakes(hours, minMagnitude, limit);
        BBox bbox = parseBBox(request.bbox()).orElse(null);
        List<EarthquakeDto> scoped = bbox != null ? filterByBBox(recent, bbox) : recent;
        if (scoped.isEmpty()) scoped = recent;

        EarthquakeDto focus = selectFocusEvent(scoped, request.eventId(), request.latitude(), request.longitude())
                .orElse(scoped.isEmpty() ? null : scoped.get(0));
        FaultAnalysis faultAnalysis = analyzeFaults(focus, bbox, scoped);
        FaultMatch nearestFault = faultAnalysis != null ? faultAnalysis.nearestFault : null;

        if (groqApiKey == null || groqApiKey.isBlank()) {
            String fallback = buildFallbackAnswer(request.question(), scoped, focus, faultAnalysis);
            return toResponse(fallback, "local-fallback", scoped, focus, nearestFault,
                    "GROQ_API_KEY tanimli degil. Cevap yerel fallback ile uretildi.");
        }

        String context = buildAiContext(request.question(), scoped, focus, faultAnalysis, hours, minMagnitude, bbox);
        try {
            String answer = callGroq(context, request.question());
            return toResponse(answer, groqModel, scoped, focus, nearestFault, null);
        } catch (Exception ex) {
            String fallback = buildFallbackAnswer(request.question(), scoped, focus, faultAnalysis);
            return toResponse(
                    fallback,
                    "local-fallback",
                    scoped,
                    focus,
                    nearestFault,
                    "Groq erisimi basarisiz oldu, fallback kullanildi: " + ex.getMessage()
            );
        }
    }

    private AiChatResponse toResponse(
            String answer,
            String model,
            List<EarthquakeDto> scoped,
            EarthquakeDto focus,
            FaultMatch nearestFault,
            String note
    ) {
        return new AiChatResponse(
                answer,
                model,
                scoped.size(),
                focus != null ? focus.id() : null,
                focus != null ? focus.location() : null,
                focus != null ? round2(focus.magnitude()) : null,
                focus != null ? round2(focus.depthKm()) : null,
                nearestFault != null ? round2(nearestFault.distanceKm) : null,
                nearestFault != null ? nearestFault.summary : null,
                note
        );
    }

    private String callGroq(String context, String question) throws IOException, InterruptedException {
        ObjectNode payload = objectMapper.createObjectNode();
        payload.put("model", groqModel);
        payload.put("temperature", clamp(groqTemperature, 0.0, 1.0));
        payload.put("max_tokens", clampInt(groqMaxTokens, 128, 2048));

        ArrayNode messages = objectMapper.createArrayNode();

        ObjectNode system = objectMapper.createObjectNode();
        system.put("role", "system");
        system.put(
                "content",
                """
                Sen deprem bilgi asistanisin. Turkce, net ve sakin bir dille yanit ver.
                Asla deprem zamani/buyuklugu tahmini yapma.
                Cevabi yalnizca verilen veri baglamina dayandir.
                Bilgi yetersizse acikca belirt.
                Kullanici deprem-fay iliskisi, odak depremin hangi faya yakin oldugu,
                fayin kayma tipi/hareket gecmisi/hiz bilgisi gibi detaylari sorabilir.
                "Hangi fay ustunde?" sorusunda kesinlik iddiasi yapma; mesafeye dayali
                olasilikli yorum yap ve belirsizligi acikca belirt.
                """
        );
        messages.add(system);

        ObjectNode user = objectMapper.createObjectNode();
        user.put("role", "user");
        user.put("content", "Veri baglami:\n" + context + "\n\nSoru:\n" + question);
        messages.add(user);

        payload.set("messages", messages);

        HttpRequest httpRequest = HttpRequest.newBuilder()
                .uri(URI.create(groqApiUrl))
                .timeout(Duration.ofSeconds(clampInt(groqTimeoutSeconds, 5, 90)))
                .header("Authorization", "Bearer " + groqApiKey)
                .header("Content-Type", "application/json")
                .POST(HttpRequest.BodyPublishers.ofString(payload.toString()))
                .build();

        HttpResponse<String> response = httpClient.send(httpRequest, HttpResponse.BodyHandlers.ofString());
        if (response.statusCode() < 200 || response.statusCode() >= 300) {
            throw new ResponseStatusException(HttpStatus.BAD_GATEWAY, "Groq API status " + response.statusCode());
        }

        JsonNode root = objectMapper.readTree(response.body());
        String content = root.path("choices").path(0).path("message").path("content").asText("").trim();
        if (content.isBlank()) {
            throw new ResponseStatusException(HttpStatus.BAD_GATEWAY, "Groq bos cevap dondu");
        }
        return content;
    }

    private String buildFallbackAnswer(
            String question,
            List<EarthquakeDto> scoped,
            EarthquakeDto focus,
            FaultAnalysis faultAnalysis
    ) {
        if (scoped.isEmpty()) {
            return "Bu sorgu icin deprem verisi bulunamadi. Zaman araligi veya filtreyi genisletin.";
        }

        StringBuilder sb = new StringBuilder();
        sb.append("Sorun anlasildi: ").append(question).append("\n");
        sb.append("Son veriye gore ").append(scoped.size()).append(" olay bulundu.\n");

        if (focus != null) {
            sb.append("Odak deprem: ")
                    .append(focus.location())
                    .append(" | M")
                    .append(round2(focus.magnitude()))
                    .append(" | ")
                    .append(round2(focus.depthKm()))
                    .append(" km\n");
        }

        FaultMatch nearestFault = faultAnalysis != null ? faultAnalysis.nearestFault : null;
        if (nearestFault != null) {
            sb.append("En yakin fay: ")
                    .append(nearestFault.summary)
                    .append(" (yaklasik ")
                    .append(round2(nearestFault.distanceKm))
                    .append(" km, ")
                    .append(distanceBand(nearestFault.distanceKm))
                    .append(")\n");
        } else {
            sb.append("Bu odak icin yakin fay eslesmesi bulunamadi.\n");
        }

        if (faultAnalysis != null && !faultAnalysis.focusCandidates.isEmpty()) {
            sb.append("Odaga en yakin aday faylar:\n");
            faultAnalysis.focusCandidates.stream().limit(3).forEach(c ->
                    sb.append("- ")
                            .append(c.summary)
                            .append(" | ")
                            .append(round2(c.distanceKm))
                            .append(" km")
                            .append(c.detail != null && !c.detail.isBlank() ? " | " + c.detail : "")
                            .append("\n")
            );
        }

        if (faultAnalysis != null && !faultAnalysis.activityRows.isEmpty()) {
            sb.append("Son olaylara gore fay aktivite ozeti (yaklasik):\n");
            faultAnalysis.activityRows.stream().limit(4).forEach(r ->
                    sb.append("- ")
                            .append(r.summary)
                            .append(": ")
                            .append(r.eventCount)
                            .append(" olay | max M")
                            .append(round2(r.maxMagnitude))
                            .append(" | ort mesafe ")
                            .append(round2(r.avgDistanceKm))
                            .append(" km\n")
            );
        }

        sb.append("Not: Deprem noktasi fay cizgisinin birebir ustunde gorunmeyebilir; konum belirsizligi ve derinlik etkisi normaldir.");
        return sb.toString();
    }

    private String buildAiContext(
            String question,
            List<EarthquakeDto> scoped,
            EarthquakeDto focus,
            FaultAnalysis faultAnalysis,
            int hours,
            double minMagnitude,
            BBox bbox
    ) {
        StringBuilder sb = new StringBuilder();
        sb.append("Sorgu penceresi: son ").append(hours).append(" saat\n");
        sb.append("Min buyukluk filtresi: M").append(round2(minMagnitude)).append("\n");
        sb.append("Toplam olay: ").append(scoped.size()).append("\n");

        if (bbox != null) {
            sb.append("Harita BBOX: ")
                    .append(round3(bbox.minLon)).append(",")
                    .append(round3(bbox.minLat)).append(",")
                    .append(round3(bbox.maxLon)).append(",")
                    .append(round3(bbox.maxLat)).append("\n");
        }

        if (!scoped.isEmpty()) {
            double maxMag = scoped.stream().mapToDouble(EarthquakeDto::magnitude).max().orElse(0);
            double avgMag = scoped.stream().mapToDouble(EarthquakeDto::magnitude).average().orElse(0);
            sb.append("Max buyukluk: M").append(round2(maxMag)).append("\n");
            sb.append("Ortalama buyukluk: M").append(round2(avgMag)).append("\n");
        }

        if (focus != null) {
            sb.append("Odak deprem:\n");
            sb.append("- id: ").append(focus.id()).append("\n");
            sb.append("- zaman: ").append(TIME_FMT.format(focus.time().atZone(TURKEY_ZONE))).append("\n");
            sb.append("- lokasyon: ").append(focus.location()).append("\n");
            sb.append("- koordinat: ").append(round4(focus.longitude())).append(", ").append(round4(focus.latitude())).append("\n");
            sb.append("- buyukluk: M").append(round2(focus.magnitude())).append("\n");
            sb.append("- derinlik: ").append(round2(focus.depthKm())).append(" km\n");
        }

        FaultMatch nearestFault = faultAnalysis != null ? faultAnalysis.nearestFault : null;
        if (nearestFault != null) {
            sb.append("Fay eslesmesi:\n");
            sb.append("- en yakin fay mesafesi: ").append(round2(nearestFault.distanceKm)).append(" km\n");
            sb.append("- fay ozeti: ").append(nearestFault.summary).append("\n");
            sb.append("- yorum: odak deprem faya ").append(distanceBand(nearestFault.distanceKm)).append("\n");
        }

        if (faultAnalysis != null) {
            sb.append("Penceredeki toplam fay segmenti: ").append(faultAnalysis.faultCount).append("\n");

            if (!faultAnalysis.focusCandidates.isEmpty()) {
                sb.append("Odaga en yakin aday faylar (ilk 4):\n");
                faultAnalysis.focusCandidates.stream().limit(4).forEach(c ->
                        sb.append("- ")
                                .append(c.summary)
                                .append(" | ")
                                .append(round2(c.distanceKm))
                                .append(" km")
                                .append(c.detail != null && !c.detail.isBlank() ? " | " + c.detail : "")
                                .append("\n")
                );
            }

            if (!faultAnalysis.activityRows.isEmpty()) {
                sb.append("Deprem-fay aktivite ozeti (yaklasik, 35 km esik):\n");
                faultAnalysis.activityRows.stream().limit(6).forEach(r ->
                        sb.append("- ")
                                .append(r.summary)
                                .append(" | olay: ")
                                .append(r.eventCount)
                                .append(" | max M")
                                .append(round2(r.maxMagnitude))
                                .append(" | ort mesafe ")
                                .append(round2(r.avgDistanceKm))
                                .append(" km\n")
                );
            }
        }

        sb.append("Son olaylar (ilk 12):\n");
        List<EarthquakeDto> top = scoped.stream().limit(12).toList();
        for (EarthquakeDto e : top) {
            sb.append("- ")
                    .append(TIME_FMT.format(e.time().atZone(TURKEY_ZONE)))
                    .append(" | M").append(round2(e.magnitude()))
                    .append(" | ").append(round2(e.depthKm())).append(" km | ")
                    .append(e.location())
                    .append("\n");
        }

        sb.append("Kural: tahmin yapma, yalnizca veri tabanli yorum yap.");
        return sb.toString();
    }

    private Optional<EarthquakeDto> selectFocusEvent(
            List<EarthquakeDto> scoped,
            String eventId,
            Double latitude,
            Double longitude
    ) {
        if (scoped == null || scoped.isEmpty()) return Optional.empty();

        if (eventId != null && !eventId.isBlank()) {
            Optional<EarthquakeDto> byId = scoped.stream()
                    .filter(e -> eventId.equalsIgnoreCase(e.id()))
                    .findFirst();
            if (byId.isPresent()) return byId;
        }

        if (latitude != null && longitude != null && Double.isFinite(latitude) && Double.isFinite(longitude)) {
            return scoped.stream()
                    .min(Comparator.comparingDouble(e -> haversineKm(latitude, longitude, e.latitude(), e.longitude())));
        }

        return scoped.stream()
                .sorted(Comparator.comparingDouble(EarthquakeDto::magnitude).reversed()
                        .thenComparing(EarthquakeDto::time).reversed())
                .findFirst();
    }

    private FaultAnalysis analyzeFaults(EarthquakeDto focus, BBox preferredBBox, List<EarthquakeDto> scoped) {
        if (focus == null) return null;

        BBox bbox = preferredBBox != null
                ? preferredBBox
                : new BBox(
                focus.longitude() - 2.2,
                focus.latitude() - 2.2,
                focus.longitude() + 2.2,
                focus.latitude() + 2.2
        );

        JsonNode faultGeo = faultLineService.getFaultLinesGeoJson(
                bbox.minLon,
                bbox.minLat,
                bbox.maxLon,
                bbox.maxLat,
                0.005
        );
        JsonNode features = faultGeo.path("features");
        if (!features.isArray() || features.size() == 0) {
            return new FaultAnalysis(null, List.of(), List.of(), 0);
        }

        List<FaultFeature> faults = new ArrayList<>();
        int idx = 0;
        for (JsonNode feature : features) {
            JsonNode props = feature.path("properties");
            List<List<double[]>> lines = toFaultLines(feature.path("geometry"));
            if (lines.isEmpty()) continue;
            String summary = extractFaultSummary(props);
            String detail = extractFaultDetail(props);
            String key = sanitize(props.path("catalog_id").asText(""));
            if (key.isBlank()) key = sanitize(props.path("name").asText(""));
            if (key.isBlank()) key = summary + "#" + idx;
            faults.add(new FaultFeature(key, summary, detail, lines));
            idx++;
        }

        if (faults.isEmpty()) {
            return new FaultAnalysis(null, List.of(), List.of(), 0);
        }

        List<FaultCandidate> focusCandidates = faults.stream()
                .map(f -> new FaultCandidate(distanceToFaultKm(focus.longitude(), focus.latitude(), f), f.summary, f.detail, f.key))
                .filter(c -> Double.isFinite(c.distanceKm))
                .sorted(Comparator.comparingDouble(c -> c.distanceKm))
                .limit(5)
                .toList();

        FaultMatch nearest = focusCandidates.isEmpty()
                ? null
                : new FaultMatch(focusCandidates.get(0).distanceKm, focusCandidates.get(0).summary);

        Map<String, FaultActivityAgg> activityByFault = new HashMap<>();
        scoped.stream().limit(140).forEach(e -> {
            double best = Double.POSITIVE_INFINITY;
            FaultFeature bestFault = null;
            for (FaultFeature f : faults) {
                double d = distanceToFaultKm(e.longitude(), e.latitude(), f);
                if (d < best) {
                    best = d;
                    bestFault = f;
                }
            }
            if (bestFault == null || !Double.isFinite(best) || best > 35.0) return;
            final String faultKey = bestFault.key;
            final String faultSummary = bestFault.summary;

            FaultActivityAgg agg = activityByFault.computeIfAbsent(
                    faultKey,
                    k -> new FaultActivityAgg(faultSummary)
            );
            agg.eventCount++;
            agg.maxMagnitude = Math.max(agg.maxMagnitude, e.magnitude());
            agg.sumDistanceKm += best;
        });

        List<FaultActivityRow> activityRows = activityByFault.values().stream()
                .map(a -> new FaultActivityRow(
                        a.summary,
                        a.eventCount,
                        a.maxMagnitude,
                        a.eventCount == 0 ? 0 : a.sumDistanceKm / a.eventCount
                ))
                .sorted((a, b) -> {
                    int byCount = Integer.compare(b.eventCount, a.eventCount);
                    if (byCount != 0) return byCount;
                    return Double.compare(b.maxMagnitude, a.maxMagnitude);
                })
                .limit(6)
                .toList();

        return new FaultAnalysis(nearest, focusCandidates, activityRows, faults.size());
    }

    private List<List<double[]>> toFaultLines(JsonNode geometry) {
        if (geometry == null || !geometry.isObject()) return List.of();
        String type = geometry.path("type").asText("");
        JsonNode coords = geometry.path("coordinates");
        if (!coords.isArray()) return List.of();

        List<List<double[]>> lines = new ArrayList<>();
        if ("LineString".equals(type)) {
            List<double[]> line = toPoints(coords);
            if (line.size() >= 2) lines.add(line);
            return lines;
        }

        if ("MultiLineString".equals(type)) {
            for (JsonNode lineNode : coords) {
                List<double[]> line = toPoints(lineNode);
                if (line.size() >= 2) lines.add(line);
            }
        }
        return lines;
    }

    private List<double[]> toPoints(JsonNode lineNode) {
        List<double[]> points = new ArrayList<>();
        if (lineNode == null || !lineNode.isArray()) return points;
        for (JsonNode p : lineNode) {
            if (!p.isArray() || p.size() < 2) continue;
            double lon = p.get(0).asDouble(Double.NaN);
            double lat = p.get(1).asDouble(Double.NaN);
            if (Double.isFinite(lon) && Double.isFinite(lat)) {
                points.add(new double[]{lon, lat});
            }
        }
        return points;
    }

    private double distanceToFaultKm(double lon, double lat, FaultFeature fault) {
        double minDist = Double.POSITIVE_INFINITY;
        for (List<double[]> line : fault.lines) {
            minDist = Math.min(minDist, distanceToLineKm(lon, lat, line));
        }
        return minDist;
    }

    private double distanceToLineKm(double lon, double lat, List<double[]> points) {
        if (points.size() < 2) return Double.POSITIVE_INFINITY;
        double minDist = Double.POSITIVE_INFINITY;
        for (int i = 0; i < points.size() - 1; i++) {
            double[] a = points.get(i);
            double[] b = points.get(i + 1);
            double d = pointToSegmentDistanceKm(lon, lat, a[0], a[1], b[0], b[1]);
            if (d < minDist) minDist = d;
        }
        return minDist;
    }

    private String extractFaultSummary(JsonNode properties) {
        if (properties == null || !properties.isObject()) return "Bilinmeyen fay segmenti";

        String[] directKeys = {"name", "fs_name", "catalog_name", "faultName", "ACIKLAMA", "aciklama", "segment", "type"};
        for (String key : directKeys) {
            JsonNode n = properties.get(key);
            if (n != null && n.isTextual()) {
                String text = sanitize(n.asText(""));
                if (!text.isBlank()) return text;
            }
        }

        JsonNode desc = properties.get("description");
        if (desc != null) {
            if (desc.isTextual()) {
                String text = sanitize(desc.asText(""));
                if (!text.isBlank()) return text;
            } else if (desc.isObject()) {
                String text = sanitize(desc.path("value").asText(""));
                if (!text.isBlank()) return text;
            }
        }

        // Keep some compact context when known keys are missing.
        if (properties.has("styleUrl")) {
            return "Segment (" + properties.path("styleUrl").asText("") + ")";
        }
        return "Bilinmeyen fay segmenti";
    }

    private String extractFaultDetail(JsonNode properties) {
        if (properties == null || !properties.isObject()) return "";
        List<String> parts = new ArrayList<>();
        appendFaultProp(parts, properties, "slip_type", "kayma");
        appendFaultProp(parts, properties, "last_movement", "son hareket");
        appendFaultProp(parts, properties, "net_slip_rate", "net hiz");
        appendFaultProp(parts, properties, "strike_slip_rate", "yanal hiz");
        appendFaultProp(parts, properties, "shortening_rate", "kisalma");
        appendFaultProp(parts, properties, "vert_sep_rate", "dusey ayrim");
        appendFaultProp(parts, properties, "activity_confidence", "aktivite guveni");
        appendFaultProp(parts, properties, "average_dip", "egim");
        appendFaultProp(parts, properties, "average_rake", "rake");

        if (parts.isEmpty()) {
            String notes = sanitize(properties.path("notes").asText(""));
            if (!notes.isBlank()) return notes;
            return "";
        }
        return String.join(" | ", parts);
    }

    private void appendFaultProp(List<String> parts, JsonNode properties, String key, String label) {
        JsonNode n = properties.get(key);
        if (n == null || n.isNull()) return;
        String value = sanitize(n.asText(""));
        if (value.isBlank() || "null".equalsIgnoreCase(value)) return;
        parts.add(label + ": " + value);
    }

    private String sanitize(String raw) {
        if (raw == null) return "";
        String noHtml = raw.replaceAll("<[^>]*>", " ");
        String cleaned = noHtml.replace("&nbsp;", " ")
                .replaceAll("\\s+", " ")
                .trim();
        return cleaned;
    }

    private List<EarthquakeDto> filterByBBox(List<EarthquakeDto> source, BBox bbox) {
        return source.stream()
                .filter(e ->
                        e.longitude() >= bbox.minLon && e.longitude() <= bbox.maxLon &&
                                e.latitude() >= bbox.minLat && e.latitude() <= bbox.maxLat
                )
                .toList();
    }

    private Optional<BBox> parseBBox(List<Double> bboxValues) {
        if (bboxValues == null || bboxValues.size() != 4) return Optional.empty();

        double minLon = nvl(bboxValues.get(0), Double.NaN);
        double minLat = nvl(bboxValues.get(1), Double.NaN);
        double maxLon = nvl(bboxValues.get(2), Double.NaN);
        double maxLat = nvl(bboxValues.get(3), Double.NaN);
        if (!Double.isFinite(minLon) || !Double.isFinite(minLat) || !Double.isFinite(maxLon) || !Double.isFinite(maxLat)) {
            return Optional.empty();
        }

        double nMinLon = Math.min(minLon, maxLon);
        double nMaxLon = Math.max(minLon, maxLon);
        double nMinLat = Math.min(minLat, maxLat);
        double nMaxLat = Math.max(minLat, maxLat);
        return Optional.of(new BBox(nMinLon, nMinLat, nMaxLon, nMaxLat));
    }

    private double pointToSegmentDistanceKm(
            double lon,
            double lat,
            double lon1,
            double lat1,
            double lon2,
            double lat2
    ) {
        double latRad = Math.toRadians(lat);
        double kx = 111.32 * Math.cos(latRad);
        double ky = 110.57;

        double ax = (lon1 - lon) * kx;
        double ay = (lat1 - lat) * ky;
        double bx = (lon2 - lon) * kx;
        double by = (lat2 - lat) * ky;

        double vx = bx - ax;
        double vy = by - ay;
        double len2 = vx * vx + vy * vy;
        if (len2 <= 1e-12) {
            return Math.sqrt(ax * ax + ay * ay);
        }

        double t = -(ax * vx + ay * vy) / len2;
        t = Math.max(0, Math.min(1, t));
        double px = ax + t * vx;
        double py = ay + t * vy;
        return Math.sqrt(px * px + py * py);
    }

    private double haversineKm(double lat1, double lon1, double lat2, double lon2) {
        double dLat = Math.toRadians(lat2 - lat1);
        double dLon = Math.toRadians(lon2 - lon1);
        double a = Math.sin(dLat / 2) * Math.sin(dLat / 2) +
                Math.cos(Math.toRadians(lat1)) * Math.cos(Math.toRadians(lat2)) *
                        Math.sin(dLon / 2) * Math.sin(dLon / 2);
        return 6371.0 * (2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a)));
    }

    private double round2(double value) {
        return Math.round(value * 100.0) / 100.0;
    }

    private double round3(double value) {
        return Math.round(value * 1000.0) / 1000.0;
    }

    private double round4(double value) {
        return Math.round(value * 10000.0) / 10000.0;
    }

    private String distanceBand(double km) {
        if (!Double.isFinite(km)) return "belirsiz mesafede";
        if (km <= 2.0) return "cok yakin";
        if (km <= 8.0) return "yakin";
        if (km <= 20.0) return "orta yakinlikta";
        return "uzak";
    }

    private double clamp(double value, double min, double max) {
        if (Double.isNaN(value)) return min;
        return Math.max(min, Math.min(max, value));
    }

    private int clampInt(int value, int min, int max) {
        return Math.max(min, Math.min(max, value));
    }

    private int nvl(Integer value, int fallback) {
        return value == null ? fallback : value;
    }

    private double nvl(Double value, double fallback) {
        return value == null ? fallback : value;
    }

    private static final class FaultFeature {
        final String key;
        final String summary;
        final String detail;
        final List<List<double[]>> lines;

        FaultFeature(String key, String summary, String detail, List<List<double[]>> lines) {
            this.key = key;
            this.summary = summary;
            this.detail = detail;
            this.lines = lines;
        }
    }

    private static final class FaultCandidate {
        final double distanceKm;
        final String summary;
        final String detail;
        final String key;

        FaultCandidate(double distanceKm, String summary, String detail, String key) {
            this.distanceKm = distanceKm;
            this.summary = summary;
            this.detail = detail;
            this.key = key;
        }
    }

    private static final class FaultActivityAgg {
        final String summary;
        int eventCount = 0;
        double maxMagnitude = 0.0;
        double sumDistanceKm = 0.0;

        FaultActivityAgg(String summary) {
            this.summary = summary;
        }
    }

    private static final class FaultActivityRow {
        final String summary;
        final int eventCount;
        final double maxMagnitude;
        final double avgDistanceKm;

        FaultActivityRow(String summary, int eventCount, double maxMagnitude, double avgDistanceKm) {
            this.summary = summary;
            this.eventCount = eventCount;
            this.maxMagnitude = maxMagnitude;
            this.avgDistanceKm = avgDistanceKm;
        }
    }

    private static final class FaultAnalysis {
        final FaultMatch nearestFault;
        final List<FaultCandidate> focusCandidates;
        final List<FaultActivityRow> activityRows;
        final int faultCount;

        FaultAnalysis(
                FaultMatch nearestFault,
                List<FaultCandidate> focusCandidates,
                List<FaultActivityRow> activityRows,
                int faultCount
        ) {
            this.nearestFault = nearestFault;
            this.focusCandidates = focusCandidates;
            this.activityRows = activityRows;
            this.faultCount = faultCount;
        }
    }

    private record BBox(double minLon, double minLat, double maxLon, double maxLat) {
    }

    private static final class FaultMatch {
        final double distanceKm;
        final String summary;

        FaultMatch(double distanceKm, String summary) {
            this.distanceKm = distanceKm;
            this.summary = summary;
        }
    }
}
