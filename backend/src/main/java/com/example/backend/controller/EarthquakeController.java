package com.example.backend.controller;

import com.example.backend.earthquake.EarthquakeDto;
import com.example.backend.earthquake.EarthquakeDetailDto;
import com.example.backend.earthquake.EarthquakeDetailService;
import com.example.backend.earthquake.EarthquakeService;
import com.example.backend.earthquake.ShakeMapService;
import org.springframework.web.bind.annotation.CrossOrigin;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import java.util.List;

@RestController
@RequestMapping("/api/earthquakes")
@CrossOrigin(origins = {
        "http://localhost:4200",
        "http://127.0.0.1:4200",
        "http://localhost:5173",
        "http://127.0.0.1:5173"
})
public class EarthquakeController {

    private final EarthquakeService earthquakeService;
    private final EarthquakeDetailService earthquakeDetailService;
    private final ShakeMapService shakeMapService;

    public EarthquakeController(
            EarthquakeService earthquakeService,
            EarthquakeDetailService earthquakeDetailService,
            ShakeMapService shakeMapService
    ) {
        this.earthquakeService = earthquakeService;
        this.earthquakeDetailService = earthquakeDetailService;
        this.shakeMapService = shakeMapService;
    }

    @GetMapping("/recent")
    public List<EarthquakeDto> recentEarthquakes(
            @RequestParam(defaultValue = "24") int hours,
            @RequestParam(defaultValue = "1.0") double minMagnitude,
            @RequestParam(defaultValue = "200") int limit
    ) {
        int normalizedHours = Math.min(Math.max(hours, 1), 168);
        double normalizedMinMagnitude = Math.min(Math.max(minMagnitude, 0.0), 10.0);
        int normalizedLimit = Math.min(Math.max(limit, 1), 500);
        return earthquakeService.fetchRecentTurkeyEarthquakes(
                normalizedHours,
                normalizedMinMagnitude,
                normalizedLimit
        );
    }

    @GetMapping("/{eventId}")
    public EarthquakeDetailDto earthquakeDetail(
            @PathVariable String eventId,
            @RequestParam(defaultValue = "12") int aftershockLimit,
            @RequestParam(defaultValue = "8") int similarLimit
    ) {
        EarthquakeDto event = earthquakeDetailService.findById(eventId);
        int normalizedAftershockLimit = Math.min(Math.max(aftershockLimit, 1), 50);
        int normalizedSimilarLimit = Math.min(Math.max(similarLimit, 1), 25);
        return new EarthquakeDetailDto(
                event,
                earthquakeDetailService.aftershocks(event, normalizedAftershockLimit),
                earthquakeDetailService.similarHistorical(event, normalizedSimilarLimit),
                earthquakeDetailService.dyfi(event),
                shakeMapService.fetchShakeMap(eventId)
        );
    }

    @GetMapping("/{eventId}/aftershocks")
    public List<EarthquakeDto> aftershocks(
            @PathVariable String eventId,
            @RequestParam(defaultValue = "12") int limit
    ) {
        EarthquakeDto event = earthquakeDetailService.findById(eventId);
        return earthquakeDetailService.aftershocks(event, Math.min(Math.max(limit, 1), 50));
    }

    @GetMapping("/{eventId}/similar")
    public List<EarthquakeDetailDto.HistoricalMatch> similarHistorical(
            @PathVariable String eventId,
            @RequestParam(defaultValue = "8") int limit
    ) {
        EarthquakeDto event = earthquakeDetailService.findById(eventId);
        return earthquakeDetailService.similarHistorical(event, Math.min(Math.max(limit, 1), 25));
    }

    @GetMapping("/{eventId}/dyfi")
    public EarthquakeDetailDto.DyfiSummary dyfi(@PathVariable String eventId) {
        EarthquakeDto event = earthquakeDetailService.findById(eventId);
        return earthquakeDetailService.dyfi(event);
    }

    @GetMapping("/{eventId}/shakemap")
    public ShakeMapService.ShakeMapDto shakeMap(@PathVariable String eventId) {
        return shakeMapService.fetchShakeMap(eventId);
    }
}
