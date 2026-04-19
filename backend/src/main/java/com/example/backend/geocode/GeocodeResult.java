package com.example.backend.geocode;

public record GeocodeResult(
        double latitude,
        double longitude,
        String displayName
) {
}
