package com.example.backend.feed;

import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.servlet.mvc.method.annotation.SseEmitter;

@RestController
@RequestMapping("/api/feed/earthquakes")
public class EarthquakeFeedController {

    private final EarthquakeFeedService feed;

    public EarthquakeFeedController(EarthquakeFeedService feed) {
        this.feed = feed;
    }

    @GetMapping(value = "/stream", produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    public SseEmitter stream(
            @RequestParam(defaultValue = "168") int hours,
            @RequestParam(defaultValue = "1.0") double minMagnitude,
            @RequestParam(defaultValue = "500") int limit
    ) {
        return feed.subscribe(hours, minMagnitude, limit);
    }
}
