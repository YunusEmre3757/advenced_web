"""Quake-detail graph — parallel fan-out, magnitude-gated routing, narrative synthesis.

Graph topology (ed-donner style: START, conditional edges, structured output):

    START
      │
      ▼
   fan_out   ← asyncio.gather: event detail + aftershocks + similar historical
      │
      ├─ mag < 3.0  ──► synthesize_brief    (1 short paragraph)
      ├─ 3.0 ≤ mag < 5.0 ──► synthesize_standard  (3 paragraphs)
      └─ mag ≥ 5.0  ──► synthesize_detailed  (4 paragraphs + op note)
                │
                └─────► END
"""

import asyncio
from typing import Literal, TypedDict

from pydantic import BaseModel, Field
from langgraph.graph import END, START, StateGraph

from ..llm import get_llm, get_structured_llm
from ..spring_client import get_spring_client


Depth = Literal["brief", "standard", "detailed"]


# ---------------------------------------------------------------------------
# Pydantic schemas for structured LLM output
# ---------------------------------------------------------------------------

class BriefSynthesisOutput(BaseModel):
    summary: str = Field(description="1 kisa paragraf, 2-3 cumle. Sismolojik olarak dikkatli ton.")
    risk_level: Literal["low", "moderate", "high", "critical"] = Field(description="Risk seviyesi")
    recommendations: list[str] = Field(description="1 somut eylem maddesi")


class StandardSynthesisOutput(BaseModel):
    summary: str = Field(description="3 kisa paragraf: durum, artci adayi filtresi, tarihsel baglam. Duz metin.")
    risk_level: Literal["low", "moderate", "high", "critical"] = Field(description="Risk seviyesi")
    recommendations: list[str] = Field(description="2 somut eylem maddesi")


class DetailedSynthesisOutput(BaseModel):
    summary: str = Field(description="4 kisa paragraf: durum, artci adayi filtresi, tarihsel baglam, operasyon notu. Duz metin.")
    risk_level: Literal["low", "moderate", "high", "critical"] = Field(description="Risk seviyesi")
    recommendations: list[str] = Field(description="3 somut, oncelikli eylem maddesi")


# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------

class QuakeDetailState(TypedDict, total=False):
    eventId: str
    event: dict
    aftershocks: list[dict]
    similar: list[dict]
    shakemap: dict | None
    depth: Depth
    summary: str
    risk_level: str
    recommendations: list[str]


# ---------------------------------------------------------------------------
# Nodes
# ---------------------------------------------------------------------------

async def fan_out_node(state: QuakeDetailState) -> QuakeDetailState:
    """Parallel fetch: event detail, aftershocks, similar historical, ShakeMap."""
    client = get_spring_client()
    event_id = state["eventId"]

    detail, after, similar, shakemap = await asyncio.gather(
        client.earthquake_detail(event_id),
        client.aftershocks(event_id, 16),
        client.similar_historical(event_id, 10),
        client.shakemap(event_id),
    )
    event = (detail or {}).get("event") if detail else None
    return {
        "event": event or {},
        "aftershocks": after or (detail or {}).get("aftershocks", []) or [],
        "similar": similar or (detail or {}).get("similarHistorical", []) or [],
        "shakemap": shakemap,
    }


def _route_by_magnitude(state: QuakeDetailState) -> str:
    """Conditional edge: branch synthesis node based on earthquake magnitude."""
    mag = float(state.get("event", {}).get("magnitude", 0))
    if mag >= 5.0:
        return "synthesize_detailed"
    if mag >= 3.0:
        return "synthesize_standard"
    return "synthesize_brief"


def _build_shakemap_line(sm: dict | None) -> str:
    if not sm:
        return "ShakeMap mevcut degil (kucuk veya istasyon kapsamı disinda olay)."
    parts = []
    if sm.get("maxMmi") is not None:
        parts.append(f"maks. sarsinti siddet MMI={sm['maxMmi']:.1f}")
    if sm.get("maxPga") is not None:
        parts.append(f"maks. PGA={sm['maxPga']:.3f}g")
    if sm.get("maxPgv") is not None:
        parts.append(f"maks. PGV={sm['maxPgv']:.1f} cm/s")
    if sm.get("mapStatus"):
        parts.append(f"durum={sm['mapStatus']}")
    return "ShakeMap: " + (", ".join(parts) if parts else "veri var ama degerler bos.")


def _build_base_context(state: QuakeDetailState) -> tuple[dict, str, str, str]:
    ev = state.get("event", {})
    after = state.get("aftershocks", [])
    similar = state.get("similar", [])
    sm = state.get("shakemap")
    after_line = ", ".join(f"M{a.get('magnitude')}" for a in after[:5]) or "bu filtrede kayit yok"
    similar_line = ", ".join(
        f"M{s.get('magnitude')} {str(s.get('place', '?'))[:30]}" for s in similar[:3]
    ) or "kayit yok"
    shakemap_line = _build_shakemap_line(sm)
    return ev, after_line, similar_line, shakemap_line


_COMMON_RULES = (
    "Yalnizca duz metin yaz; markdown, kalin yazi, madde imi veya baslik etiketi kullanma. "
    "Sismolojik olarak dikkatli ol: 'artci' yerine gerekli yerlerde 'artci adayi' de. "
    "Eger veri filtre tabanliysa bunu belirt. "
    "Cikarsal cumlelerde 'gosteriyor' yerine 'dusunduruyor' veya 'isaret ediyor' kullan. "
    "Ilk verilerin degisebilecegini ima eden dikkatli bir ton koru. "
    "Su an icin artci yok deme; 'bu zaman ve mesafe filtresinde artci adayi kaydi gorunmuyor' de."
)


async def synthesize_brief_node(state: QuakeDetailState) -> QuakeDetailState:
    """Low-magnitude path: 1 short paragraph."""
    ev, after_line, similar_line, shakemap_line = _build_base_context(state)
    mag = float(ev.get("magnitude", 0))

    if not ev:
        return {"summary": "Olay detayi alinamadi.", "risk_level": "low", "recommendations": ["Rutin izleme yeterli."]}

    llm = get_structured_llm(BriefSynthesisOutput)
    prompt = (
        f"Deprem olayini Turkce ozetle. Abartma, panikletme, kesin hukum kurma. {_COMMON_RULES}\n"
        f"Uzunluk: 1 kisa paragraf, 2-3 cumle.\n\n"
        f"Olay: M{mag} {ev.get('location')}, derinlik {ev.get('depthKm')} km, ({ev.get('latitude')}, {ev.get('longitude')}).\n"
        f"Artci adayi filtresi sonucu: {after_line}.\n"
        f"Benzer tarihsel: {similar_line}.\n"
        f"{shakemap_line}\n"
    )
    result: BriefSynthesisOutput = await llm.ainvoke([{"role": "user", "content": prompt}])
    return {
        "summary": result.summary,
        "risk_level": result.risk_level,
        "recommendations": result.recommendations,
        "depth": "brief",
    }


async def synthesize_standard_node(state: QuakeDetailState) -> QuakeDetailState:
    """Medium-magnitude path: 3 paragraphs."""
    ev, after_line, similar_line, shakemap_line = _build_base_context(state)
    mag = float(ev.get("magnitude", 0))

    if not ev:
        return {"summary": "Olay detayi alinamadi.", "risk_level": "moderate", "recommendations": ["Bolge icin son kayitlari takip et."]}

    llm = get_structured_llm(StandardSynthesisOutput)
    prompt = (
        f"Deprem olayini Turkce ozetle. Abartma, panikletme, kesin hukum kurma. {_COMMON_RULES}\n"
        f"Uzunluk: 3 kisa paragraf — durum, artci adayi filtresi, tarihsel baglam.\n\n"
        f"Olay: M{mag} {ev.get('location')}, derinlik {ev.get('depthKm')} km, ({ev.get('latitude')}, {ev.get('longitude')}).\n"
        f"Artci adayi filtresi sonucu: {after_line}.\n"
        f"Benzer tarihsel: {similar_line}.\n"
        f"{shakemap_line}\n"
    )
    result: StandardSynthesisOutput = await llm.ainvoke([{"role": "user", "content": prompt}])
    return {
        "summary": result.summary,
        "risk_level": result.risk_level,
        "recommendations": result.recommendations,
        "depth": "standard",
    }


async def synthesize_detailed_node(state: QuakeDetailState) -> QuakeDetailState:
    """High-magnitude path: 4 paragraphs including operational note."""
    ev, after_line, similar_line, shakemap_line = _build_base_context(state)
    mag = float(ev.get("magnitude", 0))

    if not ev:
        return {"summary": "Olay detayi alinamadi.", "risk_level": "high", "recommendations": ["AFAD kanallarini takip edin.", "Aileye durum bildirin."]}

    llm = get_structured_llm(DetailedSynthesisOutput)
    prompt = (
        f"Deprem olayini Turkce ozetle. Abartma, panikletme, kesin hukum kurma. {_COMMON_RULES}\n"
        f"Uzunluk: 4 kisa paragraf — durum, artci adayi filtresi, tarihsel baglam, operasyon notu.\n\n"
        f"Olay: M{mag} {ev.get('location')}, derinlik {ev.get('depthKm')} km, ({ev.get('latitude')}, {ev.get('longitude')}).\n"
        f"Artci adayi filtresi sonucu: {after_line}.\n"
        f"Benzer tarihsel: {similar_line}.\n"
        f"{shakemap_line}\n"
        f"ShakeMap varsa 4. paragrafta (operasyon notu) MMI ve PGA degerlerini yorumla.\n"
    )
    result: DetailedSynthesisOutput = await llm.ainvoke([{"role": "user", "content": prompt}])
    return {
        "summary": result.summary,
        "risk_level": result.risk_level,
        "recommendations": result.recommendations,
        "depth": "detailed",
    }


# ---------------------------------------------------------------------------
# Graph construction (ed-donner style: START, conditional edges)
# ---------------------------------------------------------------------------

def build_quake_detail_graph():
    g = StateGraph(QuakeDetailState)

    g.add_node("fan_out", fan_out_node)
    g.add_node("synthesize_brief", synthesize_brief_node)
    g.add_node("synthesize_standard", synthesize_standard_node)
    g.add_node("synthesize_detailed", synthesize_detailed_node)

    g.add_edge(START, "fan_out")
    g.add_conditional_edges(
        "fan_out",
        _route_by_magnitude,
        {
            "synthesize_brief": "synthesize_brief",
            "synthesize_standard": "synthesize_standard",
            "synthesize_detailed": "synthesize_detailed",
        },
    )
    g.add_edge("synthesize_brief", END)
    g.add_edge("synthesize_standard", END)
    g.add_edge("synthesize_detailed", END)

    return g.compile()


_compiled = None


def get_quake_detail_graph():
    global _compiled
    if _compiled is None:
        _compiled = build_quake_detail_graph()
    return _compiled
