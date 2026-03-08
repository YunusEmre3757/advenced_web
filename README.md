# Seismic Command Dashboard

Türkiye için AI destekli deprem izleme ve risk değerlendirme sistemi. Platform; Kandilli Rasathanesi'nden (KOERI) canlı deprem verisi çekerek interaktif harita üzerinde deprem noktalarını, MTA fay hatlarını ve zemin sınıflandırma zonlarını görselleştirir. Groq LLM (LLaMA 3.3 70B) entegrasyonu ile kullanıcılara Türkçe deprem analizi, fay-deprem korelasyonu ve doğal dil tabanlı soru-cevap imkânı sunar.

## Özellikler

- **Canlı Deprem İzleme** – Kandilli Rasathanesi'nden gerçek zamanlı veri (30 sn cache), büyüklük/derinlik/zaman filtresi
- **İnteraktif Harita** – Leaflet/MapLibre tabanlı harita; deprem işaretçileri (büyüklüğe göre renk kodlu), MTA fay hattı katmanları, zemin sınıflandırma zonları (ZA–ZF)
- **Dashboard Analitiği** – KPI kartları, 7 günlük trend grafiği, büyüklük dağılımı, en riskli şehirler, saatlik anomali tespiti
- **AI Copilot** – Groq LLM ile deprem analizi, fay-deprem korelasyonu, risk değerlendirmesi, deprem önlemleri ve Türkçe doğal dil soru-cevap
- **Jeo-uzamsal Arama & Filtreleme** – Konum araması, çoklu parametre filtresi, dinamik viewport tabanlı veri yükleme

## Sayfalar

| Sayfa | Route | Açıklama |
|-------|-------|----------|
| Dashboard | `/dashboard` | KPI özeti, trend grafikleri, büyüklük dağılımı, riskli şehirler, AI önerileri |
| Harita | `/map` | Tam ekran interaktif harita, fay hatları, zemin zonları, AI sohbet paneli |
| Risk Sorgusu | `/risk-query` | Risk sorgulama arayüzü |

## Kullanılan Teknolojiler

### Frontend
- **Angular 21** (Standalone Components, TypeScript 5.9)
- **Leaflet & MapLibre GL** – İnteraktif haritalar
- **RxJS** – Reaktif veri akışları
- **Vitest** – Birim testleri

### Backend
- **Spring Boot 4.0** (Java 17)
- **Spring Data JPA** + H2 Database
- **Groq AI API** – LLaMA 3.3 70B Versatile modeli
- **Jackson** – JSON işleme

### Dış Veri Kaynakları
- **Kandilli Rasathanesi (KOERI)** – Gerçek zamanlı deprem verisi
- **MTA (Maden Tetkik ve Arama)** – Türkiye aktif fay hatları (GeoJSON)
- **Zemin Sınıflandırma** – Vs30 tabanlı zemin zonları (GeoJSON)

## Kurulum ve Çalıştırma

### Gereksinimler
- Java 17+
- Node.js 18+
- npm 9+

### Backend

```bash
cd backend
./mvnw spring-boot:run
```

Backend `http://localhost:8080` adresinde çalışır.

> **Not:** AI özelliklerini aktif etmek için `backend/src/main/resources/application.properties` dosyasında Groq API anahtarınızı ayarlayın:
> ```
> ai.groq.api-key=YOUR_API_KEY
> ```

### Frontend

```bash
cd frontend
npm install
npm start
```

Frontend `http://localhost:4200` adresinde çalışır.

## API Endpoint'leri

| Metod | Endpoint | Açıklama |
|-------|----------|----------|
| GET | `/api/earthquakes/recent` | Son depremleri getir (params: hours, minMagnitude, limit) |
| GET | `/api/fault-lines` | Bounding box'a göre fay hatlarını getir (params: bbox, simplify) |
| GET | `/api/soil-zones` | Bounding box'a göre zemin sınıflandırma zonlarını getir (params: bbox) |
| POST | `/api/ai/chat` | AI destekli deprem analizi sohbeti |

## Proje Yapısı

```
├── frontend/src/app/
│   ├── pages/
│   │   ├── dashboard/        # KPI dashboard, mini harita
│   │   ├── map/              # Tam ekran interaktif harita + AI sohbet
│   │   └── risk-query/       # Risk sorgulama sayfası
│   ├── shared/               # Yeniden kullanılabilir UI bileşenleri
│   │   ├── navbar/
│   │   ├── kpi-card/
│   │   ├── weekly-chart/
│   │   ├── mag-distribution/
│   │   ├── risk-city-list/
│   │   ├── ai-insights/
│   │   └── hourly-anomaly/
│   └── core/                 # API servis katmanları
│       ├── earthquake-api.ts
│       ├── fault-line-api.ts
│       ├── soil-zone-api.ts
│       └── ai-api.ts
│
├── backend/src/main/java/com/example/backend/
│   ├── controller/           # REST controller'lar
│   ├── earthquake/           # Deprem servisi & DTO
│   ├── fault/                # Fay hattı servisi
│   ├── soil/                 # Zemin zonu servisi
│   └── ai/                   # Groq AI entegrasyonu
│
└── docs/
    └── AI_AGENT_PLANNING.md  # AI Agent planlama dokümanı
```

## Planlama Dokümanı

AI Agent Planlama Dokümanı: [docs/AI_AGENT_PLANNING.md](docs/AI_AGENT_PLANNING.md)

## Lisans

Bu proje eğitim amaçlı geliştirilmiştir.
