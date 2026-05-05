"""Chat graph — hybrid classifier + MCP tool routing.

Graph topology:

    START
      │
      ▼
   classify   ← keyword fast-path → LLM fallback (structured output)
      │
      ├─ "data"           ──► fetch_data          ──► answer_data
      ├─ "detail"         ──► fetch_detail        ──► answer_detail
      ├─ "historical"     ──► fetch_historical    ──► answer_historical
      ├─ "gaps"           ──────────────────────────► answer_gaps
      ├─ "faults"         ──► fetch_faults        ──► answer_faults
      ├─ "geocode"        ──► fetch_geocode       ──► answer_geocode
      ├─ "building_risk"  ──► fetch_building_risk ──► answer_building_risk
      ├─ "guide"          ──────────────────────────► answer_guide
      ├─ "risk"           ──► fetch_risk          ──► answer_risk
      ├─ "risk_no_loc"    ──────────────────────────► answer_risk_no_loc
      └─ "smalltalk"      ──────────────────────────► answer_smalltalk
                                         │
                                         └──► END

MCP error handling: every fetch node checks the "error" key returned by
call_mcp_tool. If set, it stores a user-friendly fallback message and
skips the answer node's LLM call so the graph never hangs.
"""

import re
from typing import Annotated, Any, Literal

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from pydantic import BaseModel, Field
from typing_extensions import TypedDict

from ..config import DRY_RUN
from ..llm import get_llm, get_structured_llm
from ..mcp.seismic_client import call_mcp_tool


Category = Literal[
    "data", "detail", "historical", "gaps", "faults",
    "geocode", "building_risk",
    "guide", "risk", "risk_no_loc", "smalltalk",
]


# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------

class ChatState(TypedDict, total=False):
    question: str
    messages: Annotated[list[Any], add_messages]
    user_context: dict
    category: Category
    fetched: dict
    sources: list[str]
    answer: str


# ---------------------------------------------------------------------------
# Structured output schema for LLM classifier
# ---------------------------------------------------------------------------

class ClassifyOutput(BaseModel):
    category: Literal[
        "data", "detail", "historical", "gaps", "faults",
        "geocode", "building_risk", "guide", "risk", "smalltalk",
    ] = Field(
        description=(
            "data       — son depremler, bugün/dün/bu hafta ne oldu;\n"
            "detail     — belirli bir deprem ID'si veya olayı hakkında detay;\n"
            "historical — tarihsel büyük depremler, geçmiş yüzyıllardaki olaylar;\n"
            "gaps       — sismik boşluk, uzun süredir kırılmamış fay;\n"
            "faults     — fay hatları, hangi faylar var, fay geometrisi;\n"
            "geocode    — adres veya yer adı koordinat sorgulama;\n"
            "building_risk — binam/evin güvenli mi, yapı risk skoru;\n"
            "guide      — nasıl hazırlanılır, ne yapılmalı, güvenlik rehberi;\n"
            "risk       — benim bölgem/evim/şehrim için risk;\n"
            "smalltalk  — selamlama, genel sohbet, kategori dışı."
        )
    )


# ---------------------------------------------------------------------------
# Keyword fast-path
# ---------------------------------------------------------------------------

_KEYWORDS: dict[str, list[str]] = {
    "data": [
        "son deprem", "bugün", "dün", "bu hafta", "deprem oldu mu", "kaç deprem",
        "büyüklük", "nerede oldu", "saat kaçta", "kandilli", "son sarsıntı",
        "son 7", "son 24", "depremleri getir", "deprem listesi",
    ],
    "detail": [
        "deprem detay", "olay detay", "hakkında bilgi", "aftershock", "artçı",
        "shakemap", "dyfi", "hissettiniz mi", "us7000", "deprem id",
    ],
    "historical": [
        "tarihsel deprem", "geçmiş deprem", "büyük depremler", "1999 depremi",
        "1939 depremi", "tarihi deprem", "geçmişte", "yıl önce olan", "arşiv",
    ],
    "gaps": [
        "sismik boşluk", "kırılmamış fay", "sessiz fay", "boşluk analizi",
        "seismic gap", "fay birikimi", "stres birikimi",
    ],
    "faults": [
        "fay hattı", "fay hatları", "aktif fay", "kuzey anadolu fayı", "doğu anadolu fayı",
        "fay geometri", "hangi faylar", "yakınımda fay",
    ],
    "geocode": [
        "koordinat", "konum bul", "nerede", "adres koordinat", "lat lon",
        "enlem boylam", "geocode", "konumu nedir",
    ],
    "building_risk": [
        "binam güvenli", "evim güvenli", "bina riski", "yapı riski", "depreme dayanıklı",
        "eski bina", "kaç puanlık", "risk skoru", "bina değerlendir",
    ],
    "guide": [
        "nasıl hazırlan", "ne yapmalı", "ne yapıyım", "çanta", "rehber",
        "tavsiye", "afet çantası", "deprem çantası", "güvenli", "tahliye",
        "toplanma", "önlem",
    ],
    "risk": [
        "benim bölge", "bölgem", "evim", "şehrim", "yaşadığım", "oturduğum",
        "konumum", "bulunduğum", "yakınımda", "tehlikeli mi",
    ],
}


def _keyword_classify(question: str) -> Category | None:
    q = question.lower()
    q_ascii = (
        q.replace("ç", "c").replace("ğ", "g").replace("ı", "i")
         .replace("ö", "o").replace("ş", "s").replace("ü", "u")
    )
    for category, keywords in _KEYWORDS.items():
        if any(
            k in q or (
                k.replace("ç", "c").replace("ğ", "g").replace("ı", "i")
                 .replace("ö", "o").replace("ş", "s").replace("ü", "u")
            ) in q_ascii
            for k in keywords
        ):
            return category  # type: ignore[return-value]
    return None


# ---------------------------------------------------------------------------
# System prompts
# ---------------------------------------------------------------------------

_BASE_IDENTITY = (
    "Sen Deprem Rehberim uygulamasının Türkçe konuşan AI asistanısın. "
    "Yalnızca sismoloji, deprem güvenliği ve Türkiye'deki deprem verileriyle ilgili konularda yardım edersin. "
    "Abartma, panikletme ve kesin hüküm vermekten kaçın. "
    "Dil: doğal, sade Türkçe. Markdown başlık veya kalın yazı kullanma."
)


def _system_data(mcp_result: dict) -> str:
    rows = mcp_result.get("records", [])
    lines = [
        f"- M{r.get('magnitude')} {r.get('location')} ({r.get('time')}, derinlik {r.get('depthKm')} km)"
        for r in rows[:10]
    ]
    data_block = "\n".join(lines) if lines else "(veri alınamadı)"
    return (
        f"{_BASE_IDENTITY}\n\n"
        "Görev: Deprem veri sorusunu MCP tool sonucuna dayanarak yanıtla. "
        "Yalnızca listede olanları kullan.\n\n"
        f"MCP özeti: {mcp_result.get('summary', '')}\n"
        f"Son depremler:\n{data_block}"
    )


def _system_detail(mcp_result: dict) -> str:
    event = mcp_result.get("event") or {}
    return (
        f"{_BASE_IDENTITY}\n\n"
        "Görev: Kullanıcının sorduğu deprem olayının detaylarını MCP verisine dayanarak açıkla.\n\n"
        f"MCP özeti: {mcp_result.get('summary', '')}\n"
        f"Olay: {event}\n"
        f"Artçı sayısı: {mcp_result.get('aftershockCount', 0)}\n"
        f"Benzer tarihsel: {mcp_result.get('similarHistoricalCount', 0)}\n"
        f"Risk seviyesi: {mcp_result.get('riskLevel', '-')}"
    )


def _system_historical(mcp_result: dict) -> str:
    records = mcp_result.get("records", [])[:8]
    lines = [
        f"- M{r.get('magnitude')} {r.get('location')} ({r.get('time')})"
        for r in records
    ]
    return (
        f"{_BASE_IDENTITY}\n\n"
        "Görev: Kullanıcının tarihsel deprem sorusunu MCP verisiyle yanıtla.\n\n"
        f"MCP özeti: {mcp_result.get('summary', '')}\n"
        f"Tarihsel depremler:\n" + ("\n".join(lines) if lines else "(veri yok)")
    )


def _system_gaps(mcp_result: dict) -> str:
    return (
        f"{_BASE_IDENTITY}\n\n"
        "Görev: Sismik boşluk sorusunu MCP verisine dayanarak açıkla. "
        "Sismik boşluğun ne anlama geldiğini ve verilen sonuçların ne gösterdiğini anlat.\n\n"
        f"Sismik boşluk verisi: {mcp_result}"
    )


def _system_faults(mcp_result: dict) -> str:
    names = mcp_result.get("sampleNames", [])
    return (
        f"{_BASE_IDENTITY}\n\n"
        "Görev: Fay hattı sorusunu MCP verisiyle yanıtla.\n\n"
        f"MCP özeti: {mcp_result.get('summary', '')}\n"
        f"Fay isimleri: {', '.join(names) if names else 'veri yok'}\n"
        f"Fay geometri sayısı: {mcp_result.get('featureCount', 0)}"
    )


def _system_geocode(mcp_result: dict) -> str:
    return (
        f"{_BASE_IDENTITY}\n\n"
        "Görev: Kullanıcının sorduğu konumu MCP geocode sonucuyla açıkla.\n\n"
        f"MCP özeti: {mcp_result.get('summary', '')}\n"
        f"En iyi sonuç: {mcp_result.get('best', '(bulunamadı)')}"
    )


def _system_building_risk(mcp_result: dict) -> str:
    return (
        f"{_BASE_IDENTITY}\n\n"
        "Görev: Bina risk skorunu kullanıcıya anlaşılır Türkçeyle açıkla. "
        "Kesin hüküm verme, ön değerlendirme olduğunu vurgula.\n\n"
        f"Risk skoru: {mcp_result.get('score', '?')}/100\n"
        f"Risk seviyesi: {mcp_result.get('level', '?')}\n"
        f"Risk etkenleri: {mcp_result.get('drivers', [])}\n"
        f"MCP özeti: {mcp_result.get('summary', '')}"
    )


def _system_guide() -> str:
    return (
        f"{_BASE_IDENTITY}\n\n"
        "Görev: Deprem güvenliği ve hazırlık sorusunu yanıtla. "
        "Kısa, uygulanabilir maddeler hâlinde ver. "
        "Kaynak uydurmaktan kaçın; yalnızca AFAD ve genel bilinen rehber ilkelerini kullan."
    )


def _system_risk(mcp_context: dict, loc_hint: str) -> str:
    nearby = mcp_context.get("sampleRecent", [])
    rows_txt = (
        "\n".join(
            f"- M{r.get('magnitude')} {r.get('location')} ({r.get('time')})"
            for r in nearby[:8]
        )
        or "(yakın kayıt yok)"
    )
    faults = ", ".join(mcp_context.get("sampleFaultNames", [])[:5]) or "fay adı bulunamadı"
    return (
        f"{_BASE_IDENTITY}\n\n"
        "Görev: Kullanıcının kendi bölgesi için risk yorumu isteğini yanıtla. "
        "MCP sismik bağlam tool sonucunu kullan. "
        "Abartma yapma; 3-4 cümle, ölçülü bir yorum yap.\n\n"
        f"Kullanıcı konumu: {loc_hint}\n"
        f"MCP özeti: {mcp_context.get('summary', '')}\n"
        f"Yakın aktif fay örnekleri: {faults}\n"
        f"Son 7 gün yakın olay sayısı: {mcp_context.get('recentCount7Days', 0)}\n"
        f"50 yıllık tarihsel olay sayısı: {mcp_context.get('historicalCount50Years', 0)}\n"
        f"Yakın kayıtlar:\n{rows_txt}"
    )


def _system_risk_no_loc() -> str:
    return (
        f"{_BASE_IDENTITY}\n\n"
        "Görev: Kullanıcı kendi bölgesi için risk sordu ancak konum bilgisi paylaşılmadı. "
        "Kibarca konumun neden gerekli olduğunu açıkla ve uygulamadan konum izni vermesini iste. "
        "Genel bir bölge adı söyleyebileceğini de belirt."
    )


def _system_smalltalk() -> str:
    return (
        f"{_BASE_IDENTITY}\n\n"
        "Görev: Kullanıcıyla doğal bir sohbet kur. "
        "Uygunsa uygulamanın özelliklerini (son depremler, güvenlik rehberi, bölge riski, bina riski) kısaca tanıt. "
        "Eğer konu depremle hiç ilgili değilse kibarca odaklan."
    )


# ---------------------------------------------------------------------------
# State helpers
# ---------------------------------------------------------------------------

def _build_messages(system_prompt: str, state: ChatState) -> list[Any]:
    history = list(state.get("messages") or [])
    if history and isinstance(history[0], SystemMessage):
        history[0] = SystemMessage(content=system_prompt)
    else:
        history = [SystemMessage(content=system_prompt)] + history
    return history


def _current_question(state: ChatState) -> str:
    incoming = str(state.get("question") or "").strip()
    if incoming:
        return incoming
    for msg in reversed(state.get("messages") or []):
        if isinstance(msg, HumanMessage):
            return msg.content
    return ""


def _pending_user_message(state: ChatState) -> list[Any]:
    question = str(state.get("question") or "").strip()
    if not question:
        return []
    history = list(state.get("messages") or [])
    if history and isinstance(history[-1], HumanMessage) and history[-1].content == question:
        return []
    return [HumanMessage(content=question)]


def _merge_sources(*groups: list[str]) -> list[str]:
    merged: list[str] = []
    for group in groups:
        for source in group:
            if source and source not in merged:
                merged.append(source)
    return merged


def _mcp_error_response(mcp_call: dict) -> str | None:
    """Return a user-friendly message if the MCP call failed, else None."""
    error = mcp_call.get("error")
    if not error:
        return None
    return (
        "Üzgünüm, şu anda veri servisine ulaşılamıyor. "
        "Lütfen birkaç dakika sonra tekrar deneyin. "
        f"(Teknik detay: {error})"
    )


# ---------------------------------------------------------------------------
# Query argument helpers
# ---------------------------------------------------------------------------

def _data_query_args(question: str) -> dict[str, Any]:
    q = question.lower()
    hours = 24
    if any(token in q for token in ["hafta", "7 gün", "7 gun"]):
        hours = 168
    elif match := re.search(r"son\s+(\d{1,3})\s*(saat|hour)", q):
        hours = max(1, min(168, int(match.group(1))))
    min_magnitude = 1.0
    if match := re.search(r"m\s?(\d+(?:[.,]\d+)?)", q):
        min_magnitude = float(match.group(1).replace(",", "."))
    elif match := re.search(r"(\d+(?:[.,]\d+)?)\s*(?:ve üzeri|ustu|üstü|\+)", q):
        min_magnitude = float(match.group(1).replace(",", "."))
    return {"hours": hours, "min_magnitude": max(0.0, min(10.0, min_magnitude)), "limit": 12}


def _extract_event_id(question: str) -> str | None:
    """Try to extract a USGS-style event ID from the question."""
    match = re.search(r"\b([a-z]{2}\d{7,})\b", question.lower())
    return match.group(1) if match else None


def _extract_place_query(question: str) -> str:
    """Extract the place name / address from a geocode question."""
    q = question
    for prefix in ["koordinatını bul", "koordinatı", "koordinat", "konumu nedir", "nerede", "adres", "geocode"]:
        q = re.sub(prefix, "", q, flags=re.IGNORECASE).strip()
    return q.strip("? ") or question


def _building_args_from_context(ctx: dict) -> dict[str, Any]:
    """Build assess_building_risk arguments from user_context."""
    return {
        "latitude": float(ctx.get("latitude", 41.0)),
        "longitude": float(ctx.get("longitude", 29.0)),
        "construction_year": int(ctx.get("constructionYear", 2000)),
        "floor_count": int(ctx.get("floorCount", 4)),
        "soil_type": str(ctx.get("soilType", "ZC")),
        "structural_system": str(ctx.get("structuralSystem", "RC")),
        "visible_damage": bool(ctx.get("visibleDamage", False)),
        "radius_km": 100.0,
    }


# ---------------------------------------------------------------------------
# Classify node
# ---------------------------------------------------------------------------

async def classify_node(state: ChatState) -> ChatState:
    question = _current_question(state)
    pending_messages = _pending_user_message(state)
    ctx = state.get("user_context") or {}
    has_location = "latitude" in ctx and "longitude" in ctx

    keyword_hit = _keyword_classify(question)
    if keyword_hit or DRY_RUN:
        raw = keyword_hit or "smalltalk"
        category: Category = "risk_no_loc" if raw == "risk" and not has_location else raw  # type: ignore[assignment]
        result_state: ChatState = {"category": category}
        if pending_messages:
            result_state["messages"] = pending_messages
        return result_state

    llm = get_structured_llm(ClassifyOutput, temperature=0.0)
    system = (
        "Bir deprem uygulaması soru sınıflandırıcısısın. "
        "Kullanıcı sorusunu aşağıdaki kategorilerden birine ata:\n"
        "  data          — son depremler, bugün/dün/bu hafta ne oldu\n"
        "  detail        — belirli bir deprem ID/olayı hakkında detay\n"
        "  historical    — tarihsel büyük depremler, geçmiş yüzyıllar\n"
        "  gaps          — sismik boşluk, uzun süredir kırılmamış fay\n"
        "  faults        — fay hatları, aktif faylar, fay geometrisi\n"
        "  geocode       — adres veya yer adı koordinat sorgulama\n"
        "  building_risk — binam/evin güvenli mi, yapı risk skoru\n"
        "  guide         — nasıl hazırlanılır, ne yapılmalı, güvenlik rehberi\n"
        "  risk          — benim bölgem/evim/şehrim için sismik risk\n"
        "  smalltalk     — selamlama, genel sohbet, kategori dışı\n"
        "Yalnızca JSON döndür."
    )
    result: ClassifyOutput = await llm.ainvoke([
        SystemMessage(content=system),
        HumanMessage(content=question),
    ])

    raw_category = result.category
    category = "risk_no_loc" if raw_category == "risk" and not has_location else raw_category  # type: ignore[assignment]
    result_state = {"category": category}
    if pending_messages:
        result_state["messages"] = pending_messages
    return result_state


# ---------------------------------------------------------------------------
# Fetch nodes
# ---------------------------------------------------------------------------

async def fetch_data_node(state: ChatState) -> ChatState:
    args = _data_query_args(_current_question(state))
    mcp_call = await call_mcp_tool("get_recent_earthquakes", args)
    result = mcp_call.get("result", {})
    return {
        "fetched": {"mcp_data": result, "mcp_call": mcp_call},
        "sources": _merge_sources(
            ["MCP get_recent_earthquakes"],
            [str(result.get("source") or "Kandilli / koeri.boun.edu.tr")],
        ),
    }


async def fetch_detail_node(state: ChatState) -> ChatState:
    question = _current_question(state)
    event_id = _extract_event_id(question)
    if not event_id:
        return {
            "fetched": {"mcp_call": {"error": "Soruda bir deprem ID'si bulunamadı."}},
            "sources": [],
        }
    mcp_call = await call_mcp_tool("get_earthquake_detail", {"event_id": event_id})
    result = mcp_call.get("result", {})
    return {
        "fetched": {"mcp_detail": result, "mcp_call": mcp_call, "event_id": event_id},
        "sources": _merge_sources(
            ["MCP get_earthquake_detail"],
            [str(result.get("source") or "USGS / Spring backend")],
        ),
    }


async def fetch_historical_node(state: ChatState) -> ChatState:
    mcp_call = await call_mcp_tool("get_historical_events", {"years": 100, "min_magnitude": 5.5})
    result = mcp_call.get("result", {})
    return {
        "fetched": {"mcp_historical": result, "mcp_call": mcp_call},
        "sources": _merge_sources(
            ["MCP get_historical_events"],
            [str(result.get("source") or "USGS tarihsel arşiv")],
        ),
    }


async def fetch_faults_node(state: ChatState) -> ChatState:
    ctx = state.get("user_context") or {}
    if "latitude" in ctx and "longitude" in ctx:
        from ..mcp.seismic_server import _bbox
        lat, lon = float(ctx["latitude"]), float(ctx["longitude"])
        min_lon, min_lat, max_lon, max_lat = _bbox(lat, lon, 150.0)
    else:
        # Default: Turkey bounding box
        min_lon, min_lat, max_lon, max_lat = 26.0, 36.0, 45.0, 42.0

    mcp_call = await call_mcp_tool("get_fault_lines", {
        "min_longitude": min_lon, "min_latitude": min_lat,
        "max_longitude": max_lon, "max_latitude": max_lat,
    })
    result = mcp_call.get("result", {})
    return {
        "fetched": {"mcp_faults": result, "mcp_call": mcp_call},
        "sources": _merge_sources(
            ["MCP get_fault_lines"],
            [str(result.get("source") or "MTA aktif fay katmanı")],
        ),
    }


async def fetch_geocode_node(state: ChatState) -> ChatState:
    query = _extract_place_query(_current_question(state))
    mcp_call = await call_mcp_tool("geocode_address", {"query": query})
    result = mcp_call.get("result", {})
    return {
        "fetched": {"mcp_geocode": result, "mcp_call": mcp_call},
        "sources": ["MCP geocode_address"],
    }


async def fetch_building_risk_node(state: ChatState) -> ChatState:
    ctx = state.get("user_context") or {}
    if "latitude" not in ctx:
        return {
            "fetched": {"mcp_call": {"error": "Bina risk değerlendirmesi için konum gerekli. Lütfen konum izni verin."}},
            "sources": [],
        }
    args = _building_args_from_context(ctx)
    mcp_call = await call_mcp_tool("assess_building_risk", args)
    result = mcp_call.get("result", {})
    return {
        "fetched": {"mcp_building": result, "mcp_call": mcp_call},
        "sources": _merge_sources(
            ["MCP assess_building_risk"],
            [str(result.get("source") or "Deterministik kural motoru")],
        ),
    }


async def fetch_risk_node(state: ChatState) -> ChatState:
    ctx = state.get("user_context") or {}
    ulat, ulon = float(ctx["latitude"]), float(ctx["longitude"])
    mcp_call = await call_mcp_tool("get_seismic_context", {
        "latitude": ulat, "longitude": ulon, "radius_km": 100.0,
    })
    result = mcp_call.get("result", {})
    return {
        "fetched": {"mcp_context": result, "mcp_call": mcp_call, "user_context": ctx},
        "sources": _merge_sources(
            ["MCP get_seismic_context"],
            [str(result.get("source") or "Kandilli + fay hatları")],
        ),
    }


# ---------------------------------------------------------------------------
# Answer nodes
# ---------------------------------------------------------------------------

async def answer_data_node(state: ChatState) -> ChatState:
    mcp_call = state.get("fetched", {}).get("mcp_call", {})
    mcp_result = state.get("fetched", {}).get("mcp_data", {})

    if err := _mcp_error_response(mcp_call):
        response = AIMessage(content=err)
        return {"messages": [response], "answer": response.content}

    if DRY_RUN:
        rows = mcp_result.get("records", [])
        summary = mcp_result.get("summary") or "MCP deprem tool'u çalıştı."
        lines = [f"{i+1}. M{r.get('magnitude')} - {r.get('location')}" for i, r in enumerate(rows[:5])]
        content = f"{summary}\n" + "\n".join(lines) if lines else summary
        response = AIMessage(content=content)
        return {"messages": [response], "answer": response.content}

    messages = _build_messages(_system_data(mcp_result), state)
    response: AIMessage = await get_llm(temperature=0.3).ainvoke(messages)
    return {"messages": [response], "answer": response.content}


async def answer_detail_node(state: ChatState) -> ChatState:
    mcp_call = state.get("fetched", {}).get("mcp_call", {})
    mcp_result = state.get("fetched", {}).get("mcp_detail", {})

    if err := _mcp_error_response(mcp_call):
        response = AIMessage(content=err)
        return {"messages": [response], "answer": response.content}

    messages = _build_messages(_system_detail(mcp_result), state)
    response: AIMessage = await get_llm(temperature=0.3).ainvoke(messages)
    return {"messages": [response], "answer": response.content}


async def answer_historical_node(state: ChatState) -> ChatState:
    mcp_call = state.get("fetched", {}).get("mcp_call", {})
    mcp_result = state.get("fetched", {}).get("mcp_historical", {})

    if err := _mcp_error_response(mcp_call):
        response = AIMessage(content=err)
        return {"messages": [response], "answer": response.content}

    messages = _build_messages(_system_historical(mcp_result), state)
    response: AIMessage = await get_llm(temperature=0.3).ainvoke(messages)
    return {"messages": [response], "answer": response.content}


async def answer_gaps_node(state: ChatState) -> ChatState:
    mcp_call = await call_mcp_tool("get_seismic_gaps", {})
    mcp_result = mcp_call.get("result", {})

    if err := _mcp_error_response(mcp_call):
        response = AIMessage(content=err)
        return {"messages": [response], "answer": response.content}

    messages = _build_messages(_system_gaps(mcp_result), state)
    response: AIMessage = await get_llm(temperature=0.3).ainvoke(messages)
    return {"messages": [response], "answer": response.content}


async def answer_faults_node(state: ChatState) -> ChatState:
    mcp_call = state.get("fetched", {}).get("mcp_call", {})
    mcp_result = state.get("fetched", {}).get("mcp_faults", {})

    if err := _mcp_error_response(mcp_call):
        response = AIMessage(content=err)
        return {"messages": [response], "answer": response.content}

    messages = _build_messages(_system_faults(mcp_result), state)
    response: AIMessage = await get_llm(temperature=0.3).ainvoke(messages)
    return {"messages": [response], "answer": response.content}


async def answer_geocode_node(state: ChatState) -> ChatState:
    mcp_call = state.get("fetched", {}).get("mcp_call", {})
    mcp_result = state.get("fetched", {}).get("mcp_geocode", {})

    if err := _mcp_error_response(mcp_call):
        response = AIMessage(content=err)
        return {"messages": [response], "answer": response.content}

    messages = _build_messages(_system_geocode(mcp_result), state)
    response: AIMessage = await get_llm(temperature=0.3).ainvoke(messages)
    return {"messages": [response], "answer": response.content}


async def answer_building_risk_node(state: ChatState) -> ChatState:
    mcp_call = state.get("fetched", {}).get("mcp_call", {})
    mcp_result = state.get("fetched", {}).get("mcp_building", {})

    if err := _mcp_error_response(mcp_call):
        response = AIMessage(content=err)
        return {"messages": [response], "answer": response.content}

    messages = _build_messages(_system_building_risk(mcp_result), state)
    response: AIMessage = await get_llm(temperature=0.3).ainvoke(messages)
    return {"messages": [response], "answer": response.content}


async def answer_guide_node(state: ChatState) -> ChatState:
    messages = _build_messages(_system_guide(), state)
    response: AIMessage = await get_llm(temperature=0.3).ainvoke(messages)
    return {
        "messages": [response],
        "answer": response.content,
        "sources": ["AFAD rehberi (genel bilgi)"],
    }


async def answer_risk_node(state: ChatState) -> ChatState:
    mcp_call = state.get("fetched", {}).get("mcp_call", {})
    mcp_context = state.get("fetched", {}).get("mcp_context", {})
    ctx = state.get("fetched", {}).get("user_context", {})
    loc_hint = f"{ctx.get('latitude')}, {ctx.get('longitude')}"

    if err := _mcp_error_response(mcp_call):
        response = AIMessage(content=err)
        return {"messages": [response], "answer": response.content}

    if DRY_RUN:
        content = (
            f"Konumun için MCP sismik bağlam tool'u çalıştı. "
            f"100 km çevrede son 7 günde {mcp_context.get('recentCount7Days', 0)} kayıt, "
            f"50 yıllık tarihsel veri içinde {mcp_context.get('historicalCount50Years', 0)} M4.5+ olay bulundu."
        )
        response = AIMessage(content=content)
        return {"messages": [response], "answer": response.content}

    messages = _build_messages(_system_risk(mcp_context, loc_hint), state)
    response: AIMessage = await get_llm(temperature=0.3).ainvoke(messages)
    return {"messages": [response], "answer": response.content}


async def answer_risk_no_loc_node(state: ChatState) -> ChatState:
    messages = _build_messages(_system_risk_no_loc(), state)
    response: AIMessage = await get_llm(temperature=0.3).ainvoke(messages)
    return {"messages": [response], "answer": response.content}


async def answer_smalltalk_node(state: ChatState) -> ChatState:
    messages = _build_messages(_system_smalltalk(), state)
    response: AIMessage = await get_llm(temperature=0.7).ainvoke(messages)
    return {"messages": [response], "answer": response.content}


def _route(state: ChatState) -> str:
    return state.get("category", "smalltalk")


# ---------------------------------------------------------------------------
# Graph construction
# ---------------------------------------------------------------------------

def build_chat_graph(checkpointer=None):
    g = StateGraph(ChatState)

    # Nodes
    g.add_node("classify", classify_node)

    g.add_node("fetch_data", fetch_data_node)
    g.add_node("fetch_detail", fetch_detail_node)
    g.add_node("fetch_historical", fetch_historical_node)
    g.add_node("fetch_faults", fetch_faults_node)
    g.add_node("fetch_geocode", fetch_geocode_node)
    g.add_node("fetch_building_risk", fetch_building_risk_node)
    g.add_node("fetch_risk", fetch_risk_node)

    g.add_node("answer_data", answer_data_node)
    g.add_node("answer_detail", answer_detail_node)
    g.add_node("answer_historical", answer_historical_node)
    g.add_node("answer_gaps", answer_gaps_node)
    g.add_node("answer_faults", answer_faults_node)
    g.add_node("answer_geocode", answer_geocode_node)
    g.add_node("answer_building_risk", answer_building_risk_node)
    g.add_node("answer_guide", answer_guide_node)
    g.add_node("answer_risk", answer_risk_node)
    g.add_node("answer_risk_no_loc", answer_risk_no_loc_node)
    g.add_node("answer_smalltalk", answer_smalltalk_node)

    # Classify → route
    g.add_edge(START, "classify")
    g.add_conditional_edges(
        "classify",
        _route,
        {
            "data":          "fetch_data",
            "detail":        "fetch_detail",
            "historical":    "fetch_historical",
            "gaps":          "answer_gaps",       # gaps fetch is done inside the answer node
            "faults":        "fetch_faults",
            "geocode":       "fetch_geocode",
            "building_risk": "fetch_building_risk",
            "guide":         "answer_guide",
            "risk":          "fetch_risk",
            "risk_no_loc":   "answer_risk_no_loc",
            "smalltalk":     "answer_smalltalk",
        },
    )

    # Fetch → answer edges
    g.add_edge("fetch_data",          "answer_data")
    g.add_edge("fetch_detail",        "answer_detail")
    g.add_edge("fetch_historical",    "answer_historical")
    g.add_edge("fetch_faults",        "answer_faults")
    g.add_edge("fetch_geocode",       "answer_geocode")
    g.add_edge("fetch_building_risk", "answer_building_risk")
    g.add_edge("fetch_risk",          "answer_risk")

    # Answer → END
    for node in [
        "answer_data", "answer_detail", "answer_historical", "answer_gaps",
        "answer_faults", "answer_geocode", "answer_building_risk",
        "answer_guide", "answer_risk", "answer_risk_no_loc", "answer_smalltalk",
    ]:
        g.add_edge(node, END)

    return g.compile(checkpointer=checkpointer)


_compiled = None


def get_chat_graph(checkpointer: Any = None) -> Any:
    global _compiled
    if _compiled is None:
        _compiled = build_chat_graph(checkpointer)
    return _compiled


def reset_chat_graph() -> None:
    global _compiled
    _compiled = None
