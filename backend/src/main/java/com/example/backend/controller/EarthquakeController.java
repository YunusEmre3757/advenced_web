package com.example.backend.controller;

import com.example.backend.earthquake.EarthquakeDto;
import com.example.backend.earthquake.EarthquakeService;
import org.springframework.web.bind.annotation.CrossOrigin;
import org.springframework.web.bind.annotation.GetMapping;
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

    public EarthquakeController(EarthquakeService earthquakeService) {
        this.earthquakeService = earthquakeService;
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
}
