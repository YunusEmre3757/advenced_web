package com.example.backend.fault;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.core.io.ClassPathResource;
import org.springframework.core.io.FileSystemResource;
import org.springframework.core.io.Resource;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.web.server.ResponseStatusException;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.ObjectMapper;
import tools.jackson.databind.node.ArrayNode;
import tools.jackson.databind.node.ObjectNode;

import java.io.IOException;
import java.io.InputStream;
import java.time.Instant;
import java.util.ArrayList;
import java.util.List;

@Service
public class FaultLineService {

    private final ObjectMapper objectMapper;

    @Value("${faults.mta.geojson-path:classpath:data/turkey_active_faults.geojson}")
    private String geoJsonPath;

    @Value("${faults.viewport.expand-deg:0.6}")
    private double viewportExpandDeg;

    private volatile JsonNode cachedGeoJson = null;
    private volatile Instant cacheExpiresAt = Instant.EPOCH;

    public FaultLineService(ObjectMapper objectMapper) {
        this.objectMapper = objectMapper;
    }

    public JsonNode getFaultLinesGeoJson(
            Double minLon,
            Double minLat,
            Double maxLon,
            Double maxLat,
            double simplifyTolerance
    ) {
        JsonNode root = getRawFaultGeoJson();

        BBox bbox = null;
        if (minLon != null && minLat != null && maxLon != null && maxLat != null) {
            double expand = clamp(viewportExpandDeg, 0.0, 2.0);
            bbox = new BBox(minLon, minLat, maxLon, maxLat).normalized().expanded(expand);
        }

        double tolerance = clamp(simplifyTolerance, 0.001, 0.06);

        ObjectNode outRoot = objectMapper.createObjectNode();
        outRoot.put("type", "FeatureCollection");
        ArrayNode outFeatures = objectMapper.createArrayNode();

        JsonNode features = root.path("features");
        if (!features.isArray()) {
            throw new ResponseStatusException(HttpStatus.BAD_GATEWAY, "Fault GeoJSON has invalid features array");
        }

        for (JsonNode feature : features) {
            JsonNode geometry = feature.path("geometry");
            String geometryType = geometry.path("type").asText("");
            JsonNode coordinates = geometry.path("coordinates");

            if ("LineString".equals(geometryType) && coordinates.isArray()) {
                JsonNode simplified = simplifyLineStringNode(coordinates, bbox, tolerance);
                if (simplified != null) {
                    outFeatures.add(buildFeature(feature.path("properties"), "LineString", simplified));
                }
            } else if ("MultiLineString".equals(geometryType) && coordinates.isArray()) {
                ArrayNode simplifiedMulti = simplifyMultiLineStringNode(coordinates, bbox, tolerance);
                if (simplifiedMulti != null && simplifiedMulti.size() > 0) {
                    outFeatures.add(buildFeature(feature.path("properties"), "MultiLineString", simplifiedMulti));
                }
            }
        }

        outRoot.set("features", outFeatures);
        return outRoot;
    }

    private JsonNode getRawFaultGeoJson() {
        Instant now = Instant.now();
        if (cachedGeoJson != null && now.isBefore(cacheExpiresAt)) {
            return cachedGeoJson;
        }

        Resource resource = resolveResource();
        if (!resource.exists()) {
            throw new ResponseStatusException(
                    HttpStatus.SERVICE_UNAVAILABLE,
                    "MTA fault GeoJSON file not found: " + geoJsonPath
            );
        }

        try (InputStream inputStream = resource.getInputStream()) {
            JsonNode root = objectMapper.readTree(inputStream);
            if (!root.isObject() || !"FeatureCollection".equals(root.path("type").asText())) {
                throw new ResponseStatusException(
                        HttpStatus.BAD_GATEWAY,
                        "Fault GeoJSON must be a FeatureCollection"
                );
            }

            cachedGeoJson = root;
            cacheExpiresAt = now.plusSeconds(300);
            return root;
        } catch (IOException e) {
            throw new ResponseStatusException(
                    HttpStatus.SERVICE_UNAVAILABLE,
                    "Could not read fault GeoJSON",
                    e
            );
        }
    }

    private ObjectNode buildFeature(JsonNode properties, String geometryType, JsonNode geometryCoords) {
        ObjectNode feature = objectMapper.createObjectNode();
        feature.put("type", "Feature");

        if (properties != null && properties.isObject()) {
            feature.set("properties", properties);
        } else {
            feature.set("properties", objectMapper.createObjectNode());
        }

        ObjectNode geometry = objectMapper.createObjectNode();
        geometry.put("type", geometryType);
        geometry.set("coordinates", geometryCoords);
        feature.set("geometry", geometry);
        return feature;
    }

    private JsonNode simplifyLineStringNode(JsonNode coordinates, BBox bbox, double tolerance) {
        List<double[]> line = parseLine(coordinates);
        if (line.size() < 2) return null;

        if (bbox != null && !intersectsBBox(line, bbox)) {
            return null;
        }

        List<double[]> simplified = simplifyByDistance(line, tolerance);
        if (simplified.size() < 2) return null;

        return toCoordinatesNode(simplified);
    }

    private ArrayNode simplifyMultiLineStringNode(JsonNode coordinates, BBox bbox, double tolerance) {
        ArrayNode outMulti = objectMapper.createArrayNode();

        for (JsonNode lineNode : coordinates) {
            if (!lineNode.isArray()) continue;

            List<double[]> line = parseLine(lineNode);
            if (line.size() < 2) continue;

            if (bbox != null && !intersectsBBox(line, bbox)) {
                continue;
            }

            List<double[]> simplified = simplifyByDistance(line, tolerance);
            if (simplified.size() >= 2) {
                outMulti.add(toCoordinatesNode(simplified));
            }
        }

        return outMulti;
    }

    private List<double[]> parseLine(JsonNode coordinates) {
        List<double[]> result = new ArrayList<>();
        for (JsonNode p : coordinates) {
            if (!p.isArray() || p.size() < 2) continue;
            double lon = p.get(0).asDouble(Double.NaN);
            double lat = p.get(1).asDouble(Double.NaN);
            if (Double.isNaN(lon) || Double.isNaN(lat)) continue;
            result.add(new double[]{lon, lat});
        }
        return result;
    }

    private ArrayNode toCoordinatesNode(List<double[]> points) {
        ArrayNode out = objectMapper.createArrayNode();
        for (double[] p : points) {
            ArrayNode point = objectMapper.createArrayNode();
            point.add(p[0]);
            point.add(p[1]);
            out.add(point);
        }
        return out;
    }

    private List<double[]> simplifyByDistance(List<double[]> points, double tolerance) {
        if (points.size() <= 2) return points;

        List<double[]> out = new ArrayList<>();
        double[] previous = points.get(0);
        out.add(previous);

        for (int i = 1; i < points.size() - 1; i++) {
            double[] current = points.get(i);
            if (distance(previous, current) >= tolerance) {
                out.add(current);
                previous = current;
            }
        }

        double[] last = points.get(points.size() - 1);
        double[] beforeLast = out.get(out.size() - 1);
        if (distance(beforeLast, last) > 0) {
            out.add(last);
        }

        return out;
    }

    private boolean intersectsBBox(List<double[]> line, BBox bbox) {
        double minLon = Double.POSITIVE_INFINITY;
        double minLat = Double.POSITIVE_INFINITY;
        double maxLon = Double.NEGATIVE_INFINITY;
        double maxLat = Double.NEGATIVE_INFINITY;

        for (double[] p : line) {
            minLon = Math.min(minLon, p[0]);
            minLat = Math.min(minLat, p[1]);
            maxLon = Math.max(maxLon, p[0]);
            maxLat = Math.max(maxLat, p[1]);
        }

        return maxLon >= bbox.minLon && minLon <= bbox.maxLon &&
                maxLat >= bbox.minLat && minLat <= bbox.maxLat;
    }

    private double distance(double[] a, double[] b) {
        double dx = a[0] - b[0];
        double dy = a[1] - b[1];
        return Math.sqrt(dx * dx + dy * dy);
    }

    private double clamp(double value, double min, double max) {
        if (Double.isNaN(value)) return min;
        return Math.max(min, Math.min(max, value));
    }

    private Resource resolveResource() {
        if (geoJsonPath == null || geoJsonPath.isBlank()) {
            return new ClassPathResource("data/turkey_active_faults.geojson");
        }

        if (geoJsonPath.startsWith("classpath:")) {
            String cp = geoJsonPath.substring("classpath:".length());
            if (cp.startsWith("/")) cp = cp.substring(1);
            return new ClassPathResource(cp);
        }

        return new FileSystemResource(geoJsonPath);
    }

    private record BBox(double minLon, double minLat, double maxLon, double maxLat) {
        BBox normalized() {
            double nMinLon = Math.min(minLon, maxLon);
            double nMaxLon = Math.max(minLon, maxLon);
            double nMinLat = Math.min(minLat, maxLat);
            double nMaxLat = Math.max(minLat, maxLat);
            return new BBox(nMinLon, nMinLat, nMaxLon, nMaxLat);
        }

        BBox expanded(double delta) {
            return new BBox(minLon - delta, minLat - delta, maxLon + delta, maxLat + delta);
        }
    }
}
