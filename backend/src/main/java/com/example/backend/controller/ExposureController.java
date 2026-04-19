package com.example.backend.controller;

import com.example.backend.exposure.ExposureEstimateDto;
import com.example.backend.exposure.PopulationExposureService;
import org.springframework.web.bind.annotation.CrossOrigin;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/exposure")
@CrossOrigin(origins = {
        "http://localhost:4200",
        "http://127.0.0.1:4200",
        "http://localhost:5173",
        "http://127.0.0.1:5173"
})
public class ExposureController {

    private final PopulationExposureService exposureService;

    public ExposureController(PopulationExposureService exposureService) {
        this.exposureService = exposureService;
    }

    @GetMapping("/estimate")
    public ExposureEstimateDto estimate(
            @RequestParam double latitude,
            @RequestParam double longitude,
            @RequestParam double magnitude,
            @RequestParam double depthKm
    ) {
        double lat = Math.max(35.0, Math.min(43.5, latitude));
        double lng = Math.max(25.0, Math.min(45.5, longitude));
        double mag = Math.max(0.0, Math.min(10.0, magnitude));
        double depth = Math.max(0.0, Math.min(700.0, depthKm));
        return exposureService.estimate(lat, lng, mag, depth);
    }
}
