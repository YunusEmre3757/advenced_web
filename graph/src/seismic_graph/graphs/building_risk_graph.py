"""Building-risk graph — agentic evaluation loop (ed-donner pattern).

Graph topology — mirrors sidekick.py's worker→evaluator feedback loop:

    START
      │
      ▼
  collect_context   ← parallel asyncio.gather: fault lines + historical + recent
      │
      ▼
    score           ← deterministic rule engine (no LLM), sets totalScore
      │
      ├─ score < 20  ──► brief_analysis
      ├─ 20 ≤ score < 70 ──► standard_analysis
      └─ score ≥ 70  ──► deep_analysis
              │
              ▼
          evaluator   ← LLM judges its own output (ed-donner pattern)
              │
              ├─ quality OK or retries exhausted ──► END
              └─ needs improvement ──► score (retry, max 2 turns)
"""

from __future__ import annotations

import asyncio
import math
from datetime import datetime, timezone
from typing import Any, Literal, TypedDict

from pydantic import BaseModel, Field
from langgraph.graph import END, START, StateGraph

from ..config import DRY_RUN
from ..llm import get_llm, get_structured_llm
from ..spring_client import get_spring_client


RiskLevel = Literal["dusuk", "orta", "yuksek", "kritik"]
MAX_RETRIES = 2


# ---------------------------------------------------------------------------
# Pydantic schemas for structured LLM output (ed-donner pattern)
# ---------------------------------------------------------------------------

class BriefAnalysisOutput(BaseModel):
    confidence: Literal["dusuk", "orta", "yuksek"] = Field(
        description="Risk degerlendirmesinin guven duzeyi"
    )
    summary: str = Field(
        description="2-3 cumlelik kisa Turkce ozet. Riskin neden dusuk oldugunu ve ne yapilmasi onerildigini acikla."
    )
    recommendedActions: list[str] = Field(
        description="Tam olarak 2 kisa, dogal Turkce eylem maddesi"
    )


class StandardAnalysisOutput(BaseModel):
    confidence: Literal["dusuk", "orta", "yuksek"] = Field(
        description="Risk degerlendirmesinin guven duzeyi"
    )
    summary: str = Field(
        description="2 kisa paragraf: ilki riskin nedenini, ikincisi ne yapilacagini anlatiyor. Dogal Turkce."
    )
    recommendedActions: list[str] = Field(
        description="Tam olarak 3 kisa, dogal Turkce eylem maddesi"
    )


class DeepAnalysisOutput(BaseModel):
    confidence: Literal["dusuk", "orta", "yuksek"] = Field(
        description="Risk degerlendirmesinin guven duzeyi"
    )
    summary: str = Field(
        description="3 kisa paragraf: yapisal durum, konum/zemin tehlikesi, acil adimlar. Duz metin, markdown yok."
    )
    recommendedActions: list[str] = Field(
        description="Tam olarak 3 somut, oncelikli Turkce eylem maddesi. Her biri tek cumle."
    )
    additionalCautions: list[str] = Field(
        default_factory=list,
        description="Yuksek/kritik risk icin ekstra 1-2 uyari maddesi"
    )


class EvaluatorOutput(BaseModel):
    """Ed-donner pattern: LLM evaluates its own previous output."""
    quality_ok: bool = Field(
        description="True if summary is specific, natural Turkish, covers both building and location factors, and has correct number of recommendedActions."
    )
    feedback: str = Field(
        description="One sentence of specific feedback if quality_ok is False. What is missing or wrong."
    )


# ---------------------------------------------------------------------------
# State — includes retry counter and evaluator feedback (ed-donner pattern)
# ---------------------------------------------------------------------------

class BuildingRiskState(TypedDict, total=False):
    building: dict[str, Any]
    location: dict[str, Any] | None
    context: dict[str, Any]
    componentScores: dict[str, int]
    totalScore: int
    level: RiskLevel
    label: str
    confidence: str
    primaryDrivers: list[str]
    buildingDrivers: list[str]
    locationDrivers: list[str]
    recommendedActions: list[str]
    cautions: list[str]
    summary: str
    sources: list[str]
    # Evaluator loop fields (ed-donner pattern)
    evaluator_feedback: str | None
    retry_count: int


# ---------------------------------------------------------------------------
# Geo helpers
# ---------------------------------------------------------------------------

def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return r * 2 * math.asin(math.sqrt(max(0.0, min(1.0, a))))


def _point_segment_distance_km(lat: float, lon: float, a: list[float], b: list[float]) -> float:
    mean_lat = math.radians((lat + a[1] + b[1]) / 3.0)
    sx, sy = 111.32 * math.cos(mean_lat), 111.32
    px, py = lon * sx, lat * sy
    ax, ay = a[0] * sx, a[1] * sy
    bx, by = b[0] * sx, b[1] * sy
    dx, dy = bx - ax, by - ay
    if abs(dx) < 1e-9 and abs(dy) < 1e-9:
        return math.hypot(px - ax, py - ay)
    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)))
    return math.hypot(px - (ax + t * dx), py - (ay + t * dy))


def _extract_fault_name(feature: dict[str, Any]) -> str:
    props = feature.get("properties") or {}
    for key in ("name", "fault_name", "segment_name", "fs_name", "Name", "FAULT_NAME"):
        v = props.get(key)
        if isinstance(v, str) and v.strip():
            return v.strip()
    pieces = [str(props.get(k) or "").strip() for k in ("catalog_name", "catalog_id") if props.get(k)]
    slip = str(props.get("slip_type") or "").strip()
    if slip:
        pieces.append(slip)
    return " / ".join(pieces) if pieces else "Isimsiz aktif fay segmenti"


def _fault_line_sets(feature: dict[str, Any]) -> list[list[list[float]]]:
    geo = feature.get("geometry") or {}
    coords = geo.get("coordinates") or []
    gtype = geo.get("type")
    if gtype == "LineString":
        return [coords]
    if gtype == "MultiLineString":
        return coords
    return []


def _parse_slip_rate(feat: dict[str, Any]) -> float | None:
    """Extract net_slip_rate (mm/yr) from fault feature properties. Returns None if absent/unparseable."""
    props = feat.get("properties") or {}
    for key in ("net_slip_rate", "slip_rate", "slipRate", "SLIP_RATE"):
        v = props.get(key)
        if v is None:
            continue
        try:
            f = float(str(v).split("/")[0].strip())  # handle "5.0/10.0" ranges → take lower bound
            if f > 0:
                return f
        except Exception:
            continue
    return None


def _nearest_fault_context(lat: float, lon: float, fault_geojson: dict[str, Any] | None) -> dict[str, Any]:
    nearest_d, nearest_name, nearest_feat = None, None, None
    if not fault_geojson:
        return {
            "nearestFaultDistanceKm": None, "nearestFaultName": None,
            "nearestFaultFeature": None, "nearestFaultSlipRateMmYr": None,
        }
    for feat in fault_geojson.get("features", []):
        for line in _fault_line_sets(feat):
            if not isinstance(line, list) or len(line) < 2:
                continue
            for i in range(len(line) - 1):
                s, e = line[i], line[i + 1]
                if not (isinstance(s, list) and isinstance(e, list) and len(s) >= 2 and len(e) >= 2):
                    continue
                d = _point_segment_distance_km(lat, lon, s, e)
                if nearest_d is None or d < nearest_d:
                    nearest_d, nearest_name, nearest_feat = d, _extract_fault_name(feat), feat
    slip_rate = _parse_slip_rate(nearest_feat) if nearest_feat else None
    return {
        "nearestFaultDistanceKm": round(nearest_d, 1) if nearest_d is not None else None,
        "nearestFaultName": nearest_name,
        "nearestFaultFeature": nearest_feat,
        "nearestFaultSlipRateMmYr": slip_rate,
    }


def _event_dist_to_fault(ev: dict[str, Any], feat: dict[str, Any]) -> float | None:
    try:
        elat, elon = float(ev.get("latitude", 0)), float(ev.get("longitude", 0))
    except Exception:
        return None
    nearest = None
    for line in _fault_line_sets(feat):
        if not isinstance(line, list) or len(line) < 2:
            continue
        for i in range(len(line) - 1):
            s, e = line[i], line[i + 1]
            if not (isinstance(s, list) and isinstance(e, list) and len(s) >= 2 and len(e) >= 2):
                continue
            d = _point_segment_distance_km(elat, elon, s, e)
            if nearest is None or d < nearest:
                nearest = d
    return nearest


def _segment_history(fault_feat: dict[str, Any] | None, hist_events: list[dict[str, Any]]) -> dict[str, Any]:
    if not fault_feat:
        return {
            "segmentHistoricalCount": 0, "segmentM5Count": 0, "segmentM6Count": 0,
            "segmentLastM5EventYear": None, "segmentLastM6EventYear": None,
            "segmentYearsSinceM5Event": None, "segmentYearsSinceM6Event": None,
            "segmentQuietSignal": "belirsiz",
            "segmentContextNote": "En yakin fay segmenti icin ayrintili baglam kurulamadı.",
        }
    corridor = [ev for ev in hist_events
                if (d := _event_dist_to_fault(ev, fault_feat)) is not None and d <= 25]
    m5 = [ev for ev in corridor if float(ev.get("magnitude", 0) or 0) >= 5.0]
    m6 = [ev for ev in corridor if float(ev.get("magnitude", 0) or 0) >= 6.0]

    def _latest_year(evs: list[dict]) -> tuple[int | None, int | None]:
        if not evs:
            return None, None
        latest = max(evs, key=lambda ev: str(ev.get("time", "")))
        try:
            year = datetime.fromisoformat(str(latest.get("time", "")).replace("Z", "+00:00")).year
            return year, max(0, datetime.now(timezone.utc).year - year)
        except Exception:
            return None, None

    m5y, y5 = _latest_year(m5)
    m6y, y6 = _latest_year(m6)
    if y5 is None:
        sig, note = "belirsiz", "Bu fay koridoru icin son M5+ olay yili net belirlenemedi."
    elif y6 is not None and y6 >= 60:
        sig, note = "uzun_sureli_sessizlik", "Yakin fay koridorunda gecmiste buyuk olaylar var ve son M6+ uzerinden uzun zaman gecmis gorunuyor."
    elif y5 <= 20:
        sig, note = "yakin_donemde_aktivite", "Yakin fay koridorunda gorece yakin donemde M5+ olay kaydi bulunuyor."
    else:
        sig, note = "orta_duzey_baglamsal", "Yakin fay koridorunda tarihsel aktivite goruluyor; yalnizca baglamsal tehlike gostergesidir."
    return {
        "segmentHistoricalCount": len(corridor), "segmentM5Count": len(m5), "segmentM6Count": len(m6),
        "segmentLastM5EventYear": m5y, "segmentLastM6EventYear": m6y,
        "segmentYearsSinceM5Event": y5, "segmentYearsSinceM6Event": y6,
        "segmentQuietSignal": sig, "segmentContextNote": note,
    }


# ---------------------------------------------------------------------------
# Rule-based score engine (deterministic, no LLM)
# FIX: removed double-counting of softStorey/heavyTopFloor in observedDamage
# FIX: retrofitDone penalty raised from -6 to -12
# FIX: thresholds changed from 25/50/75 to 20/45/70
# ---------------------------------------------------------------------------

def _risk_level(total: int) -> tuple[RiskLevel, str]:
    if total < 20:  return "dusuk",  "Dusuk risk"
    if total < 45:  return "orta",   "Orta risk"
    if total < 70:  return "yuksek", "Yuksek risk"
    return "kritik", "Kritik risk"


def _norm(v: Any, lo: int, hi: int) -> int:
    try:
        return max(lo, min(hi, int(round(float(v)))))
    except Exception:
        return lo


def _building_drivers(building: dict[str, Any]) -> list[str]:
    year = int(building.get("constructionYear", 2005))
    floors = int(building.get("floorCount", 4))
    sys = str(building.get("structuralSystem", "unknown"))
    d: list[str] = []
    if year < 2000:   d.append("Yapi 2000 oncesi mevzuat doneminde insa edilmis gorunuyor.")
    elif year < 2018: d.append("Yapi 2018 oncesi deprem mevzuati donemine ait gorunuyor.")
    if sys == "masonry":   d.append("Tasiyici sistem yigma duvar olarak secildi.")
    elif sys == "unknown": d.append("Tasiyici sistem bilinmedigi icin yapisal yorumun guveni sinirli.")
    if floors >= 10:  d.append("Kat sayisi yuksek oldugu icin yapisal davranis daha kritik olabilir.")
    elif floors >= 6: d.append("Orta-yuksek kat sayisi yapisal etkileri artirabilir.")
    if building.get("columnCracks"):   d.append("Kolon veya kiris catlagi bildirildi.")
    if building.get("pastDamage"):     d.append("Gecmis deprem hasari beyan edildi.")
    if building.get("softStorey"):     d.append("Zemin kat acik veya ticari kullanimli gorunuyor.")
    if building.get("heavyTopFloor"):  d.append("Ust katlara sonradan eklenti oldugu belirtildi.")
    if building.get("irregularShape"): d.append("Plana ait duzensizlik veya asimetri bildirildi.")
    if building.get("retrofitDone"):   d.append("Guclendirme yapildigi beyan edildi; bu etkiyi azaltabilir.")
    return d[:4]


def _location_drivers(building: dict[str, Any], context: dict[str, Any]) -> list[str]:
    soil = str(building.get("soilType", "ZC"))
    dist = context.get("nearestFaultDistanceKm")
    hcount = int(context.get("historicalNearbyCount", 0))
    maxmag = float(context.get("historicalMaxMagnitude", 0.0) or 0.0)
    recent = int(context.get("recentNearbyCount", 0))
    y5 = context.get("segmentYearsSinceM5Event")
    d: list[str] = []
    if soil in {"ZD", "ZE", "ZF"}:
        d.append(f"Zemin sinifi {soil} oldugu icin yerel zemin etkisi daha belirgin olabilir.")
    elif soil == "ZC":
        d.append("Zemin sinifi ZC oldugu icin zemin etkisi orta duzeyde dikkate alinmali.")
    slip_rate = context.get("nearestFaultSlipRateMmYr")
    y6 = context.get("segmentYearsSinceM6Event")
    m6_count = int(context.get("segmentM6Count", 0))
    if dist is not None:
        if float(dist) <= 5:    d.append(f"En yakin aktif fay yaklasik {dist} km mesafede.")
        elif float(dist) <= 15: d.append(f"Yakindaki aktif fay koridoru yaklasik {dist} km mesafede.")
    if slip_rate is not None and float(slip_rate) >= 10:
        d.append(f"En yakin fay yillik ~{slip_rate} mm kayma hizina sahip; stres birikimi yuksek olabilir.")
    if y6 is not None and m6_count > 0 and int(y6) >= 50:
        d.append(f"Fay koridorunda son M6+ olayinin uzerinden yaklasik {y6} yil gecmis; uzun donemli sessizlik dikkat gerektiriyor.")
    if y5 is not None and int(y5) <= 20:
        d.append("Yakin fay koridorunda gorece yakin donemde M5+ olay kaydi bulunuyor.")
    elif hcount >= 8 or maxmag >= 5.5:
        d.append("Yakin cevrede tarihsel olarak dikkat ceken deprem aktivitesi bulunuyor.")
    if recent >= 3:
        d.append("Son gunlerde yakin cevrede birden fazla deprem kaydi izleniyor.")
    return d[:4]


def _fallback_actions(level: RiskLevel, building: dict[str, Any], context: dict[str, Any]) -> list[str]:
    a: list[str] = []
    if building.get("columnCracks") or building.get("pastDamage"):
        a.append("Gorunur hasar icin muhendis gorusu al.")
    elif level in {"yuksek", "kritik"}:
        a.append("Yerinde muhendislik incelemesini onceliklendir.")
    else:
        a.append("Binayi yerinde kontrol ettir ve temel riskleri dogrula.")
    if building.get("retrofitDone"):
        a.append("Mevcut guclendirmenin neyi kapsadigini belgeyle dogrula.")
    elif building.get("softStorey") or building.get("heavyTopFloor") or building.get("irregularShape"):
        a.append("Yapisal zayifliklar icin guclendirme seceneklerini degerlendir.")
    else:
        a.append("Bakim, sabitleme ve acil durum hazirligini guncel tut.")
    dist = context.get("nearestFaultDistanceKm")
    if dist is not None and float(dist) <= 5:
        a.append("Toplanma ve aile haberlesme planini bu konuma gore netlestir.")
    else:
        a.append("Acil durum plani ve toplanma noktasini hazir tut.")
    return a[:3]


def _deterministic_cautions(building: dict[str, Any], context: dict[str, Any], location: dict[str, Any] | None) -> list[str]:
    c: list[str] = []
    if not location:
        c.append("Konum secilmedigi icin fay baglami daha dusuk guvenle yorumlandi.")
    elif location.get("source") == "device":
        c.append("Konum cihaz verisinden alindi; bina adresi ile birebir ortusmeyebilir.")
    if not building.get("addressText"):
        c.append("Adres veya bina notu girilmedigi icin konum baglami kisitli kalabilir.")
    if context.get("segmentLastM5EventYear") is None:
        c.append("Segment icin son M5+ olay yili net belirlenemedi; tarihsel baglam sinirli olabilir.")
    if building.get("structuralSystem") == "unknown":
        c.append("Tasiyici sistem bilinmedigi icin yapisal puan daha belirsizdir.")
    if not c:
        c.append("Bu sonuc deprem tahmini degil, tarihsel ve yapisal tehlike baglamina dayali on degerlendirmedir.")
    return c[:3]


def _compute_scores(building: dict[str, Any], context: dict[str, Any], location: dict[str, Any] | None) -> dict[str, Any]:
    year = int(building.get("constructionYear", 2005))
    floors = int(building.get("floorCount", 4))
    sys = str(building.get("structuralSystem", "unknown"))
    soil = str(building.get("soilType", "ZC"))

    # Structural component (max 35)
    structural = 0
    if year < 1975:    structural += 14
    elif year < 2000:  structural += 10
    elif year < 2018:  structural += 6
    else:              structural += 2
    if floors >= 10:   structural += 8
    elif floors >= 6:  structural += 5
    elif floors >= 4:  structural += 3
    if sys == "masonry":   structural += 10
    elif sys == "unknown": structural += 4
    if building.get("softStorey"):     structural += 7
    if building.get("irregularShape"): structural += 4
    if building.get("heavyTopFloor"):  structural += 3
    # FIX: raised from -6 to -12 — real retrofit halves structural risk
    if building.get("retrofitDone"):   structural -= 12
    structural = _norm(structural, 0, 35)

    # Soil component (max 15)
    soil_map = {"ZA": 1, "ZB": 3, "ZC": 6, "ZD": 10, "ZE": 13, "ZF": 15}
    soil_score = _norm(soil_map.get(soil, 6), 0, 15)

    # Fault proximity component (max 20)
    # Base score from distance
    dist = context.get("nearestFaultDistanceKm")
    if dist is None:          fault = 5
    elif float(dist) <= 5:    fault = 15
    elif float(dist) <= 15:   fault = 12
    elif float(dist) <= 30:   fault = 8
    elif float(dist) <= 60:   fault = 5
    else:                     fault = 2

    # Slip rate bonus: fast-slipping faults accumulate stress faster (NAF=20-30mm/yr)
    # Scientific basis: moment rate ∝ slip_rate × fault_area
    slip_rate = context.get("nearestFaultSlipRateMmYr")
    if slip_rate is not None and dist is not None and float(dist) <= 60:
        sr = float(slip_rate)
        if sr >= 20:    fault += 4   # NAF/EAF class: very fast
        elif sr >= 10:  fault += 3   # fast
        elif sr >= 5:   fault += 2   # moderate
        elif sr >= 1:   fault += 1   # slow but active

    # Seismic gap penalty: long silence on a known active fault = accumulated stress
    # If corridor has M6+ history but last event >50 years ago → elevated hazard
    y6 = context.get("segmentYearsSinceM6Event")
    m6_count = context.get("segmentM6Count", 0)
    if y6 is not None and int(m6_count) > 0:
        gap_years = int(y6)
        if gap_years >= 100:  fault += 5   # century-scale gap (e.g. Istanbul Marmara)
        elif gap_years >= 70: fault += 4
        elif gap_years >= 50: fault += 2   # half-century gap

    fault = _norm(fault, 0, 20)

    # Historical seismicity component (max 15)
    hcount = int(context.get("historicalNearbyCount", 0))
    maxmag = float(context.get("historicalMaxMagnitude", 0.0) or 0.0)
    historical = 2
    if hcount >= 8:    historical += 7
    elif hcount >= 4:  historical += 5
    elif hcount >= 2:  historical += 3
    if maxmag >= 6.5:  historical += 6
    elif maxmag >= 5.5: historical += 4
    elif maxmag >= 4.5: historical += 2
    historical = _norm(historical, 0, 15)

    # Observed damage component (max 20)
    # FIX: only direct physical damage indicators here — softStorey/heavyTopFloor
    # already counted in structural, removed to prevent double-counting
    damage = 0
    if building.get("columnCracks"): damage += 10
    if building.get("pastDamage"):   damage += 8
    damage = _norm(damage, 0, 20)

    component_scores = {
        "structural": structural, "soil": soil_score,
        "faultProximity": fault, "historicalSeismicity": historical,
        "observedDamage": damage,
    }
    total = sum(component_scores.values())
    level, label = _risk_level(total)
    bld_d = _building_drivers(building)
    loc_d = _location_drivers(building, context)
    return {
        "componentScores": component_scores, "totalScore": total,
        "level": level, "label": label,
        "confidence": "orta" if context.get("nearestFaultDistanceKm") is not None else "dusuk",
        "primaryDrivers": (bld_d + loc_d)[:4],
        "buildingDrivers": bld_d,
        "locationDrivers": loc_d,
        "recommendedActions": _fallback_actions(level, building, context),
        "cautions": _deterministic_cautions(building, context, location),
        "summary": "",
        "evaluator_feedback": None,
    }


def _fallback_summary(state: BuildingRiskState) -> str:
    label = state.get("label", "Orta risk")
    total = state.get("totalScore", 0)
    bld_d = state.get("buildingDrivers", [])
    loc_d = state.get("locationDrivers", [])
    key = (bld_d + loc_d)[:3]
    parts = [f"Bu bina icin on degerlendirme {label.lower()} seviyesinde. Toplam skor {total}/100."]
    if key:
        parts.append(f"Skoru en cok {', '.join(key).lower()} etkiliyor.")
    parts.append("Bu sonuc kesin bir muhendislik raporu degil; yerinde kontrol ve uzman gorusu onerilir.")
    return " ".join(parts)


# ---------------------------------------------------------------------------
# Graph nodes
# ---------------------------------------------------------------------------

async def collect_context_node(state: BuildingRiskState) -> BuildingRiskState:
    """Parallel fan-out: fetch fault lines + historical + recent earthquakes at once."""
    building = state.get("building", {})
    location = state.get("location") or {}
    lat = location.get("latitude")
    lon = location.get("longitude")
    sources = ["MTA aktif fay katmani", "USGS tarihsel deprem arsivi", "Kandilli son depremler"]

    if lat is None or lon is None:
        return {
            "context": {
                "nearestFaultDistanceKm": None, "nearestFaultName": None,
                "historicalNearbyCount": 0, "historicalMaxMagnitude": 0.0,
                "recentNearbyCount": 0, "recentMaxMagnitude": 0.0,
                "segmentM5Count": 0, "segmentM6Count": 0,
                "segmentLastM5EventYear": None, "segmentLastM6EventYear": None,
                "segmentYearsSinceM5Event": None, "segmentYearsSinceM6Event": None,
                "segmentContextNote": "Konum olmadan fay koridoru baglami kurulamadı.",
            },
            "sources": sources,
            "retry_count": 0,
        }

    client = get_spring_client()
    # FIX: reduced from 1.0° (~111km) to 0.5° (~55km) — less noise, more relevant data
    delta = 0.5
    bbox = (float(lon) - delta, float(lat) - delta, float(lon) + delta, float(lat) + delta)

    fault_geojson, hist_events, recent_events = await asyncio.gather(
        client.fault_lines(bbox=bbox, simplify=0.008),
        client.historical_events(years=100, min_magnitude=4.5),
        client.recent_earthquakes(hours=168, min_magnitude=3.0, limit=120),
    )

    nearest = _nearest_fault_context(float(lat), float(lon), fault_geojson)
    seg_hist = _segment_history(nearest.get("nearestFaultFeature"), hist_events)

    nearby_hist = [
        ev for ev in hist_events
        if _haversine_km(float(lat), float(lon), float(ev.get("latitude", 0)), float(ev.get("longitude", 0))) <= 120
    ]
    nearby_recent = [
        ev for ev in recent_events
        if _haversine_km(float(lat), float(lon), float(ev.get("latitude", 0)), float(ev.get("longitude", 0))) <= 120
    ]

    return {
        "context": {
            "nearestFaultDistanceKm": nearest.get("nearestFaultDistanceKm"),
            "nearestFaultName": nearest.get("nearestFaultName"),
            "nearestFaultSlipRateMmYr": nearest.get("nearestFaultSlipRateMmYr"),
            "historicalNearbyCount": len(nearby_hist),
            "historicalMaxMagnitude": max((float(ev.get("magnitude", 0) or 0) for ev in nearby_hist), default=0.0),
            "recentNearbyCount": len(nearby_recent),
            "recentMaxMagnitude": max((float(ev.get("magnitude", 0) or 0) for ev in nearby_recent), default=0.0),
            "locationLabel": location.get("label"),
            "soilType": building.get("soilType"),
            **seg_hist,
        },
        "sources": sources,
        "retry_count": 0,
    }


async def score_node(state: BuildingRiskState) -> BuildingRiskState:
    """Rule-based deterministic scoring — no LLM. Sets totalScore used by router."""
    building = state.get("building", {})
    context = state.get("context", {})
    location = state.get("location")
    base = _compute_scores(building, context, location)
    # Preserve retry_count across re-entries from evaluator loop
    base["retry_count"] = state.get("retry_count", 0)
    return base


def _route_by_score(state: BuildingRiskState) -> str:
    """Conditional edge: branch to different LLM analysis nodes based on risk score."""
    total = state.get("totalScore", 0)
    if total < 20:
        return "brief_analysis"
    if total < 70:
        return "standard_analysis"
    return "deep_analysis"


def _build_analysis_prompt_context(state: BuildingRiskState) -> str:
    """Shared context block injected into all analysis prompts."""
    building = state.get("building", {})
    context = state.get("context", {})
    feedback = state.get("evaluator_feedback")
    lines = [
        f"Skor: {state.get('totalScore')}/100 | Seviye: {state.get('level')} | Guven: {state.get('confidence')}",
        f"Bina kaynakli etkenler: {state.get('buildingDrivers', [])}",
        f"Konum/fay etkenler: {state.get('locationDrivers', [])}",
        f"Bina verisi: yapim yili={building.get('constructionYear')}, kat={building.get('floorCount')}, "
        f"sistem={building.get('structuralSystem')}, zemin={building.get('soilType')}, "
        f"catlakvarmı={building.get('columnCracks')}, gecmisHasar={building.get('pastDamage')}, "
        f"yumusatKat={building.get('softStorey')}, guclendirme={building.get('retrofitDone')}",
        f"Zemin/fay: en yakin fay={context.get('nearestFaultDistanceKm')} km ({context.get('nearestFaultName')}), "
        f"kayma hizi={context.get('nearestFaultSlipRateMmYr')} mm/yil, "
        f"tarihsel yakin kayit={context.get('historicalNearbyCount')}, maks mag={context.get('historicalMaxMagnitude')}, "
        f"son M5+ yil={context.get('segmentLastM5EventYear')}, son M6+ uzerinden={context.get('segmentYearsSinceM6Event')} yil",
        f"Sismik bosluk sinyali: {context.get('segmentQuietSignal', 'belirsiz')} — {context.get('segmentContextNote', '')}",
    ]
    if feedback:
        lines.append(f"\nONCEKI DENEME YETERSIZDI. Evaluator geribildirim: {feedback}")
        lines.append("Bu geribildirimi dikkate alarak daha iyi bir analiz yaz.")
    return "\n".join(lines)


_COMMON_RULES = (
    "Kurallar: muhendislik raporu gibi kesin hukum verme; 'on degerlendirme', 'yerinde inceleme' dilini koru. "
    "'bulunmaktadir'/'islemleri yapilmasi' gibi bürokratik kaliplardan kacin. "
    "retrofitDone=true ise 'guclendirme yok' yazma. "
    "observedDamage>0 ise bu bilgiyi ozette mutlaka yansit. "
    "Duz metin; markdown, kalin yazi, madde imi kullanma.\n\n"
)


async def brief_analysis_node(state: BuildingRiskState) -> BuildingRiskState:
    """Low-risk path (score < 20): 2-3 sentence note with structured output."""
    if DRY_RUN:
        return {
            "summary": _fallback_summary(state),
            "confidence": "orta",
        }
    llm = get_structured_llm(BriefAnalysisOutput)
    prompt = (
        "Bina risk on degerlendirmesi dusuk cikti. Kisa, rahatlatici Turkce ozet yaz.\n"
        + _COMMON_RULES
        + _build_analysis_prompt_context(state)
    )
    result: BriefAnalysisOutput = await llm.ainvoke([{"role": "user", "content": prompt}])
    return {
        "summary": result.summary or _fallback_summary(state),
        "confidence": result.confidence or state.get("confidence", "orta"),
        "recommendedActions": result.recommendedActions or state.get("recommendedActions", []),
    }


async def standard_analysis_node(state: BuildingRiskState) -> BuildingRiskState:
    """Medium-risk path (20 ≤ score < 70): 2-paragraph LLM enrichment."""
    if DRY_RUN:
        return {
            "summary": _fallback_summary(state),
            "confidence": "orta",
        }
    llm = get_structured_llm(StandardAnalysisOutput)
    prompt = (
        "Bina risk on degerlendirmesi orta duzeyde cikti. 2 kisa paragraf Turkce ozet yaz:\n"
        "  1. paragraf: riskin nedenini anlat (bina + konum etkenlerini birlestir)\n"
        "  2. paragraf: ne yapilmasi onerilir\n"
        + _COMMON_RULES
        + _build_analysis_prompt_context(state)
    )
    result: StandardAnalysisOutput = await llm.ainvoke([{"role": "user", "content": prompt}])
    return {
        "summary": result.summary or _fallback_summary(state),
        "confidence": result.confidence or state.get("confidence", "orta"),
        "recommendedActions": result.recommendedActions or state.get("recommendedActions", []),
    }


async def deep_analysis_node(state: BuildingRiskState) -> BuildingRiskState:
    """High/critical path (score ≥ 70): 3-paragraph detailed analysis."""
    if DRY_RUN:
        return {
            "summary": _fallback_summary(state),
            "confidence": "dusuk",
        }
    llm = get_structured_llm(DeepAnalysisOutput)
    prompt = (
        "Bina risk on degerlendirmesi yuksek/kritik seviyede cikti. Ayrintili Turkce analiz yaz:\n"
        "  1. paragraf: yapisal durum — hangi bina ozellikleri en cok risk katiyor\n"
        "  2. paragraf: konum ve zemin tehlikesi — fay yakinligi, zemin sinifi, tarihsel aktivite\n"
        "  3. paragraf: acil adimlar — ne yapilmali, kim cagirilmali\n"
        "recommendedActions tam 3 madde. additionalCautions 1-2 onemli uyari.\n"
        + _COMMON_RULES
        + _build_analysis_prompt_context(state)
    )
    result: DeepAnalysisOutput = await llm.ainvoke([{"role": "user", "content": prompt}])
    extra = [c for c in (result.additionalCautions or []) if str(c).strip()][:2]
    merged = (state.get("cautions", []) + extra)[:4]
    return {
        "summary": result.summary or _fallback_summary(state),
        "confidence": result.confidence or state.get("confidence", "dusuk"),
        "recommendedActions": result.recommendedActions or state.get("recommendedActions", []),
        "cautions": merged,
    }


async def evaluator_node(state: BuildingRiskState) -> BuildingRiskState:
    """Ed-donner pattern: LLM evaluates its own previous output.

    Checks if the summary is specific, covers both building and location factors,
    has the right number of recommendedActions, and uses natural Turkish.
    Sets evaluator_feedback so analysis nodes can improve on retry.
    """
    summary = state.get("summary", "")
    actions = state.get("recommendedActions", [])
    level = state.get("level", "orta")
    retry_count = state.get("retry_count", 0)

    # DRY_RUN or already retried max times — accept whatever we have
    if DRY_RUN or retry_count >= MAX_RETRIES:
        return {"evaluator_feedback": None}

    # Fast structural checks before calling LLM (saves tokens for obvious failures)
    min_words = {"dusuk": 15, "orta": 25, "yuksek": 35, "kritik": 35}
    if len(summary.split()) < min_words.get(level, 20):
        return {
            "evaluator_feedback": f"Ozet cok kisa ({len(summary.split())} kelime). Daha ayrintili yaz.",
            "retry_count": retry_count + 1,
        }
    expected_actions = 2 if level == "dusuk" else 3
    if len(actions) < expected_actions:
        return {
            "evaluator_feedback": f"recommendedActions sayisi yetersiz ({len(actions)}/{expected_actions}). Tam sayi gerekli.",
            "retry_count": retry_count + 1,
        }

    # Full LLM evaluation (ed-donner pattern: evaluator_llm judges worker output)
    llm = get_structured_llm(EvaluatorOutput)
    building_drivers = state.get("buildingDrivers", [])
    location_drivers = state.get("locationDrivers", [])
    prompt = (
        "Bir bina risk ozeti kalite degerlendirmesi yap.\n\n"
        f"Risk seviyesi: {level} | Skor: {state.get('totalScore')}/100\n"
        f"Bina etkenler: {building_drivers}\n"
        f"Konum etkenler: {location_drivers}\n\n"
        f"Uretilen ozet:\n{summary}\n\n"
        f"Uretilen eylemler:\n{actions}\n\n"
        "Kalite kriterleri:\n"
        "1. Ozet hem bina hem konum etkenlerini kapsıyor mu?\n"
        "2. Dil dogal Turkce mi? ('bulunmaktadir' gibi bürokratik ifade yok mu?)\n"
        "3. Eger observedDamage>0 ise bu ozetle yansitilmis mi?\n"
        "4. Eylem maddeleri somut ve uygulanabilir mi?\n"
        "quality_ok=True yalnizca TUM kriterler karsilaniyorsa. "
        "quality_ok=False ise feedback alanina tek cumle spesifik geribildirim yaz."
    )
    result: EvaluatorOutput = await llm.ainvoke([{"role": "user", "content": prompt}])

    if result.quality_ok:
        return {"evaluator_feedback": None}

    return {
        "evaluator_feedback": result.feedback,
        "retry_count": retry_count + 1,
    }


def _route_evaluator(state: BuildingRiskState) -> str:
    """Ed-donner pattern: route back to score node for retry, or end if satisfied."""
    feedback = state.get("evaluator_feedback")
    retry_count = state.get("retry_count", 0)
    if feedback and retry_count < MAX_RETRIES:
        return "score"   # re-enter the pipeline with feedback injected into prompt
    return END


# ---------------------------------------------------------------------------
# Graph construction — ed-donner agentic loop pattern
# ---------------------------------------------------------------------------

def build_building_risk_graph():
    g = StateGraph(BuildingRiskState)

    g.add_node("collect_context", collect_context_node)
    g.add_node("score", score_node)
    g.add_node("brief_analysis", brief_analysis_node)
    g.add_node("standard_analysis", standard_analysis_node)
    g.add_node("deep_analysis", deep_analysis_node)
    g.add_node("evaluator", evaluator_node)

    g.add_edge(START, "collect_context")
    g.add_edge("collect_context", "score")

    # Score → analysis branch (conditional edge by score value)
    g.add_conditional_edges(
        "score",
        _route_by_score,
        {
            "brief_analysis": "brief_analysis",
            "standard_analysis": "standard_analysis",
            "deep_analysis": "deep_analysis",
        },
    )

    # All analysis branches → evaluator
    g.add_edge("brief_analysis", "evaluator")
    g.add_edge("standard_analysis", "evaluator")
    g.add_edge("deep_analysis", "evaluator")

    # Evaluator → retry (back to score) or END (ed-donner feedback loop)
    g.add_conditional_edges(
        "evaluator",
        _route_evaluator,
        {
            "score": "score",
            END: END,
        },
    )

    return g.compile()


_compiled = None


def get_building_risk_graph():
    global _compiled
    if _compiled is None:
        _compiled = build_building_risk_graph()
    return _compiled
