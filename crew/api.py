"""
FastAPI wrapper for SeismicCrew.
Runs on http://localhost:8001

Start:
    cd crew
    uvicorn api:app --port 8001 --reload
"""

import os
import sys
import json
import re
import warnings
from datetime import datetime
from typing import Optional

warnings.filterwarnings("ignore", category=SyntaxWarning, module="pysbd")

# load .env
_env_path = os.path.join(os.path.dirname(__file__), ".env")
if os.path.exists(_env_path):
    for _line in open(_env_path):
        _line = _line.strip()
        if _line and not _line.startswith("#") and "=" in _line:
            _k, _v = _line.split("=", 1)
            os.environ.setdefault(_k, _v)

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel

app = FastAPI(title="SeismicCrew API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    import logging
    body = await request.body()
    logging.error(f"422 Validation Error — body: {body.decode()}")
    logging.error(f"Errors: {exc.errors()}")
    return JSONResponse(status_code=422, content={"detail": exc.errors(), "body": body.decode()})


class AnalyzeRequest(BaseModel):
    eventId: str
    location: str
    magnitude: float
    depthKm: float
    latitude: float
    longitude: float
    hours: Optional[int] = 24
    minMagnitude: Optional[float] = 2.0


class AgentResult(BaseModel):
    hazardLevel: str
    nearestFault: str
    distanceKm: float
    faultType: str
    slipRate: str
    soilClass: str
    historicalSummary: str
    seismicGapStatus: str
    seismicGapNote: str
    dataCollectorSummary: str
    faultAnalystReport: str
    riskAssessorReport: str
    finalReport: str
    reportDate: str


@app.get("/health")
def health():
    return {"status": "ok"}


BACKEND_URL = os.environ.get("BACKEND_URL", "http://localhost:8080")


@app.post("/analyze", response_model=AgentResult)
async def analyze(req: AnalyzeRequest):
    from seismic_crew.crew import SeismicCrew

    report_date = datetime.now().strftime("%Y-%m-%d %H:%M UTC")
    lat = req.latitude
    lon = req.longitude

    # ── Pre-fetch REAL data in Python — agents must NOT fabricate these ──────
    #
    # Each helper returns (context_string_for_prompt, structured_meta).
    # The prompt string goes into `inputs` so the LLM reads it verbatim.
    # The structured meta is used directly in the HTTP response, so even if
    # the LLM drifts, the user sees correct numbers.

    usgs_ctx, usgs_meta = _fetch_usgs_history(lat, lon)
    nearby_ctx, nearby_meta = _fetch_nearby_events(
        lat, lon, hours=req.hours or 24, min_magnitude=req.minMagnitude or 2.0,
        focus_event_id=req.eventId,
    )
    faults_ctx, faults_meta = _fetch_nearest_faults(lat, lon)
    soil_ctx, soil_meta = _fetch_soil_class(lat, lon)

    inputs = {
        "hours": req.hours,
        "min_magnitude": req.minMagnitude,
        "report_date": report_date,
        "backend_url": BACKEND_URL,
        "event_id": req.eventId,
        "event_location": req.location,
        "event_magnitude": req.magnitude,
        "event_depth_km": req.depthKm,
        "event_latitude": lat,
        "event_longitude": lon,
        # Pre-computed real data — agents MUST copy these, not invent
        "usgs_historical_context": usgs_ctx,
        "nearby_events_context": nearby_ctx,
        "nearest_faults_context": faults_ctx,
        "soil_class_context": soil_ctx,
        # Scalar shortcuts the LLM can quote directly
        "real_nearest_fault_name": faults_meta["nearest_name"],
        "real_nearest_fault_distance_km": faults_meta["nearest_distance_km"],
        "real_nearest_fault_type": faults_meta["nearest_type"],
        "real_nearest_fault_slip_rate": faults_meta["nearest_slip_rate"],
        "real_soil_class": soil_meta["site_class"],
        "real_soil_vs30": soil_meta["vs30"],
        "real_hazard_level": faults_meta["hazard_level"],
    }

    crew_output = SeismicCrew().crew().kickoff(inputs=inputs)
    raw = str(crew_output)

    sections = _parse_sections(raw)

    # ── Always prefer Python-computed values over LLM output ─────────────────
    # LLM narrative goes into the free-text report fields; scalars come from
    # the pre-fetched data. This is the firewall against hallucination.

    return AgentResult(
        hazardLevel=faults_meta["hazard_level"],
        nearestFault=faults_meta["nearest_name"],
        distanceKm=faults_meta["nearest_distance_km"],
        faultType=faults_meta["nearest_type"],
        slipRate=faults_meta["nearest_slip_rate"],
        soilClass=soil_meta["site_class"],
        historicalSummary=usgs_meta["historical_summary"],
        seismicGapStatus=usgs_meta["gap_status"],
        seismicGapNote=usgs_meta["gap_note"],
        dataCollectorSummary=sections.get("DATA_COLLECTOR_SUMMARY", "").strip() or nearby_meta["summary"],
        faultAnalystReport=sections.get("FAULT_ANALYST_REPORT", "").strip(),
        riskAssessorReport=sections.get("RISK_ASSESSOR_REPORT", "").strip(),
        finalReport=sections.get("FINAL_REPORT", raw).strip(),
        reportDate=report_date,
    )


# ── helpers ──────────────────────────────────────────────────────────────────

def _fetch_usgs_history(lat: float, lon: float) -> tuple[str, dict]:
    """Fetch real historical M>=4.5 earthquakes from USGS FDSN API.
    Returns a pre-formatted string injected into agent context.
    Agents must use this data — never invent historical earthquakes."""
    import urllib.request as _ur
    from datetime import datetime as _dt

    url = (
        "https://earthquake.usgs.gov/fdsnws/event/1/query?format=geojson"
        f"&minmagnitude=4.5"
        f"&minlatitude={round(lat-2,4)}&maxlatitude={round(lat+2,4)}"
        f"&minlongitude={round(lon-2,4)}&maxlongitude={round(lon+2,4)}"
        "&starttime=1990-01-01&orderby=time&limit=50"
    )
    try:
        req = _ur.Request(url, headers={"User-Agent": "SeismicCrew/1.0"})
        with _ur.urlopen(req, timeout=15) as r:
            data = json.load(r)

        features = data.get("features", [])
        if not features:
            empty_meta = {
                "gap_status": "DUZENLI_AKTIVITE",
                "gap_note": "1990'dan beri M>=4.5 deprem kaydı yok.",
                "historical_summary": "Tarihsel M≥4.5 deprem kaydı yok (USGS, 1990+, ±2°).",
            }
            return ("USGS tarihsel veri: Bu bölgede 1990'dan beri M>=4.5 deprem kaydı bulunamadı.",
                    empty_meta)

        events = []
        for f in features:
            p = f["properties"]
            t = _dt.fromtimestamp(p["time"] / 1000).strftime("%Y-%m-%d")
            events.append({
                "date": t,
                "mag": p["mag"],
                "place": p.get("place", ""),
            })

        # compute seismic gap
        m55_events = [e for e in events if e["mag"] >= 5.5]
        last_m55 = m55_events[0] if m55_events else None
        max_event = max(events, key=lambda e: e["mag"])

        now_year = _dt.now().year
        if last_m55:
            last_year = int(last_m55["date"][:4])
            silence_years = now_year - last_year
            if silence_years > 20:
                gap_status = "UZUN_SESSIZLIK"
                gap_note = (f"Son M>=5.5 deprem {last_m55['date']} tarihinde "
                           f"M{last_m55['mag']} olarak gerçekleşti ({silence_years} yıl önce). "
                           f"Uzun süreli sessizlik — bölge enerji biriktiriyor olabilir.")
            elif silence_years <= 3:
                gap_status = "YAKIN_KIRILMA"
                gap_note = (f"Son M>=5.5 deprem {last_m55['date']} tarihinde "
                           f"M{last_m55['mag']} ile yakın zamanda gerçekleşti ({silence_years} yıl önce). "
                           f"Artçı sismik aktivite devam edebilir.")
            else:
                gap_status = "DUZENLI_AKTIVITE"
                gap_note = (f"Son M>=5.5 deprem {last_m55['date']} tarihinde "
                           f"M{last_m55['mag']} olarak gerçekleşti ({silence_years} yıl önce). "
                           f"Bölge düzenli sismik aktivite gösteriyor.")
        else:
            gap_status = "DUZENLI_AKTIVITE"
            gap_note = "1990'dan beri M>=5.5 deprem kaydı yok. Bölge düşük-orta aktivite gösteriyor."

        lines = [
            f"=== USGS GERÇEK TARİHSEL VERİ (1990-günümüz, ±2° bbox) ===",
            f"KAYNAK: USGS FDSN API (earthquake.usgs.gov) — gerçek veri, uydurma değil",
            f"Toplam M>=4.5 deprem sayısı: {len(events)}",
            f"En büyük deprem: M{max_event['mag']} — {max_event['date']} — {max_event['place']}",
            f"Son M>=5.5: {last_m55['date'] + ' M' + str(last_m55['mag']) if last_m55 else 'Yok (1990+)'}",
            f"Sismik boşluk durumu: {gap_status}",
            f"",
            f"Son 10 deprem (büyükten küçüğe):",
        ]
        for e in sorted(events[:10], key=lambda x: x["mag"], reverse=True):
            lines.append(f"  {e['date']} | M{e['mag']} | {e['place']}")

        hist_summary = (
            f"Son 35 yılda {len(events)} adet M≥4.5 deprem. "
            f"En büyük: M{max_event['mag']} ({max_event['date'][:4]}). "
            f"Son M≥5.5: {last_m55['date'] + ' M' + str(last_m55['mag']) if last_m55 else 'Kayıt yok'}."
        )

        lines += [
            f"",
            f"ZORUNLU: Yukarıdaki tarihler ve büyüklükler GERÇEK USGS verisinden gelmiştir.",
            f"Bu verileri AYNEN kullan. Farklı tarih veya büyüklük UYDURMA.",
            f"SEISMIC_GAP_STATUS: {gap_status}",
            f"SEISMIC_GAP_NOTE: {gap_note}",
        ]
        meta = {
            "gap_status": gap_status,
            "gap_note": gap_note,
            "historical_summary": hist_summary,
        }
        return "\n".join(lines), meta

    except Exception as e:
        meta = {
            "gap_status": "BILINMIYOR",
            "gap_note": f"USGS verisi alınamadı: {e}",
            "historical_summary": "Tarihsel veri alınamadı.",
        }
        return f"USGS veri çekme hatası: {e}. Tarihsel analiz yapılamadı.", meta


# ── Real data from local Spring Boot backend ────────────────────────────────
#
# These helpers replace LLM guesswork with deterministic Python computation.
# Each one calls the backend, does geometry/stat math, and returns BOTH a
# human-readable prompt block (for the LLM) AND a structured dict (for the
# HTTP response). The pattern mirrors _fetch_usgs_history above.


def _http_get_json(url: str, timeout: int = 10):
    import urllib.request as _ur
    req = _ur.Request(url, headers={"User-Agent": "SeismicCrew/1.0"})
    with _ur.urlopen(req, timeout=timeout) as r:
        return json.load(r)


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    import math
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def _point_line_distance_km(lat: float, lon: float, coords) -> float:
    """Minimum distance from point to a LineString / MultiLineString vertices.
    Good enough for Turkey-scale fault proximity (±10% vs exact geodesic)."""
    best = float("inf")
    # Flatten MultiLineString -> list of LineStrings
    lines = coords if (coords and isinstance(coords[0][0], list)) else [coords]
    for line in lines:
        for pt in line:
            if len(pt) < 2:
                continue
            d = _haversine_km(lat, lon, pt[1], pt[0])
            if d < best:
                best = d
    return best


def _hazard_from_distance(d_km: float) -> str:
    if d_km < 5:    return "CRITICAL"
    if d_km < 15:   return "HIGH"
    if d_km < 35:   return "MODERATE"
    return "LOW"


def _parse_triple(raw):
    """Fault GeoJSON stores ranges like '(0.2\n0.1\n0.4)' — extract primary value."""
    if not raw or not isinstance(raw, str):
        return None
    m = re.search(r"-?\d+(?:\.\d+)?", raw)
    return float(m.group(0)) if m else None


def _fetch_nearby_events(lat: float, lon: float, hours: int,
                         min_magnitude: float, focus_event_id: str) -> tuple[str, dict]:
    """Fetch real recent earthquakes from the Spring backend, filter to a
    ±2° bbox around the focus event, and summarise the cluster."""
    try:
        url = (f"{BACKEND_URL}/api/earthquakes/recent"
               f"?hours={hours}&minMagnitude={min_magnitude}&limit=500")
        data = _http_get_json(url, timeout=10)

        nearby = []
        for e in data or []:
            elat = e.get("latitude")
            elon = e.get("longitude")
            if elat is None or elon is None:
                continue
            if abs(elat - lat) > 2.0 or abs(elon - lon) > 2.0:
                continue
            if e.get("id") == focus_event_id:
                continue
            d = _haversine_km(lat, lon, elat, elon)
            nearby.append({
                "id": e.get("id"),
                "location": e.get("location", ""),
                "magnitude": float(e.get("magnitude", 0)),
                "depthKm": float(e.get("depthKm", 0)),
                "time": e.get("time", ""),
                "distance_km": round(d, 2),
            })

        nearby.sort(key=lambda x: x["distance_km"])
        top = nearby[:8]

        count = len(nearby)
        max_mag = max((n["magnitude"] for n in nearby), default=0.0)
        avg_mag = (sum(n["magnitude"] for n in nearby) / count) if count else 0.0
        within_30 = sum(1 for n in nearby if n["distance_km"] <= 30)

        lines = [
            "=== GERÇEK YAKIN DEPREMLER (son {}h, ±2° bbox, M≥{}) ===".format(
                hours, min_magnitude),
            "KAYNAK: Kandilli/KOERI — localhost:8080/api/earthquakes/recent",
            f"Toplam yakın olay: {count} | 30 km içinde: {within_30}",
            f"Maksimum büyüklük: M{max_mag:.1f} | Ortalama: M{avg_mag:.2f}",
            "",
            "En yakın 8 olay (mesafeye göre):",
        ]
        for n in top:
            lines.append(
                f"  {n['time'][:16]} | M{n['magnitude']:.1f} | "
                f"{n['depthKm']:.0f}km | {n['distance_km']} km uzakta | {n['location']}"
            )

        summary = (
            f"Son {hours} saatte {count} yakın olay kaydedildi "
            f"(maks M{max_mag:.1f}, ortalama M{avg_mag:.2f}, "
            f"30 km içinde {within_30} olay)."
        )

        lines += [
            "",
            "ZORUNLU: Bu sayılar gerçek KOERI verisinden gelmiştir. AYNEN kullan.",
            "Yakın olay sayısını veya büyüklükleri UYDURMA.",
        ]

        return "\n".join(lines), {
            "count": count,
            "max_magnitude": max_mag,
            "avg_magnitude": avg_mag,
            "within_30km": within_30,
            "top": top,
            "summary": summary,
        }

    except Exception as e:
        meta = {"count": 0, "max_magnitude": 0.0, "avg_magnitude": 0.0,
                "within_30km": 0, "top": [],
                "summary": f"Yakın deprem verisi alınamadı: {e}"}
        return f"Yakın deprem verisi alınamadı: {e}", meta


def _fetch_nearest_faults(lat: float, lon: float) -> tuple[str, dict]:
    """Fetch real MTA fault segments around the focus event and compute the
    top-5 nearest by haversine distance. No LLM guesswork — every fault name
    and distance is real."""
    try:
        # ±1.5° ≈ 165 km buffer is plenty for "nearest fault" reasoning
        d_buf = 1.5
        bbox = f"{lon-d_buf},{lat-d_buf},{lon+d_buf},{lat+d_buf}"
        url = f"{BACKEND_URL}/api/fault-lines?bbox={bbox}&simplify=0.004"
        data = _http_get_json(url, timeout=12)

        features = (data or {}).get("features", [])
        if not features:
            meta = {"nearest_name": "Bilinmiyor",
                    "nearest_distance_km": 999.0,
                    "nearest_type": "unknown",
                    "nearest_slip_rate": "Veri yok",
                    "hazard_level": "LOW",
                    "top5": []}
            return ("Fay verisi bulunamadı (bbox içinde segment yok). "
                    "Tehlike seviyesi: LOW.", meta)

        ranked = []
        for f in features:
            geom = f.get("geometry") or {}
            props = f.get("properties") or {}
            if geom.get("type") not in ("LineString", "MultiLineString"):
                continue
            coords = geom.get("coordinates") or []
            if not coords:
                continue
            d = _point_line_distance_km(lat, lon, coords)

            name = (props.get("name") or props.get("fs_name")
                    or props.get("catalog_id") or "Adsız fay segmenti")
            slip_type = props.get("slip_type") or "unknown"
            slip_rate = _parse_triple(props.get("net_slip_rate")) \
                        or _parse_triple(props.get("strike_slip_rate"))
            slip_rate_str = (f"{slip_rate:.2f} mm/yr"
                             if slip_rate is not None else "Veri yok")

            ranked.append({
                "name": str(name),
                "distance_km": round(d, 2),
                "slip_type": str(slip_type),
                "slip_rate": slip_rate_str,
            })

        ranked.sort(key=lambda x: x["distance_km"])
        top5 = ranked[:5]

        if not top5:
            meta = {"nearest_name": "Bilinmiyor", "nearest_distance_km": 999.0,
                    "nearest_type": "unknown", "nearest_slip_rate": "Veri yok",
                    "hazard_level": "LOW", "top5": []}
            return "Değerlendirilebilir fay geometrisi yok.", meta

        nearest = top5[0]
        hazard = _hazard_from_distance(nearest["distance_km"])

        lines = [
            "=== GERÇEK EN YAKIN FAY SEGMENTLERİ (MTA aktif fay veritabanı) ===",
            "KAYNAK: localhost:8080/api/fault-lines — her mesafe Python haversine ile hesaplandı",
            f"En yakın fay: {nearest['name']} — {nearest['distance_km']} km",
            f"Tip: {nearest['slip_type']} | Kayma hızı: {nearest['slip_rate']}",
            f"Mesafe eşiğine göre TEHLİKE SEVİYESİ: {hazard} "
            "(CRITICAL<5km, HIGH<15km, MODERATE<35km, LOW≥35km)",
            "",
            "Top-5 yakın fay:",
        ]
        for i, f in enumerate(top5, 1):
            lines.append(
                f"  {i}. {f['name']} — {f['distance_km']} km — "
                f"{f['slip_type']} — {f['slip_rate']}"
            )
        lines += [
            "",
            "ZORUNLU: Bu fay isimleri ve mesafeler GERÇEK MTA verisidir. AYNEN kullan.",
            "Başka fay ismi veya farklı mesafe UYDURMA.",
            f"HAZARD_LEVEL: {hazard}",
            f"NEAREST_FAULT: {nearest['name']}",
            f"DISTANCE_KM: {nearest['distance_km']}",
            f"FAULT_TYPE: {nearest['slip_type']}",
            f"SLIP_RATE: {nearest['slip_rate']}",
        ]

        meta = {
            "nearest_name": nearest["name"],
            "nearest_distance_km": nearest["distance_km"],
            "nearest_type": nearest["slip_type"],
            "nearest_slip_rate": nearest["slip_rate"],
            "hazard_level": hazard,
            "top5": top5,
        }
        return "\n".join(lines), meta

    except Exception as e:
        meta = {"nearest_name": "Bilinmiyor", "nearest_distance_km": 999.0,
                "nearest_type": "unknown", "nearest_slip_rate": "Veri yok",
                "hazard_level": "LOW", "top5": []}
        return f"Fay verisi alınamadı: {e}", meta


def _fetch_soil_class(lat: float, lon: float) -> tuple[str, dict]:
    """Fetch real soil zones from backend and find the polygon containing
    the focus point. Zones are axis-aligned bbox polygons (Vs30 grid cells)."""
    try:
        d_buf = 0.1
        bbox = f"{lon-d_buf},{lat-d_buf},{lon+d_buf},{lat+d_buf}"
        url = f"{BACKEND_URL}/api/soil-zones?bbox={bbox}"
        data = _http_get_json(url, timeout=10)

        features = (data or {}).get("features", [])
        for f in features:
            geom = f.get("geometry") or {}
            if geom.get("type") != "Polygon":
                continue
            coords = geom.get("coordinates") or []
            if not coords or not coords[0]:
                continue
            ring = coords[0]
            xs = [p[0] for p in ring if len(p) >= 2]
            ys = [p[1] for p in ring if len(p) >= 2]
            if not xs or not ys:
                continue
            if min(xs) <= lon <= max(xs) and min(ys) <= lat <= max(ys):
                props = f.get("properties") or {}
                site_class = str(props.get("siteClass") or "?")
                vs30 = props.get("vs30")
                vs30_str = f"{vs30:.0f} m/s" if isinstance(vs30, (int, float)) else "Veri yok"

                amp = {
                    "ZA": "düşük amplifikasyon (kaya)",
                    "ZB": "düşük amplifikasyon (sağlam zemin)",
                    "ZC": "orta amplifikasyon (yoğun/sıkı zemin)",
                    "ZD": "yüksek amplifikasyon (orta zemin)",
                    "ZE": "çok yüksek amplifikasyon (yumuşak zemin)",
                    "ZF": "özel değerlendirme gerekir (problem zemin)",
                }.get(site_class, "bilinmiyor")

                text = (
                    "=== GERÇEK ZEMİN SINIFI (TBEC Vs30 haritası) ===\n"
                    "KAYNAK: localhost:8080/api/soil-zones — epicenter polygonda\n"
                    f"Zemin sınıfı: {site_class} | Vs30: {vs30_str}\n"
                    f"Davranış: {amp}\n\n"
                    "ZORUNLU: Bu zemin sınıfı GERÇEK veridir. Farklı sınıf UYDURMA.\n"
                    f"SOIL_CLASS: {site_class}"
                )
                return text, {"site_class": site_class,
                              "vs30": vs30 if isinstance(vs30, (int, float)) else None,
                              "description": amp}

        # No polygon contained the point
        return ("Zemin sınıfı verisi yok (grid hücresi bulunamadı). "
                "Varsayılan: ZC (orta).",
                {"site_class": "ZC", "vs30": None,
                 "description": "varsayılan — gerçek veri yok"})

    except Exception as e:
        return (f"Zemin verisi alınamadı: {e}",
                {"site_class": "?", "vs30": None,
                 "description": f"hata: {e}"})


_re = re

_SECTION_HEADERS = [
    "HAZARD_LEVEL", "NEAREST_FAULT", "DISTANCE_KM", "FAULT_TYPE", "SLIP_RATE",
    "TOP_5_FAULTS", "HISTORICAL_SUMMARY", "SEISMIC_GAP_STATUS", "SEISMIC_GAP_NOTE",
    "FAULT_ACTIVITY", "INTERPRETATION",
    "SOIL_CLASS", "RISK_SCORE", "DATA_COLLECTOR_SUMMARY",
    "FAULT_ANALYST_REPORT", "RISK_ASSESSOR_REPORT", "FINAL_REPORT",
    "CONFIDENCE_LEVEL",
]


def _parse_sections(text: str) -> dict:
    """Extract section values from agent output.

    Handles multiple formats the LLM might produce:
      ## SECTION_NAME\n...content...
      # SECTION_NAME:\n...content...
      # SECTION_NAME:\nlong text\nSECTION_NAME: actual_value   ← inline at end
    """
    result = {}
    headers_pat = "|".join(_SECTION_HEADERS)

    # 1. Block sections: ## HEADER or # HEADER: followed by content
    block_pat = _re.compile(
        r"(?:##?)\s+(" + headers_pat + r"):?\s*\n(.*?)(?=(?:##?)\s+(?:"
        + headers_pat + r")|\Z)",
        _re.DOTALL,
    )
    for m in block_pat.finditer(text):
        key = m.group(1)
        body = m.group(2).strip()

        # If the block ends with "KEY: value" line, prefer that clean value
        inline = _re.search(
            r"(?:^|\n)" + key + r":\s*(.+?)(?:\n|$)", body
        )
        if inline:
            clean = inline.group(1).strip()
            # Only use inline value for short scalar fields
            if key in ("HAZARD_LEVEL", "NEAREST_FAULT", "DISTANCE_KM",
                        "FAULT_TYPE", "SLIP_RATE", "SOIL_CLASS",
                        "RISK_SCORE", "SEISMIC_GAP_STATUS", "CONFIDENCE_LEVEL"):
                result[key] = clean
            else:
                result[key] = body
        else:
            result[key] = body

    # 2. Fallback: bare inline "KEY: value" anywhere in text
    for key in _SECTION_HEADERS:
        if key not in result:
            m = _re.search(r"(?:^|\n)" + key + r":\s*(.+?)(?:\n|$)", text)
            if m:
                result[key] = m.group(1).strip()

    return result


def _extract_hazard(text: str) -> str:
    for level in ["CRITICAL", "HIGH", "MODERATE", "LOW"]:
        if level in text:
            return level
    return "UNKNOWN"


def _extract_soil(text: str) -> str:
    match = _re.search(r"\b(ZA|ZB|ZC|ZD|ZE|ZF)\b", text)
    return match.group(1) if match else "?"


def _to_float(s: str) -> float:
    try:
        return float(_re.sub(r"[^\d.]", "", s.split()[0]))
    except Exception:
        return 0.0
