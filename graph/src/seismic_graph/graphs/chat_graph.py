"""Chat graph — classifies a user question, then branches to data / guide / risk / smalltalk.

Graph topology (ed-donner style: START constant, conditional edges, Annotated reducer):

    START
      │
      ▼
   classify   ← heuristic keyword routing (no LLM token cost)
      │
      ├─ "data"      ──► fetch_data ──► answer_data
      ├─ "guide"     ──────────────────► answer_guide
      ├─ "risk"      ──► fetch_risk ──► answer_risk
      └─ "smalltalk" ──────────────────► answer_smalltalk
                                │
                                └──► END
"""

from operator import add
from typing import Annotated, Any, Literal, TypedDict  # noqa: F401 — Any used in get_chat_graph signature

from langgraph.graph import END, START, StateGraph

from ..llm import get_llm
from ..spring_client import get_spring_client


Category = Literal["data", "guide", "risk", "smalltalk"]


class ChatState(TypedDict, total=False):
    question: str
    user_context: dict
    # Annotated[list, add] accumulates turns across checkpointed invocations
    # (same pattern as add_messages in ed-donner/agents)
    turns: Annotated[list[dict[str, str]], add]
    category: Category
    fetched: dict
    answer: str
    sources: list[str]


_GUIDE_KEYWORDS = ("ne yap", "nasil", "nasıl", "hazirlan", "hazırlan", "canta", "çanta", "rehber", "tavsiye")
_DATA_KEYWORDS = ("son", "bugun", "bugün", "dun", "dün", "deprem oldu", "buyukluk", "büyüklük", "kac deprem", "kaç deprem")
_RISK_KEYWORDS = ("benim", "bolgem", "bölgem", "sehrim", "şehrim", "evim", "risk", "tehlike")


def _classify_heuristic(question: str) -> Category:
    q = question.lower()
    if any(k in q for k in _GUIDE_KEYWORDS):
        return "guide"
    if any(k in q for k in _RISK_KEYWORDS):
        return "risk"
    if any(k in q for k in _DATA_KEYWORDS):
        return "data"
    return "smalltalk"


def _history_snippet(state: ChatState, limit: int = 6) -> str:
    turns = state.get("turns", [])[-limit:]
    if not turns:
        return "(gecmis yok)"
    return "\n".join(f"{t.get('role', '?')}: {t.get('text', '')}" for t in turns)


# ---------------------------------------------------------------------------
# Nodes
# ---------------------------------------------------------------------------

async def classify_node(state: ChatState) -> ChatState:
    question = state["question"]
    return {
        "category": _classify_heuristic(question),
        "turns": [{"role": "user", "text": question}],
    }


async def fetch_data_node(state: ChatState) -> ChatState:
    client = get_spring_client()
    rows = await client.recent_earthquakes(hours=24, min_magnitude=2.0, limit=20)
    return {"fetched": {"earthquakes": rows}, "sources": ["Kandilli / koeri.boun.edu.tr"]}


async def fetch_risk_node(state: ChatState) -> ChatState:
    client = get_spring_client()
    rows = await client.recent_earthquakes(hours=168, min_magnitude=3.0, limit=50)
    ctx = state.get("user_context") or {}
    filtered = rows
    if "latitude" in ctx and "longitude" in ctx:
        from math import asin, cos, radians, sin, sqrt
        def _near(r: dict) -> bool:
            try:
                la1, lo1 = radians(ctx["latitude"]), radians(ctx["longitude"])
                la2, lo2 = radians(r["latitude"]), radians(r["longitude"])
                dlat, dlon = la2 - la1, lo2 - lo1
                a = sin(dlat / 2) ** 2 + cos(la1) * cos(la2) * sin(dlon / 2) ** 2
                return 6371 * 2 * asin(sqrt(a)) <= 200
            except Exception:
                return False
        filtered = [r for r in rows if _near(r)]
    return {"fetched": {"nearby": filtered[:15], "user_context": ctx}, "sources": ["Kandilli"]}


async def answer_with_data_node(state: ChatState) -> ChatState:
    llm = get_llm()
    rows = state.get("fetched", {}).get("earthquakes", [])
    context_lines = [
        f"- M{r.get('magnitude')} {r.get('location')} ({r.get('time')}, derinlik {r.get('depthKm')} km)"
        for r in rows[:10]
    ]
    prompt = (
        "Kullanici deprem verisi sordu. Asagidaki son Kandilli kayitlarini kullanarak kisa, net, Turkce yanit ver. "
        "Uydurma, yalnizca listedeki veriyi kullan.\n\n"
        f"Konusma gecmisi:\n{_history_snippet(state)}\n\n"
        "Son depremler:\n" + ("\n".join(context_lines) if context_lines else "(veri alinamadi)") + "\n\n"
        f"Soru: {state['question']}\n"
    )
    msg = await llm.ainvoke([{"role": "user", "content": prompt}])
    answer = getattr(msg, "content", str(msg))
    return {"answer": answer, "turns": [{"role": "assistant", "text": answer}]}


async def answer_guide_node(state: ChatState) -> ChatState:
    llm = get_llm()
    prompt = (
        "Kullanici deprem guvenligi ile ilgili bir soru sordu. Kisa, uygulanabilir, Turkce, madde-isaretli yanit ver. "
        "Ic mekan, dis mekan, arac icinde gibi duruma gore ayir. Kaynak uydurma.\n\n"
        f"Konusma gecmisi:\n{_history_snippet(state)}\n\n"
        f"Soru: {state['question']}"
    )
    msg = await llm.ainvoke([{"role": "user", "content": prompt}])
    answer = getattr(msg, "content", str(msg))
    return {"answer": answer, "turns": [{"role": "assistant", "text": answer}], "sources": ["AFAD rehberi (genel bilgi)"]}


async def answer_risk_node(state: ChatState) -> ChatState:
    llm = get_llm()
    nearby = state.get("fetched", {}).get("nearby", [])
    ctx = state.get("fetched", {}).get("user_context", {})
    loc_hint = f"{ctx.get('latitude')}, {ctx.get('longitude')}" if "latitude" in ctx else "bilinmiyor"
    rows_txt = "\n".join(f"- M{r.get('magnitude')} {r.get('location')} ({r.get('time')})" for r in nearby[:8]) or "(yakin kayit yok)"
    prompt = (
        "Kullanici kendi bolgesi icin risk yorumu istedi. Son 1 haftalik yakin deprem kayitlarina bakarak "
        "kisa bir durum yorumu yap. Abartma, falcilik yapma. Turkce, 3-4 cumle.\n\n"
        f"Konusma gecmisi:\n{_history_snippet(state)}\n\n"
        f"Kullanici konumu: {loc_hint}\n"
        f"Yakin kayitlar:\n{rows_txt}\n\n"
        f"Soru: {state['question']}"
    )
    msg = await llm.ainvoke([{"role": "user", "content": prompt}])
    answer = getattr(msg, "content", str(msg))
    return {"answer": answer, "turns": [{"role": "assistant", "text": answer}], "sources": ["Kandilli"]}


async def answer_smalltalk_node(state: ChatState) -> ChatState:
    llm = get_llm()
    prompt = (
        "Sen Deprem Rehberim uygulamasinin AI asistanisin. Kullaniciyi kisaca selamla, "
        "hangi konularda yardimci olabilecegini 2 madde halinde belirt (son depremler, guvenlik rehberi, bolge riski).\n\n"
        f"Konusma gecmisi:\n{_history_snippet(state)}\n\n"
        f"Kullanici: {state['question']}"
    )
    msg = await llm.ainvoke([{"role": "user", "content": prompt}])
    answer = getattr(msg, "content", str(msg))
    return {"answer": answer, "turns": [{"role": "assistant", "text": answer}]}


def _route(state: ChatState) -> str:
    return state.get("category", "smalltalk")


# ---------------------------------------------------------------------------
# Graph construction (ed-donner style: START constant, conditional edges)
# ---------------------------------------------------------------------------

def build_chat_graph(checkpointer=None):
    g = StateGraph(ChatState)

    g.add_node("classify", classify_node)
    g.add_node("fetch_data", fetch_data_node)
    g.add_node("fetch_risk", fetch_risk_node)
    g.add_node("answer_data", answer_with_data_node)
    g.add_node("answer_guide", answer_guide_node)
    g.add_node("answer_risk", answer_risk_node)
    g.add_node("answer_smalltalk", answer_smalltalk_node)

    g.add_edge(START, "classify")
    g.add_conditional_edges(
        "classify",
        _route,
        {
            "data": "fetch_data",
            "guide": "answer_guide",
            "risk": "fetch_risk",
            "smalltalk": "answer_smalltalk",
        },
    )
    g.add_edge("fetch_data", "answer_data")
    g.add_edge("fetch_risk", "answer_risk")
    g.add_edge("answer_data", END)
    g.add_edge("answer_guide", END)
    g.add_edge("answer_risk", END)
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
