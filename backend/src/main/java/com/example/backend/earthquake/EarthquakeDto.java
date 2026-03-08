package com.example.backend.earthquake;

import java.time.Instant;

public record EarthquakeDto(
        String id,
        Instant time,
        String location,
        double latitude,
        double longitude,
        double magnitude,
        double depthKm
) {
}
