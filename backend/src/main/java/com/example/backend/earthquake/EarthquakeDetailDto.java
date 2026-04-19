package com.example.backend.earthquake;

import java.time.Instant;
import java.util.List;

// ShakeMapService.ShakeMapDto is in the same package — no extra import needed

public record EarthquakeDetailDto(
        EarthquakeDto event,
        List<EarthquakeDto> aftershocks,
        List<HistoricalMatch> similarHistorical,
        DyfiSummary dyfi,
        ShakeMapService.ShakeMapDto shakeMap
) {
    public record HistoricalMatch(
            String id,
            Instant time,
            String place,
            double magnitude,
            double latitude,
            double longitude,
            double depthKm,
            double distanceKm,
            double magnitudeDelta
    ) {
    }

    public record DyfiSummary(
            Integer responses,
            Double maxCdi,
            String url
    ) {
    }
}
