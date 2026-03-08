package com.example.backend.controller;

import com.example.backend.fault.FaultLineService;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.CrossOrigin;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;
import tools.jackson.databind.JsonNode;

@RestController
@RequestMapping("/api/fault-lines")
@CrossOrigin(origins = {
        "http://localhost:4200",
        "http://127.0.0.1:4200",
        "http://localhost:5173",
        "http://127.0.0.1:5173"
})
public class FaultLineController {

    private final FaultLineService faultLineService;

    public FaultLineController(FaultLineService faultLineService) {
        this.faultLineService = faultLineService;
    }

    @GetMapping(produces = MediaType.APPLICATION_JSON_VALUE)
    public JsonNode faultLines(
            @RequestParam(required = false) String bbox,
            @RequestParam(defaultValue = "0.012") double simplify
    ) {
        Double minLon = null;
        Double minLat = null;
        Double maxLon = null;
        Double maxLat = null;

        if (bbox != null && !bbox.isBlank()) {
            String[] parts = bbox.split(",");
            if (parts.length != 4) {
                throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "bbox must be minLon,minLat,maxLon,maxLat");
            }
            try {
                minLon = Double.parseDouble(parts[0].trim());
                minLat = Double.parseDouble(parts[1].trim());
                maxLon = Double.parseDouble(parts[2].trim());
                maxLat = Double.parseDouble(parts[3].trim());
            } catch (NumberFormatException ex) {
                throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "bbox contains invalid numbers", ex);
            }
        }

        return faultLineService.getFaultLinesGeoJson(minLon, minLat, maxLon, maxLat, simplify);
    }
}
