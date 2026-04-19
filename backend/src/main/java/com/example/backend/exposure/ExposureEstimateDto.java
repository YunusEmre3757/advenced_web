package com.example.backend.exposure;

public record ExposureEstimateDto(
        double latitude,
        double longitude,
        double magnitude,
        double depthKm,
        int radiusKm,
        long estimatedAffectedPopulation,
        long exposedPopulationWithinRadius,
        int cellsUsed,
        String confidence,
        String source,
        String method
) {
}
