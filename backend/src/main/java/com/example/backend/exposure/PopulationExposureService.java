package com.example.backend.exposure;

import org.springframework.core.io.ClassPathResource;
import org.springframework.stereotype.Service;

import java.io.BufferedReader;
import java.io.IOException;
import java.io.InputStreamReader;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;
import java.util.zip.GZIPInputStream;

@Service
public class PopulationExposureService {

    private static final String GRID_RESOURCE = "data/worldpop_tur_2021_1km_constrained.csv.gz";
    private static final String SOURCE = "WorldPop Turkey 2021 constrained population grid, 1km, CC BY 4.0";
    private volatile List<GridCell> cells;

    public ExposureEstimateDto estimate(double latitude, double longitude, double magnitude, double depthKm) {
        List<GridCell> grid = gridCells();
        int radiusKm = shakeRadiusKm(magnitude, depthKm);
        double latDelta = radiusKm / 111.32;
        double lngDelta = radiusKm / (111.32 * Math.max(0.2, Math.cos(Math.toRadians(latitude))));

        double exposed = 0;
        double affected = 0;
        int used = 0;

        for (GridCell cell : grid) {
            if (cell.lat < latitude - latDelta || cell.lat > latitude + latDelta) continue;
            if (cell.lng < longitude - lngDelta || cell.lng > longitude + lngDelta) continue;

            double distance = haversineKm(latitude, longitude, cell.lat, cell.lng);
            if (distance > radiusKm) continue;

            double distanceWeight = Math.pow(Math.max(0, 1 - distance / radiusKm), 1.35);
            double depthWeight = depthKm <= 10 ? 1.0 : depthKm <= 30 ? 0.88 : depthKm <= 70 ? 0.66 : 0.45;
            double magnitudeWeight = magnitude >= 6 ? 1.0 : magnitude >= 5 ? 0.72 : magnitude >= 4 ? 0.44 : 0.24;

            exposed += cell.population;
            affected += cell.population * distanceWeight * depthWeight * magnitudeWeight;
            used++;
        }

        String confidence = used >= 75 ? "orta" : "dusuk";
        String method = String.format(
                Locale.US,
                "WorldPop 1km grid hucreleri %.0f km yaricap icinde toplandi; magnitude, derinlik ve mesafe agirliklari uygulandi.",
                (double) radiusKm
        );

        return new ExposureEstimateDto(
                latitude,
                longitude,
                magnitude,
                depthKm,
                radiusKm,
                Math.round(affected),
                Math.round(exposed),
                used,
                confidence,
                SOURCE,
                method
        );
    }

    private List<GridCell> gridCells() {
        List<GridCell> loaded = cells;
        if (loaded != null) return loaded;
        synchronized (this) {
            if (cells == null) {
                cells = loadGrid();
            }
            return cells;
        }
    }

    private List<GridCell> loadGrid() {
        ClassPathResource resource = new ClassPathResource(GRID_RESOURCE);
        if (!resource.exists()) {
            throw new IllegalStateException("WorldPop grid resource not found: " + GRID_RESOURCE);
        }

        List<GridCell> loaded = new ArrayList<>(340_000);
        try (
                GZIPInputStream gzip = new GZIPInputStream(resource.getInputStream());
                BufferedReader reader = new BufferedReader(new InputStreamReader(gzip, StandardCharsets.UTF_8))
        ) {
            String line = reader.readLine();
            while ((line = reader.readLine()) != null) {
                String[] parts = line.split(",");
                if (parts.length != 3) continue;
                loaded.add(new GridCell(
                        Double.parseDouble(parts[0]),
                        Double.parseDouble(parts[1]),
                        Double.parseDouble(parts[2])
                ));
            }
        } catch (IOException e) {
            throw new IllegalStateException("WorldPop grid could not be read", e);
        }
        return List.copyOf(loaded);
    }

    private int shakeRadiusKm(double magnitude, double depthKm) {
        int base;
        if (magnitude >= 7) base = 220;
        else if (magnitude >= 6) base = 150;
        else if (magnitude >= 5) base = 90;
        else if (magnitude >= 4) base = 55;
        else if (magnitude >= 3) base = 30;
        else base = 15;

        double depthFactor = depthKm <= 10 ? 1.15 : depthKm <= 30 ? 1.0 : depthKm <= 70 ? 0.82 : 0.65;
        return Math.max(12, (int) Math.round(base * depthFactor));
    }

    private double haversineKm(double lat1, double lng1, double lat2, double lng2) {
        double dLat = Math.toRadians(lat2 - lat1);
        double dLng = Math.toRadians(lng2 - lng1);
        double a = Math.sin(dLat / 2) * Math.sin(dLat / 2)
                + Math.cos(Math.toRadians(lat1)) * Math.cos(Math.toRadians(lat2))
                * Math.sin(dLng / 2) * Math.sin(dLng / 2);
        return 6371 * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
    }

    private record GridCell(double lat, double lng, double population) {
    }
}
