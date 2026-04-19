package com.example.backend.feed;

import com.example.backend.earthquake.EarthquakeDto;
import com.example.backend.earthquake.EarthquakeService;
import jakarta.annotation.PostConstruct;
import jakarta.annotation.PreDestroy;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;
import org.springframework.web.servlet.mvc.method.annotation.SseEmitter;

import java.io.IOException;
import java.time.Instant;
import java.util.List;
import java.util.UUID;
import java.util.concurrent.CopyOnWriteArrayList;
import java.util.concurrent.Executors;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.TimeUnit;

@Service
public class EarthquakeFeedService {

    private final EarthquakeService earthquakes;
    private final CopyOnWriteArrayList<FeedClient> clients = new CopyOnWriteArrayList<>();
    private final ScheduledExecutorService scheduler = Executors.newSingleThreadScheduledExecutor(r -> {
        Thread thread = new Thread(r, "earthquake-feed-broadcast");
        thread.setDaemon(true);
        return thread;
    });

    @Value("${feed.earthquakes.interval-seconds:30}")
    private long intervalSeconds;

    public EarthquakeFeedService(EarthquakeService earthquakes) {
        this.earthquakes = earthquakes;
    }

    @PostConstruct
    void start() {
        long delaySeconds = Math.max(5, intervalSeconds);
        scheduler.scheduleWithFixedDelay(this::broadcast, delaySeconds, delaySeconds, TimeUnit.SECONDS);
    }

    @PreDestroy
    void stop() {
        scheduler.shutdownNow();
    }

    public SseEmitter subscribe(int hours, double minMagnitude, int limit) {
        SseEmitter emitter = new SseEmitter(0L);
        FeedClient client = new FeedClient(
                UUID.randomUUID().toString(),
                emitter,
                normalizeHours(hours),
                normalizeMagnitude(minMagnitude),
                normalizeLimit(limit)
        );

        clients.add(client);
        emitter.onCompletion(() -> clients.remove(client));
        emitter.onTimeout(() -> clients.remove(client));
        emitter.onError(error -> clients.remove(client));

        sendSnapshot(client);
        return emitter;
    }

    private void broadcast() {
        if (clients.isEmpty()) {
            return;
        }
        for (FeedClient client : clients) {
            sendSnapshot(client);
        }
    }

    private void sendSnapshot(FeedClient client) {
        try {
            List<EarthquakeDto> data = earthquakes.fetchRecentTurkeyEarthquakes(
                    client.hours(),
                    client.minMagnitude(),
                    client.limit()
            );
            client.emitter().send(SseEmitter.event()
                    .id(Instant.now().toString())
                    .name("snapshot")
                    .data(new FeedSnapshot("KANDILLI", Instant.now(), intervalSeconds, data)));
        } catch (Exception ex) {
            try {
                client.emitter().send(SseEmitter.event()
                        .name("feed-error")
                        .data(new FeedError(Instant.now(), "Deprem akisi gecici olarak alinamiyor.")));
            } catch (IOException ioEx) {
                clients.remove(client);
            }
        }
    }

    private int normalizeHours(int hours) {
        return Math.min(Math.max(hours, 1), 168);
    }

    private double normalizeMagnitude(double magnitude) {
        return Math.min(Math.max(magnitude, 0.0), 10.0);
    }

    private int normalizeLimit(int limit) {
        return Math.min(Math.max(limit, 1), 500);
    }

    private record FeedClient(
            String id,
            SseEmitter emitter,
            int hours,
            double minMagnitude,
            int limit
    ) {
    }

    private record FeedSnapshot(
            String source,
            Instant emittedAt,
            long intervalSeconds,
            List<EarthquakeDto> earthquakes
    ) {
    }

    private record FeedError(
            Instant emittedAt,
            String message
    ) {
    }
}
