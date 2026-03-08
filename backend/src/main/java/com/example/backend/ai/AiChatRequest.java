package com.example.backend.ai;

import java.util.List;

public record AiChatRequest(
        String question,
        Integer hours,
        Double minMagnitude,
        Integer limit,
        String eventId,
        Double latitude,
        Double longitude,
        List<Double> bbox
) {
}
