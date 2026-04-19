# Seismic Graph Service

LangGraph tabanli orkestrasyon servisi. Spring Boot uygulamasi veri, kimlik, bildirim teslimati ve idempotency'den sorumludur; LangGraph karar akisi, ozetleme ve sohbet hafizasindan sorumludur.

## Neden Ayri Graph Servisi?

- Spring deterministik tarafi tutar: kullanici, aile, teslimat audit'i, SHA-256 idempotency, Pushover/Resend gonderimi.
- LangGraph degisken karar akislarini tutar: soru siniflandirma, bildirim tonu, deprem raporu derinligi, safe-check mesaj tonu.
- Graph servisi calismazsa kritik teslimat akislari Spring fallback ile devam eder.

## Endpointler

- `POST /graph/chat`: AI Asistan. `sessionId` ayni kaldikca konusma state'i Postgres checkpoint ile surer.
- `GET /graph/chat/stream`: SSE stream. Frontend token event'lerini parca parca alir.
- `POST /graph/notify-route`: Deprem olayi + aday kullanicilar girer, severity + kanal + mesaj plani cikar.
- `POST /graph/safe-check`: Guvendeyim check-in'i icin aile mesaj tonu ve ozet cikar.
- `POST /graph/quake-detail`: Spring'den detay/artci adaylari/benzer olaylari paralel toplar, raporlar.
- `GET /health`: dry-run ve checkpoint modunu gosterir.

## Checkpoint

Varsayilan mod Postgres'tir:

```text
GRAPH_CHECKPOINT_MODE=postgres
GRAPH_DATABASE_URL=postgresql://seismic:seismic_dev_only@localhost:5432/seismic
```

LangGraph `checkpoints`, `checkpoint_blobs`, `checkpoint_writes` tablolarini olusturur. Chat grafi `thread_id = sessionId` ile calisir; bu sayede ayni kullanici oturumunda konusma gecmisi process restart sonrasi da korunur.

Sadece izole demo icin:

```text
GRAPH_CHECKPOINT_MODE=memory
```

## Calistirma

```bash
cd graph
pip install -e .
python run_server.py
```

Windows'ta `python run_server.py` kullanilir; bu launcher Psycopg async Postgres checkpoint icin gerekli event loop policy ayarini uvicorn baslamadan once yapar.

Spring tarafinda graph proxy:

```text
GRAPH_SERVICE_URL=http://localhost:8002
```

## Dry Run

`GROQ_API_KEY` yoksa LLM cevaplari deterministic dry-run metni dondurur. Graph yapisi, checkpoint, stream ve routing yine calisir.

```text
GROQ_API_KEY=gsk-...
GROQ_MODEL=llama-3.3-70b-versatile
SPRING_BASE_URL=http://localhost:8080
```
