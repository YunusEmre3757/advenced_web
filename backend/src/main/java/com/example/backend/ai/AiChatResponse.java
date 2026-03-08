package com.example.backend.ai;

public record AiChatResponse(
        String answer,
        String model,
        int eventCount,
        String focusEventId,
        String focusEventLocation,
        Double focusEventMagnitude,
        Double focusEventDepthKm,
        Double nearestFaultDistanceKm,
        String nearestFaultSummary,
        String note
) {
}
