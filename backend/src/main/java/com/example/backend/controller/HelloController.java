package com.example.backend.controller;

import org.springframework.web.bind.annotation.CrossOrigin;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.Map;

@RestController
@RequestMapping("/api")
@CrossOrigin(origins = "http://localhost:4200")
public class HelloController {

    @GetMapping("/hello")
    public Map<String, String> sayHello() {
        return Map.of("message", "Hello from Spring Boot!");
    }
}
