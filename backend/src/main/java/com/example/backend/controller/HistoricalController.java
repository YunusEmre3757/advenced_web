package com.example.backend.controller;

import com.example.backend.earthquake.HistoricalEarthquakeService;
import com.example.backend.earthquake.HistoricalEarthquakeService.HistoricalEvent;
import com.example.backend.earthquake.HistoricalEarthquakeService.SeismicGap;
import org.springframework.web.bind.annotation.CrossOrigin;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import java.util.List;

@RestController
@RequestMapping("/api/historical")
@CrossOrigin(origins = {
        "http://localhost:4200",
        "http://127.0.0.1:4200",
        "http://localhost:5173",
        "http://127.0.0.1:5173"
})
public class HistoricalController {

    private final HistoricalEarthquakeService service;

    public HistoricalController(HistoricalEarthquakeService service) {
        this.service = service;
    }

    @GetMapping("/events")
    public List<HistoricalEvent> events(
            @RequestParam(defaultValue = "50") int years,
            @RequestParam(defaultValue = "5.0") double minMagnitude
    ) {
        int normalizedYears = Math.min(Math.max(years, 1), 100);
        double normalizedMag = Math.min(Math.max(minMagnitude, 3.0), 9.0);
        return service.fetch(normalizedYears, normalizedMag);
    }

    @GetMapping("/gaps")
    public List<SeismicGap> gaps(
            @RequestParam(defaultValue = "50") int years,
            @RequestParam(defaultValue = "5.5") double gapMagnitude,
            @RequestParam(defaultValue = "30") int silentYears,
            @RequestParam(defaultValue = "18") int gridSize
    ) {
        int normalizedYears = Math.min(Math.max(years, 10), 100);
        int normalizedSilent = Math.min(Math.max(silentYears, 5), 80);
        int normalizedGrid = Math.min(Math.max(gridSize, 6), 40);
        double normalizedMag = Math.min(Math.max(gapMagnitude, 4.0), 8.0);
        List<HistoricalEvent> events = service.fetch(normalizedYears, Math.min(normalizedMag - 0.5, 4.5));
        return service.computeGaps(events, normalizedGrid, normalizedSilent, normalizedMag);
    }
}
