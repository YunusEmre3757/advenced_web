"""Chat graph — Ed-Donner pattern: add_messages reducer, hybrid classifier,
dynamic system prompts, proper HumanMessage/AIMessage/SystemMessage usage.

Graph topology:

    START
      │
      ▼
   classify   ← hybrid: keyword fast-path → LLM fallback (structured output)
      │
      ├─ "data"         ──► fetch_data ──► answer_data
      ├─ "guide"        ──────────────────► answer_guide
      ├─ "risk"         ──► fetch_risk ──► answer_risk
      ├─ "risk_no_loc"  ──────────────────► answer_risk_no_loc
      └─ "smalltalk"    ──────────────────► answer_smalltalk
                                   │
                                   └──► END
"""

import math
from typing import Annotated, Any, Literal

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from pydantic import BaseModel, Field
from typing_extensions import TypedDict

from ..config import DRY_RUN
from ..llm import get_llm, get_structured_llm
from ..spring_client import get_spring_client


Category = Literal["data", "guide", "risk", "risk_no_loc", "smalltalk"]


# ---------------------------------------------------------------------------
# State — add_messages reducer handles multi-turn history automatically
# question and fetched are turn-scoped; sources accumulates per answer node
# ---------------------------------------------------------------------------

class ChatState(TypedDict, total=False):
    messages: Annotated[list[Any], add_messages]
    user_context: dict
    category: Category
    fetched: dict
    sources: list[str]


# ---------------------------------------------------------------------------
# Structured output schema for LLM classifier fallback
# ---------------------------------------------------------------------------

class ClassifyOutput(BaseModel):
    category: Literal["data", "guide", "risk", "smalltalk"] = Field(
        description=(
            "data — son depremler, bugün/dün/bu hafta ne oldu gibi veri soruları; "
            "guide — nasıl hazırlanılır, ne yapılmalı, güvenlik rehberi; "
            "risk — benim bölgem/evim/şehrim için risk; "
            "smalltalk — selamlama, genel sohbet, kategori dışı her şey"
        )
    )


# ---------------------------------------------------------------------------
# Geo helper — haversine with float-safe clamp
# ---------------------------------------------------------------------------

def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return r * 2 * math.asin(math.sqrt(max(0.0, min(1.0, a))))


# ---------------------------------------------------------------------------
# Hybrid classifier — keyword fast-path saves an LLM call for clear cases
# ---------------------------------------------------------------------------

_KEYWORDS: dict[str, list[str]] = {
    "data": [
        "son deprem", "bugün", "dün", "bu hafta", "deprem oldu mu", "kaç deprem",
        "büyüklük", "nerede oldu", "saat kaçta", "kandilli", "son sarsıntı",
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
    for category, keywords in _KEYWORDS.items():
        if any(k in q for k in keywords):
            return category  # type: ignore[return-value]
    return None


# ---------------------------------------------------------------------------
# System prompts — dynamic and context-aware (Ed-Donner pattern)
# ---------------------------------------------------------------------------

_BASE_IDENTITY = (
    "Sen Deprem Rehberim uygulamasının Türkçe konuşan AI asistanısın. "
    "Yalnızca sismoloji, deprem güvenliği ve Türkiye'deki deprem verileriyle ilgili konularda yardım edersin. "
    "Abartma, panikletme ve kesin hüküm vermekten kaçın. "
    "Dil: doğal, sade Türkçe. Markdown başlık veya kalın yazı kullanma."
)


def _system_data(rows: list[dict]) -> str:
    lines = [
        f"- M{r.get('magnitude')} {r.get('location')} ({r.get('time')}, derinlik {r.get('depthKm')} km)"
        for r in rows[:10]
    ]
    data_block = "\n".join(lines) if lines else "(veri alınamadı)"
    return (
        f"{_BASE_IDENTITY}\n\n"
        "Görev: Kullanıcının deprem veri sorusunu aşağıdaki Kandilli kayıtlarına dayanarak yanıtla. "
        "Uydurma — yalnızca listede olanları kullan. Eğer liste boşsa bunu açıkça belirt.\n\n"
        f"Son depremler:\n{data_block}"
    )


def _system_guide() -> str:
    return (
        f"{_BASE_IDENTITY}\n\n"
        "Görev: Deprem güvenliği ve hazırlık sorusunu yanıtla. "
        "Kısa, uygulanabilir maddeler hâlinde ver. "
        "İç mekân, dış mekân, araç içi gibi duruma göre ayır. "
        "Kaynak uydurmaktan kaçın; yalnızca AFAD ve genel bilinen rehber ilkelerini kullan."
    )


def _system_risk(nearby: list[dict], loc_hint: str) -> str:
    rows_txt = (
        "\n".join(
            f"- M{r.get('magnitude')} {r.get('location')} ({r.get('time')})"
            for r in nearby[:8]
        )
        or "(yakın kayıt yok)"
    )
    return (
        f"{_BASE_IDENTITY}\n\n"
        "Görev: Kullanıcının kendi bölgesi için risk yorumu isteğini yanıtla. "
        "Son 1 haftalık yakın deprem kayıtlarını bağlam olarak kullan. "
        "Abartma, falcılık yapma; 3-4 cümle, ölçülü bir yorum yap.\n\n"
        f"Kullanıcı konumu: {loc_hint}\n"
        f"Yakın kayıtlar:\n{rows_txt}"
    )


def _system_risk_no_loc() -> str:
    return (
        f"{_BASE_IDENTITY}\n\n"
        "Görev: Kullanıcı kendi bölgesi için risk sordu ancak konum bilgisi paylaşılmadı. "
        "Kibarca konumun neden gerekli olduğunu açıkla ve uygulamadan konum izni vermesini iste. "
        "Konuşmayı ilerletmek için genel bir bölge adı (il/ilçe) söyleyebileceğini de belirt."
    )


def _system_smalltalk() -> str:
    return (
        f"{_BASE_IDENTITY}\n\n"
        "Görev: Kullanıcıyla doğal bir sohbet kur. "
        "Uygunsa uygulamanın özelliklerini (son depremler, güvenlik rehberi, bölge riski) kısaca tanıt. "
        "Eğer konu depremle hiç ilgili değilse kibarca odaklan."
    )


# ---------------------------------------------------------------------------
# Node helper — Ed-Donner pattern: SystemMessage at index 0, history follows
# ---------------------------------------------------------------------------

def _build_messages(system_prompt: str, state: ChatState) -> list[Any]:
    history = list(state.get("messages") or [])
    if history and isinstance(history[0], SystemMessage):
        history[0] = SystemMessage(content=system_prompt)
    else:
        history = [SystemMessage(content=system_prompt)] + history
    return history


def _last_question(state: ChatState) -> str:
    """Extract the latest HumanMessage content from message history."""
    for msg in reversed(state.get("messages") or []):
        if isinstance(msg, HumanMessage):
            return msg.content
    return ""


# ---------------------------------------------------------------------------
# Nodes
# ---------------------------------------------------------------------------

async def classify_node(state: ChatState) -> ChatState:
    """Hybrid classifier: keyword fast-path → LLM structured output fallback."""
    question = _last_question(state)
    ctx = state.get("user_context") or {}
    has_location = "latitude" in ctx and "longitude" in ctx

    # Keyword fast-path — no LLM call for unambiguous questions
    keyword_hit = _keyword_classify(question)
    if keyword_hit or DRY_RUN:
        raw = keyword_hit or "smalltalk"
        category: Category = "risk_no_loc" if raw == "risk" and not has_location else raw
        return {"category": category}

    # LLM fallback for ambiguous questions
    llm = get_structured_llm(ClassifyOutput, temperature=0.0)
    system = (
        "Bir deprem uygulaması soru sınıflandırıcısısın. "
        "Kullanıcı sorusunu tam olarak dört kategoriden birine ata:\n"
        "  data      — son depremler, bugün/dün/bu hafta ne oldu\n"
        "  guide     — nasıl hazırlanılır, ne yapılmalı, güvenlik rehberi\n"
        "  risk      — benim bölgem/evim/şehrim için risk\n"
        "  smalltalk — selamlama, genel sohbet, kategori dışı\n"
        "Yalnızca JSON döndür."
    )
    result: ClassifyOutput = await llm.ainvoke([
        SystemMessage(content=system),
        HumanMessage(content=question),
    ])

    raw_category = result.category
    category = "risk_no_loc" if raw_category == "risk" and not has_location else raw_category
    return {"category": category}


async def fetch_data_node(_state: ChatState) -> ChatState:
    client = get_spring_client()
    rows = await client.recent_earthquakes(hours=24, min_magnitude=2.0, limit=20)
    return {
        "fetched": {"earthquakes": rows},
        "sources": ["Kandilli / koeri.boun.edu.tr"],
    }


async def fetch_risk_node(state: ChatState) -> ChatState:
    client = get_spring_client()
    ctx = state.get("user_context") or {}
    rows = await client.recent_earthquakes(hours=168, min_magnitude=3.0, limit=50)

    try:
        ulat, ulon = float(ctx["latitude"]), float(ctx["longitude"])
        filtered = [
            r for r in rows
            if _haversine_km(ulat, ulon, float(r.get("latitude", 0)), float(r.get("longitude", 0))) <= 200
        ]
    except Exception:
        filtered = rows

    return {
        "fetched": {"nearby": filtered[:15], "user_context": ctx},
        "sources": ["Kandilli"],
    }


async def answer_data_node(state: ChatState) -> ChatState:
    rows = state.get("fetched", {}).get("earthquakes", [])
    messages = _build_messages(_system_data(rows), state)
    response: AIMessage = await get_llm(temperature=0.3).ainvoke(messages)
    return {"messages": [response]}


async def answer_guide_node(state: ChatState) -> ChatState:
    messages = _build_messages(_system_guide(), state)
    response: AIMessage = await get_llm(temperature=0.3).ainvoke(messages)
    return {
        "messages": [response],
        "sources": ["AFAD rehberi (genel bilgi)"],
    }


async def answer_risk_node(state: ChatState) -> ChatState:
    nearby = state.get("fetched", {}).get("nearby", [])
    ctx = state.get("fetched", {}).get("user_context", {})
    loc_hint = f"{ctx.get('latitude')}, {ctx.get('longitude')}"
    messages = _build_messages(_system_risk(nearby, loc_hint), state)
    response: AIMessage = await get_llm(temperature=0.3).ainvoke(messages)
    return {"messages": [response]}


async def answer_risk_no_loc_node(state: ChatState) -> ChatState:
    messages = _build_messages(_system_risk_no_loc(), state)
    response: AIMessage = await get_llm(temperature=0.3).ainvoke(messages)
    return {"messages": [response]}


async def answer_smalltalk_node(state: ChatState) -> ChatState:
    messages = _build_messages(_system_smalltalk(), state)
    response: AIMessage = await get_llm(temperature=0.7).ainvoke(messages)
    return {"messages": [response]}


def _route(state: ChatState) -> str:
    return state.get("category", "smalltalk")


# ---------------------------------------------------------------------------
# Graph construction
# ---------------------------------------------------------------------------

def build_chat_graph(checkpointer=None):
    g = StateGraph(ChatState)

    g.add_node("classify", classify_node)
    g.add_node("fetch_data", fetch_data_node)
    g.add_node("fetch_risk", fetch_risk_node)
    g.add_node("answer_data", answer_data_node)
    g.add_node("answer_guide", answer_guide_node)
    g.add_node("answer_risk", answer_risk_node)
    g.add_node("answer_risk_no_loc", answer_risk_no_loc_node)
    g.add_node("answer_smalltalk", answer_smalltalk_node)

    g.add_edge(START, "classify")
    g.add_conditional_edges(
        "classify",
        _route,
        {
            "data": "fetch_data",
            "guide": "answer_guide",
            "risk": "fetch_risk",
            "risk_no_loc": "answer_risk_no_loc",
            "smalltalk": "answer_smalltalk",
        },
    )
    g.add_edge("fetch_data", "answer_data")
    g.add_edge("fetch_risk", "answer_risk")
    g.add_edge("answer_data", END)
    g.add_edge("answer_guide", END)
    g.add_edge("answer_risk", END)
    g.add_edge("answer_risk_no_loc", END)
    g.add_edge("answer_smalltalk", END)

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
