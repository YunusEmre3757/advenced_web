package com.example.backend.graph;

import org.springframework.web.bind.annotation.CrossOrigin;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.servlet.mvc.method.annotation.SseEmitter;

import java.util.Map;

@RestController
@RequestMapping("/api/graph")
@CrossOrigin(origins = {
        "http://localhost:4200",
        "http://127.0.0.1:4200",
        "http://localhost:5173",
        "http://127.0.0.1:5173"
})
public class GraphController {

    private final GraphClient client;

    public GraphController(GraphClient client) {
        this.client = client;
    }

    @PostMapping("/chat")
    public Object chat(@RequestBody Map<String, Object> body) {
        return client.postJson("/graph/chat", body);
    }

    @GetMapping(value = "/chat/stream", produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    public SseEmitter chatStream(
            @RequestParam String question,
            @RequestParam(defaultValue = "default") String sessionId,
            @RequestParam(required = false) Double latitude,
            @RequestParam(required = false) Double longitude
    ) {
        return client.streamChat(question, sessionId, latitude, longitude);
    }

    @PostMapping("/notify-route")
    public Object notifyRoute(@RequestBody Map<String, Object> body) {
        return client.postJson("/graph/notify-route", body);
    }

    @PostMapping("/quake-detail")
    public Object quakeDetail(@RequestBody Map<String, Object> body) {
        return client.postJson("/graph/quake-detail", body);
    }

    @PostMapping("/building-risk")
    public Object buildingRisk(@RequestBody Map<String, Object> body) {
        return client.postJson("/graph/building-risk", body);
    }

    @PostMapping("/safe-check")
    public Object safeCheck(@RequestBody Map<String, Object> body) {
        return client.postJson("/graph/safe-check", body);
    }
}
