"""Seismic MCP server — mounted inside the graph FastAPI service.

The server is exposed over streamable HTTP at /mcp/ by api.py:

    app.mount("/mcp", seismic_mcp.streamable_http_app())

Any MCP host (Claude Desktop, Cursor, another agent) can connect to
http://localhost:8002/mcp/ and discover + call the tools below.

Tools
-----
get_recent_earthquakes      — latest events from Spring /api/earthquakes/recent
get_seismic_context         — nearby recent, historical, and fault context for a point
get_earthquake_detail       — full enrichment for one event (aftershocks, similar, dyfi, shakemap)
get_historical_events       — historical M4.5+ events from Spring /api/historical/events
get_seismic_gaps            — seismic gap analysis from Spring /api/historical/gaps
get_fault_lines             — fault geometry (GeoJSON) for a bounding box
geocode_address             — forward geocoding via Spring /api/geocode/search
assess_building_risk        — deterministic structural + seismic risk score (no LLM)
"""

import asyncio
import math
from typing import Any

from mcp.server.fastmcp import FastMCP

from ..spring_client import SpringClient


mcp = FastMCP(
    "seismic-command-mcp",
    instructions=(
        "Provides earthquake-domain tools for Seismic Command. "
        "All tools read the Spring backend and return structured JSON. "
        "Use get_seismic_context or get_recent_earthquakes for general queries. "
        "Use assess_building_risk for structural safety analysis. "
        "Use get_earthquake_detail for event-level deep dives."
    ),
    streamable_http_path="/",
)


# ---------------------------------------------------------------------------
# Tool: get_recent_earthquakes
# ---------------------------------------------------------------------------

@mcp.tool()
async def get_recent_earthquakes(
    hours: int = 24,
    min_magnitude: float = 1.0,
    limit: int = 8,
) -> dict[str, Any]:
    """Return recent earthquakes from the Spring backend.

    Args:
        hours: Look-back window in hours (1–168).
        min_magnitude: Minimum magnitude threshold (0.0–10.0).
        limit: Maximum number of records to return (1–20).
    """
    hours = _clamp_int(hours, 1, 168)
    min_magnitude = _clamp_float(min_magnitude, 0.0, 10.0)
    limit = _clamp_int(limit, 1, 20)

    client = SpringClient(timeout=8.0)
    try:
        rows = await client.recent_earthquakes(hours=hours, min_magnitude=min_magnitude, limit=limit)
    finally:
        await client.close()

    records = [_compact_quake(row) for row in rows[:limit]]
    strongest = max(records, key=lambda r: r["magnitude"], default=None)
    average = round(sum(r["magnitude"] for r in records) / len(records), 2) if records else 0.0

    return {
        "query": {"hours": hours, "minMagnitude": min_magnitude, "limit": limit},
        "count": len(records),
        "strongest": strongest,
        "averageMagnitude": average,
        "records": records,
        "summary": _recent_summary(records, hours, min_magnitude),
        "source": "Spring /api/earthquakes/recent",
    }


# ---------------------------------------------------------------------------
# Tool: get_seismic_context
# ---------------------------------------------------------------------------

@mcp.tool()
async def get_seismic_context(
    latitude: float,
    longitude: float,
    radius_km: float = 100.0,
) -> dict[str, Any]:
    """Return nearby recent, historical, and fault-line context for a geographic point.

    Args:
        latitude: WGS-84 latitude of the centre point.
        longitude: WGS-84 longitude of the centre point.
        radius_km: Search radius in kilometres (10–300).
    """
    radius_km = _clamp_float(radius_km, 10.0, 300.0)
    bbox = _bbox(latitude, longitude, radius_km)
    client = SpringClient(timeout=12.0)
    try:
        recent_rows, historical_rows, faults = await asyncio.gather(
            client.recent_earthquakes(hours=168, min_magnitude=1.5, limit=500),
            client.historical_events(years=50, min_magnitude=4.5),
            client.fault_lines(bbox=bbox, simplify=0.02),
        )
    finally:
        await client.close()

    nearby_recent = _within_radius(recent_rows, latitude, longitude, radius_km)
    nearby_historical = _within_radius(historical_rows, latitude, longitude, radius_km)
    fault_features = (faults or {}).get("features", []) if isinstance(faults, dict) else []

    return {
        "location": {"latitude": latitude, "longitude": longitude, "radiusKm": radius_km},
        "recentCount7Days": len(nearby_recent),
        "historicalCount50Years": len(nearby_historical),
        "maxRecentMagnitude": _max_magnitude(nearby_recent),
        "maxHistoricalMagnitude": _max_magnitude(nearby_historical),
        "faultFeatureCount": len(fault_features),
        "sampleFaultNames": _sample_fault_names(fault_features),
        "sampleRecent": nearby_recent[:8],
        "sampleHistorical": nearby_historical[:8],
        "summary": (
            f"{len(nearby_recent)} recent and {len(nearby_historical)} historical events "
            f"within {round(radius_km)} km. {len(fault_features)} fault features returned."
        ),
        "source": "Spring earthquake, historical, and fault-line APIs",
    }


# ---------------------------------------------------------------------------
# Tool: get_earthquake_detail
# ---------------------------------------------------------------------------

@mcp.tool()
async def get_earthquake_detail(event_id: str) -> dict[str, Any]:
    """Return full enrichment for a single earthquake event.

    Fetches event metadata, aftershocks, similar historical events,
    Did-You-Feel-It data, and ShakeMap data in parallel.

    Args:
        event_id: The earthquake event ID (e.g. 'us7000m9g4').
    """
    client = SpringClient(timeout=12.0)
    try:
        event, aftershocks, similar, dyfi, shakemap = await asyncio.gather(
            client.earthquake_detail(event_id),
            client.aftershocks(event_id, limit=12),
            client.similar_historical(event_id, limit=8),
            client.dyfi(event_id),
            client.shakemap(event_id),
        )
    finally:
        await client.close()

    if not event:
        return {"error": f"Event '{event_id}' not found.", "eventId": event_id}

    magnitude = float(event.get("magnitude") or 0)
    depth_km = float(event.get("depthKm") or event.get("depth") or 0)
    depth_label = "yüzeysel (<70 km)" if depth_km < 70 else "orta derinlik (70–300 km)" if depth_km < 300 else "derin (>300 km)"

    return {
        "eventId": event_id,
        "event": event,
        "aftershockCount": len(aftershocks),
        "aftershocks": aftershocks,
        "similarHistoricalCount": len(similar),
        "similarHistorical": similar,
        "dyfi": dyfi,
        "shakemap": shakemap,
        "depthLabel": depth_label,
        "riskLevel": "critical" if magnitude >= 7.0 else "high" if magnitude >= 5.0 else "moderate" if magnitude >= 3.0 else "low",
        "summary": (
            f"M{round(magnitude, 1)} event at {round(depth_km)} km depth. "
            f"{len(aftershocks)} aftershocks, {len(similar)} similar historical events. "
            f"DYFI: {'yes' if dyfi else 'no'}, ShakeMap: {'yes' if shakemap else 'no'}."
        ),
        "source": "Spring /api/earthquakes/{eventId} + related endpoints",
    }


# ---------------------------------------------------------------------------
# Tool: get_historical_events
# ---------------------------------------------------------------------------

@mcp.tool()
async def get_historical_events(
    years: int = 50,
    min_magnitude: float = 4.5,
) -> dict[str, Any]:
    """Return historical earthquake events from the Spring backend.

    Args:
        years: How many years back to search (1–100).
        min_magnitude: Minimum magnitude threshold (0.0–10.0).
    """
    years = _clamp_int(years, 1, 100)
    min_magnitude = _clamp_float(min_magnitude, 0.0, 10.0)

    client = SpringClient(timeout=12.0)
    try:
        rows = await client.historical_events(years=years, min_magnitude=min_magnitude)
    finally:
        await client.close()

    records = [_compact_quake(r) for r in rows]
    strongest = max(records, key=lambda r: r["magnitude"], default=None)

    return {
        "query": {"years": years, "minMagnitude": min_magnitude},
        "count": len(records),
        "strongest": strongest,
        "records": records,
        "summary": (
            f"{len(records)} historical M{min_magnitude}+ events in the last {years} years."
            + (f" Strongest: M{strongest['magnitude']} near {strongest['location']}." if strongest else "")
        ),
        "source": "Spring /api/historical/events",
    }


# ---------------------------------------------------------------------------
# Tool: get_seismic_gaps
# ---------------------------------------------------------------------------

@mcp.tool()
async def get_seismic_gaps() -> dict[str, Any]:
    """Return seismic gap analysis from the Spring backend.

    Seismic gaps are fault segments that have not ruptured in a long time
    and may be candidates for future large earthquakes.
    """
    import httpx
    from ..config import SPRING_BASE_URL

    url = f"{SPRING_BASE_URL.rstrip('/')}/api/historical/gaps"
    try:
        async with httpx.AsyncClient(timeout=10.0) as http:
            r = await http.get(url)
            r.raise_for_status()
            data = r.json()
    except Exception as exc:
        return {"error": str(exc), "source": url}

    gaps = data if isinstance(data, list) else data.get("gaps", data.get("features", []))
    return {
        "count": len(gaps) if isinstance(gaps, list) else 0,
        "gaps": gaps,
        "summary": f"{len(gaps)} seismic gap segments returned." if isinstance(gaps, list) else "Seismic gap data returned.",
        "source": "Spring /api/historical/gaps",
    }


# ---------------------------------------------------------------------------
# Tool: get_fault_lines
# ---------------------------------------------------------------------------

@mcp.tool()
async def get_fault_lines(
    min_longitude: float,
    min_latitude: float,
    max_longitude: float,
    max_latitude: float,
    simplify: float = 0.01,
) -> dict[str, Any]:
    """Return active fault line geometry (GeoJSON) for a bounding box.

    Args:
        min_longitude: West boundary of the bounding box.
        min_latitude: South boundary of the bounding box.
        max_longitude: East boundary of the bounding box.
        max_latitude: North boundary of the bounding box.
        simplify: Douglas-Peucker simplification tolerance (0–0.1).
    """
    simplify = _clamp_float(simplify, 0.0, 0.1)
    bbox = (min_longitude, min_latitude, max_longitude, max_latitude)

    client = SpringClient(timeout=10.0)
    try:
        geojson = await client.fault_lines(bbox=bbox, simplify=simplify)
    finally:
        await client.close()

    if not geojson:
        return {"featureCount": 0, "features": [], "source": "Spring /api/fault-lines"}

    features = geojson.get("features", [])
    names = _sample_fault_names(features)

    return {
        "featureCount": len(features),
        "sampleNames": names,
        "geojson": geojson,
        "summary": f"{len(features)} fault features in bbox. Sample names: {', '.join(names) or 'none'}.",
        "source": "Spring /api/fault-lines",
    }


# ---------------------------------------------------------------------------
# Tool: geocode_address
# ---------------------------------------------------------------------------

@mcp.tool()
async def geocode_address(query: str) -> dict[str, Any]:
    """Convert a place name or address to geographic coordinates.

    Args:
        query: Address or place name (e.g. 'İzmir Konak', 'Kandilli Rasathanesi').
    """
    import httpx
    from ..config import SPRING_BASE_URL

    url = f"{SPRING_BASE_URL.rstrip('/')}/api/geocode/search"
    try:
        async with httpx.AsyncClient(timeout=8.0) as http:
            r = await http.get(url, params={"query": query})
            r.raise_for_status()
            data = r.json()
    except Exception as exc:
        return {"error": str(exc), "query": query}

    if isinstance(data, list):
        results = data
    elif isinstance(data, dict) and "results" in data:
        results = data.get("results", [])
    else:
        results = [data]
    first = results[0] if results else None

    return {
        "query": query,
        "resultCount": len(results) if isinstance(results, list) else 0,
        "best": first,
        "results": results[:5] if isinstance(results, list) else results,
        "summary": (
            f"'{query}' → {first.get('displayName', first)}" if first
            else f"No results for '{query}'."
        ),
        "source": "Spring /api/geocode/search",
    }


# ---------------------------------------------------------------------------
# Tool: assess_building_risk
# ---------------------------------------------------------------------------

@mcp.tool()
async def assess_building_risk(
    latitude: float,
    longitude: float,
    construction_year: int,
    floor_count: int,
    soil_type: str = "ZC",
    structural_system: str = "RC",
    visible_damage: bool = False,
    radius_km: float = 100.0,
) -> dict[str, Any]:
    """Deterministic structural + seismic risk assessment for a building.

    Scores are rule-based (no LLM). For a full AI-narrative assessment
    use the /graph/building-risk endpoint instead.

    Scoring components (100 pts total):
    - Structural (0–35): age, floors, system, visible damage
    - Soil (0–15): zone classification ZA–ZF
    - Seismic context (0–30): historical density, fault proximity
    - Observed damage (0–20): visible cracks / past damage reports

    Args:
        latitude: Building latitude.
        longitude: Building longitude.
        construction_year: Year the building was constructed.
        floor_count: Number of floors.
        soil_type: TBDY-2018 soil class (ZA, ZB, ZC, ZD, ZE, ZF).
        structural_system: RC (reinforced concrete), URM (unreinforced masonry), S (steel).
        visible_damage: Whether visible structural damage has been reported.
        radius_km: Radius for seismic context query (10–300 km).
    """
    context = await get_seismic_context(latitude=latitude, longitude=longitude, radius_km=radius_km)

    score = 0
    drivers: list[str] = []

    # --- Structural age ---
    if construction_year < 1975:
        score += 35
        drivers.append(f"1975 öncesi yapı ({construction_year}), modern yönetmelik öncesi")
    elif construction_year < 2000:
        score += 28
        drivers.append(f"2000 öncesi yapı ({construction_year})")
    elif construction_year < 2018:
        score += 14
        drivers.append(f"2018 TBDY öncesi yapı ({construction_year})")

    # --- Floor count ---
    if floor_count >= 8:
        score += 18
        drivers.append(f"Yüksek bina ({floor_count} kat)")
    elif floor_count >= 5:
        score += 9
        drivers.append(f"Orta yükseklikte bina ({floor_count} kat)")

    # --- Structural system ---
    system_penalty = {"RC": 0, "URM": 20, "S": 0}.get(structural_system.upper(), 5)
    score += system_penalty
    if system_penalty:
        drivers.append(f"Yapı sistemi: {structural_system.upper()} (+{system_penalty})")

    # --- Soil classification ---
    soil_risk = {"ZA": 0, "ZB": 4, "ZC": 8, "ZD": 14, "ZE": 20, "ZF": 25}.get(soil_type.upper(), 10)
    score += soil_risk
    if soil_risk >= 8:
        drivers.append(f"Zemin sınıfı {soil_type.upper()} (+{soil_risk})")

    # --- Visible damage ---
    if visible_damage:
        score += 20
        drivers.append("Görünür yapısal hasar rapor edildi")

    # --- Seismic context ---
    if context["historicalCount50Years"] >= 10:
        score += 10
        drivers.append(f"Yüksek tarihsel sismik yoğunluk ({context['historicalCount50Years']} M4.5+ olay)")
    elif context["historicalCount50Years"] >= 5:
        score += 5
        drivers.append(f"Orta tarihsel sismik yoğunluk ({context['historicalCount50Years']} M4.5+ olay)")

    if context["faultFeatureCount"] >= 5:
        score += 10
        drivers.append(f"Aktif fay yoğunluğu yüksek ({context['faultFeatureCount']} fay geometrisi)")
    elif context["faultFeatureCount"] >= 2:
        score += 5
        drivers.append(f"Yakında aktif fay mevcut ({context['faultFeatureCount']} fay geometrisi)")

    score = min(score, 100)
    level = "düşük" if score < 30 else "orta" if score < 55 else "yüksek" if score < 75 else "kritik"

    return {
        "score": score,
        "level": level,
        "drivers": drivers or ["Belirgin yüksek risk sinyali yok"],
        "componentBreakdown": {
            "structural": min(score, 35),
            "soil": soil_risk,
            "seismicContext": min(context["historicalCount50Years"] // 2, 10) + min(context["faultFeatureCount"] * 2, 10),
            "observedDamage": 20 if visible_damage else 0,
        },
        "seismicContext": context,
        "summary": (
            f"Deterministik risk skoru: {score}/100 ({level}). "
            f"Bina: {construction_year}, {floor_count} kat, {soil_type.upper()} zemin. "
            f"LLM tabanlı detaylı analiz için /graph/building-risk endpoint'ini kullanın."
        ),
        "source": "MCP assess_building_risk (deterministic rule engine)",
    }


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _compact_quake(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": str(row.get("id", "")),
        "time": row.get("time"),
        "location": row.get("location") or row.get("place") or "Unknown",
        "magnitude": round(float(row.get("magnitude") or 0), 2),
        "depthKm": round(float(row.get("depthKm") or row.get("depth") or 0), 2),
        "latitude": row.get("latitude"),
        "longitude": row.get("longitude"),
    }


def _recent_summary(records: list[dict[str, Any]], hours: int, min_magnitude: float) -> str:
    if not records:
        return f"No earthquakes found in the last {hours} hours for M{min_magnitude}+."
    strongest = max(records, key=lambda r: r["magnitude"])
    return (
        f"{len(records)} earthquakes in the last {hours} hours (M{min_magnitude}+). "
        f"Strongest: M{strongest['magnitude']} near {strongest['location']}."
    )


def _within_radius(
    rows: list[dict[str, Any]],
    latitude: float,
    longitude: float,
    radius_km: float,
) -> list[dict[str, Any]]:
    nearby = []
    for row in rows:
        lat = row.get("latitude")
        lon = row.get("longitude")
        if lat is None or lon is None:
            continue
        distance = _haversine_km(latitude, longitude, float(lat), float(lon))
        if distance <= radius_km:
            compact = _compact_quake(row)
            compact["distanceKm"] = round(distance, 1)
            nearby.append(compact)
    return sorted(nearby, key=lambda r: r.get("distanceKm", 9999))


def _sample_fault_names(features: list[dict[str, Any]]) -> list[str]:
    names: list[str] = []
    for feature in features:
        props = feature.get("properties") or {}
        name = props.get("name") or props.get("faultName") or props.get("segment") or props.get("Name")
        if name and str(name) not in names:
            names.append(str(name))
        if len(names) == 5:
            break
    return names


def _max_magnitude(rows: list[dict[str, Any]]) -> float | None:
    if not rows:
        return None
    return max(float(row.get("magnitude") or 0) for row in rows)


def _bbox(latitude: float, longitude: float, radius_km: float) -> tuple[float, float, float, float]:
    lat_delta = radius_km / 111.0
    lon_delta = radius_km / (111.0 * max(math.cos(math.radians(latitude)), 0.2))
    return (
        round(longitude - lon_delta, 5),
        round(latitude - lat_delta, 5),
        round(longitude + lon_delta, 5),
        round(latitude + lat_delta, 5),
    )


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    to_rad = math.pi / 180
    dlat = (lat2 - lat1) * to_rad
    dlon = (lon2 - lon1) * to_rad
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(lat1 * to_rad) * math.cos(lat2 * to_rad) * math.sin(dlon / 2) ** 2
    )
    return 6371 * (2 * math.atan2(math.sqrt(a), math.sqrt(1 - a)))


def _clamp_int(value: int, minimum: int, maximum: int) -> int:
    return max(minimum, min(maximum, int(value)))


def _clamp_float(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, float(value)))
