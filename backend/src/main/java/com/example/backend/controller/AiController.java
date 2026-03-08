package com.example.backend.controller;

import com.example.backend.ai.AiChatRequest;
import com.example.backend.ai.AiChatResponse;
import com.example.backend.ai.GroqAiService;
import org.springframework.web.bind.annotation.CrossOrigin;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/ai")
@CrossOrigin(origins = {
        "http://localhost:4200",
        "http://127.0.0.1:4200",
        "http://localhost:5173",
        "http://127.0.0.1:5173"
})
public class AiController {

    private final GroqAiService groqAiService;

    public AiController(GroqAiService groqAiService) {
        this.groqAiService = groqAiService;
    }

    @PostMapping("/chat")
    public AiChatResponse chat(@RequestBody AiChatRequest request) {
        return groqAiService.chat(request);
    }
}
