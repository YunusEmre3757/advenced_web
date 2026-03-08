package com.example.backend.soil;

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

@Service
public class SoilZoneService {

    private final ObjectMapper objectMapper;

    @Value("${soil.zones.geojson-path:classpath:data/turkey_soil_site_classes.geojson}")
    private String geoJsonPath;

    @Value("${soil.zones.viewport.expand-deg:0.1}")
    private double viewportExpandDeg;

    private volatile JsonNode cachedGeoJson = null;
    private volatile Instant cacheExpiresAt = Instant.EPOCH;

    public SoilZoneService(ObjectMapper objectMapper) {
        this.objectMapper = objectMapper;
    }

    public JsonNode getSoilZonesGeoJson(Double minLon, Double minLat, Double maxLon, Double maxLat) {
        JsonNode root = getRawSoilGeoJson();

        BBox bbox = null;
        if (minLon != null && minLat != null && maxLon != null && maxLat != null) {
            double expand = clamp(viewportExpandDeg, 0.0, 1.0);
            bbox = new BBox(minLon, minLat, maxLon, maxLat).normalized().expanded(expand);
        }

        ObjectNode outRoot = objectMapper.createObjectNode();
        outRoot.put("type", "FeatureCollection");
        ArrayNode outFeatures = objectMapper.createArrayNode();

        JsonNode features = root.path("features");
        if (!features.isArray()) {
            throw new ResponseStatusException(HttpStatus.BAD_GATEWAY, "Soil GeoJSON has invalid features array");
        }

        for (JsonNode feature : features) {
            JsonNode geometry = feature.path("geometry");
            String geometryType = geometry.path("type").asText("");
            JsonNode coordinates = geometry.path("coordinates");

            if (!("Polygon".equals(geometryType) || "MultiPolygon".equals(geometryType))) {
                continue;
            }
            if (!coordinates.isArray()) continue;
            if (bbox != null && !intersectsBBox(coordinates, bbox)) continue;

            outFeatures.add(buildFeature(feature.path("properties"), geometryType, coordinates));
        }

        outRoot.set("features", outFeatures);
        return outRoot;
    }

    private JsonNode getRawSoilGeoJson() {
        Instant now = Instant.now();
        if (cachedGeoJson != null && now.isBefore(cacheExpiresAt)) {
            return cachedGeoJson;
        }

        Resource resource = resolveResource();
        if (!resource.exists()) {
            throw new ResponseStatusException(
                    HttpStatus.SERVICE_UNAVAILABLE,
                    "Soil zone GeoJSON file not found: " + geoJsonPath
            );
        }

        try (InputStream inputStream = resource.getInputStream()) {
            JsonNode root = objectMapper.readTree(inputStream);
            if (!root.isObject() || !"FeatureCollection".equals(root.path("type").asText())) {
                throw new ResponseStatusException(
                        HttpStatus.BAD_GATEWAY,
                        "Soil GeoJSON must be a FeatureCollection"
                );
            }

            cachedGeoJson = root;
            cacheExpiresAt = now.plusSeconds(300);
            return root;
        } catch (IOException e) {
            throw new ResponseStatusException(
                    HttpStatus.SERVICE_UNAVAILABLE,
                    "Could not read soil GeoJSON",
                    e
            );
        }
    }

    private ObjectNode buildFeature(JsonNode rawProperties, String geometryType, JsonNode geometryCoords) {
        ObjectNode feature = objectMapper.createObjectNode();
        feature.put("type", "Feature");
        feature.set("properties", normalizeProperties(rawProperties));

        ObjectNode geometry = objectMapper.createObjectNode();
        geometry.put("type", geometryType);
        geometry.set("coordinates", geometryCoords);
        feature.set("geometry", geometry);
        return feature;
    }

    private ObjectNode normalizeProperties(JsonNode rawProperties) {
        ObjectNode props = objectMapper.createObjectNode();
        if (rawProperties != null && rawProperties.isObject()) {
            props.setAll((ObjectNode) rawProperties.deepCopy());
        }

        Double vs30 = resolveVs30(rawProperties);
        if (vs30 != null && Double.isFinite(vs30)) {
            props.put("vs30", vs30);
        }

        String normalizedClass = resolveSiteClass(rawProperties, vs30);
        props.put("siteClass", normalizedClass != null ? normalizedClass : "UNKNOWN");
        return props;
    }

    private String resolveSiteClass(JsonNode rawProperties, Double vs30) {
        if (rawProperties != null && rawProperties.isObject()) {
            String[] classKeys = {
                    "siteClass", "site_class", "soilClass", "soil_class",
                    "zeminSinifi", "zemin_sinifi", "class"
            };
            for (String key : classKeys) {
                JsonNode n = rawProperties.get(key);
                if (n != null && n.isTextual()) {
                    String normalized = normalizeClassText(n.asText(""));
                    if (normalized != null) return normalized;
                }
            }
        }

        if (vs30 != null && Double.isFinite(vs30)) {
            return classFromVs30(vs30);
        }

        return null;
    }

    private Double resolveVs30(JsonNode rawProperties) {
        if (rawProperties == null || !rawProperties.isObject()) return null;
        String[] keys = {"vs30", "Vs30", "VS30"};

        for (String key : keys) {
            JsonNode n = rawProperties.get(key);
            if (n == null || n.isNull()) continue;
            if (n.isNumber()) return n.asDouble();
            if (n.isTextual()) {
                try {
                    return Double.parseDouble(n.asText().trim());
                } catch (NumberFormatException ignored) {
                }
            }
        }
        return null;
    }

    private String normalizeClassText(String value) {
        if (value == null) return null;
        String cleaned = value.trim().toUpperCase().replaceAll("[^A-Z0-9]", "");
        if (cleaned.isBlank()) return null;
        if (cleaned.matches("^Z[ABCDEF]$")) return cleaned;
        if (cleaned.matches("^[ABCDEF]$")) return "Z" + cleaned;
        if ("UNKNOWN".equals(cleaned)) return "UNKNOWN";
        return null;
    }

    private String classFromVs30(double vs30) {
        if (vs30 >= 1500) return "ZA";
        if (vs30 >= 760) return "ZB";
        if (vs30 >= 360) return "ZC";
        if (vs30 >= 180) return "ZD";
        return "ZE";
    }

    private boolean intersectsBBox(JsonNode coordinates, BBox bbox) {
        double[] bounds = {
                Double.POSITIVE_INFINITY, // minLon
                Double.POSITIVE_INFINITY, // minLat
                Double.NEGATIVE_INFINITY, // maxLon
                Double.NEGATIVE_INFINITY  // maxLat
        };

        collectBounds(coordinates, bounds);
        if (!Double.isFinite(bounds[0]) || !Double.isFinite(bounds[1]) ||
                !Double.isFinite(bounds[2]) || !Double.isFinite(bounds[3])) {
            return false;
        }

        return bounds[2] >= bbox.minLon && bounds[0] <= bbox.maxLon &&
                bounds[3] >= bbox.minLat && bounds[1] <= bbox.maxLat;
    }

    private void collectBounds(JsonNode node, double[] bounds) {
        if (node == null || !node.isArray()) return;

        if (node.size() >= 2 && node.get(0).isNumber() && node.get(1).isNumber()) {
            double lon = node.get(0).asDouble(Double.NaN);
            double lat = node.get(1).asDouble(Double.NaN);
            if (Double.isFinite(lon) && Double.isFinite(lat)) {
                bounds[0] = Math.min(bounds[0], lon);
                bounds[1] = Math.min(bounds[1], lat);
                bounds[2] = Math.max(bounds[2], lon);
                bounds[3] = Math.max(bounds[3], lat);
            }
            return;
        }

        for (JsonNode child : node) {
            collectBounds(child, bounds);
        }
    }

    private double clamp(double value, double min, double max) {
        if (Double.isNaN(value)) return min;
        return Math.max(min, Math.min(max, value));
    }

    private Resource resolveResource() {
        if (geoJsonPath == null || geoJsonPath.isBlank()) {
            return new ClassPathResource("data/turkey_soil_site_classes.geojson");
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
