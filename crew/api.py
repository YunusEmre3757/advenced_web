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


@app.post("/analyze", response_model=AgentResult)
async def analyze(req: AnalyzeRequest):
    from seismic_crew.crew import SeismicCrew

    report_date = datetime.now().strftime("%Y-%m-%d %H:%M UTC")

    inputs = {
        "hours": req.hours,
        "min_magnitude": req.minMagnitude,
        "report_date": report_date,
        "backend_url": "http://localhost:8080",
        "event_id": req.eventId,
        "event_location": req.location,
        "event_magnitude": req.magnitude,
        "event_depth_km": req.depthKm,
        "event_latitude": req.latitude,
        "event_longitude": req.longitude,
        "fallback_earthquakes": [
            {
                "id": req.eventId,
                "location": req.location,
                "magnitude": req.magnitude,
                "depthKm": req.depthKm,
                "latitude": req.latitude,
                "longitude": req.longitude,
                "time": datetime.utcnow().isoformat() + "Z",
            }
        ],
    }

    # bbox hints
    lon = req.longitude
    lat = req.latitude
    inputs["event_longitude_minus2"] = round(lon - 2.0, 4)
    inputs["event_latitude_minus2"]  = round(lat - 2.0, 4)
    inputs["event_longitude_plus2"]  = round(lon + 2.0, 4)
    inputs["event_latitude_plus2"]   = round(lat + 2.0, 4)
    inputs["event_longitude_minus1"] = round(lon - 1.0, 4)
    inputs["event_latitude_minus1"]  = round(lat - 1.0, 4)
    inputs["event_longitude_plus1"]  = round(lon + 1.0, 4)
    inputs["event_latitude_plus1"]   = round(lat + 1.0, 4)

    # Pre-fetch USGS historical data — inject into agent context AND
    # keep the computed gap values for direct use in the response
    usgs_ctx, usgs_meta = _fetch_usgs_history(lat, lon)
    inputs["usgs_historical_context"] = usgs_ctx

    crew_output = SeismicCrew().crew().kickoff(inputs=inputs)
    raw = str(crew_output)

    sections = _parse_sections(raw)

    return AgentResult(
        hazardLevel=sections.get("HAZARD_LEVEL", _extract_hazard(raw)).strip(),
        nearestFault=sections.get("NEAREST_FAULT", "Bilinmiyor").strip(),
        distanceKm=_to_float(sections.get("DISTANCE_KM", "0")),
        faultType=sections.get("FAULT_TYPE", "unknown").strip(),
        slipRate=sections.get("SLIP_RATE", "Veri yok").strip(),
        soilClass=sections.get("SOIL_CLASS", _extract_soil(raw)).strip(),
        # Always use Python-computed USGS values — never trust LLM for these
        historicalSummary=usgs_meta["historical_summary"],
        seismicGapStatus=usgs_meta["gap_status"],
        seismicGapNote=usgs_meta["gap_note"],
        dataCollectorSummary=sections.get("DATA_COLLECTOR_SUMMARY", "").strip(),
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
            return "USGS tarihsel veri: Bu bölgede 1990'dan beri M>=4.5 deprem kaydı bulunamadı."

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

import re as _re

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
