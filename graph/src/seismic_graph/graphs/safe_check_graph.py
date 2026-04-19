"""Safe-check graph — prepares a family notification plan and summary.

Spring owns persistence and delivery; LangGraph owns the explainable state transition:
  triage (classify status) → compose (write family message) → summarize

Graph topology (ed-donner style: START constant, conditional edges):

    START
      │
      ▼
    triage          ← classify SAFE / NEEDS_HELP / UNKNOWN, set urgency
      │
      ├─ urgency "low" (SAFE) ──► compose_safe      ← short reassuring message
      │
      └─ urgency ≥ "moderate" ──► compose_urgent    ← clear, calm urgent message
                                        │
                                        ▼
                                     summarize       ← count delivery targets
                                        │
                                        ▼
                                       END
"""

from typing import Literal, TypedDict

from langgraph.graph import END, START, StateGraph

from ..llm import get_llm


Status = Literal["SAFE", "NEEDS_HELP", "UNKNOWN"]


class SafeCheckState(TypedDict, total=False):
    user: dict
    checkin: dict
    family: list[dict]
    urgency: str
    title: str
    body: str
    channels: list[str]
    summary: str


# ---------------------------------------------------------------------------
# Nodes
# ---------------------------------------------------------------------------

async def triage_node(state: SafeCheckState) -> SafeCheckState:
    """Single responsibility: classify urgency and set delivery channels."""
    status = state.get("checkin", {}).get("status", "UNKNOWN")
    urgency = {"SAFE": "low", "UNKNOWN": "moderate", "NEEDS_HELP": "critical"}.get(status, "moderate")
    channels = ["pushover", "email"]
    return {"urgency": urgency, "channels": channels}


def _route_by_urgency(state: SafeCheckState) -> str:
    """Conditional edge: different LLM tone for safe vs urgent status."""
    return "compose_safe" if state.get("urgency") == "low" else "compose_urgent"


async def compose_safe_node(state: SafeCheckState) -> SafeCheckState:
    """SAFE path: short reassuring message. Uses shared LLM singleton."""
    llm = get_llm()
    user = state.get("user", {})
    checkin = state.get("checkin", {})
    family = state.get("family", [])
    name = user.get("displayName") or user.get("email") or "Aile uyeniz"
    note = checkin.get("note") or ""
    lat, lon = checkin.get("latitude"), checkin.get("longitude")

    prompt = (
        "Turkce, kisa ve rahatlatici bir aile bildirimi yaz (en fazla 2 cumle). "
        "Kisi guvende, aileyi gereksiz endise ettirme.\n\n"
        f"Kisi: {name}\nDurum: SAFE\nNot: {note or '(not yok)'}\nKonum: {lat}, {lon}\nAlici: {len(family)} kisi\n"
    )
    msg = await llm.ainvoke([{"role": "user", "content": prompt}])
    body = getattr(msg, "content", str(msg)).strip()
    return {"title": f"{name} güvende", "body": body}


async def compose_urgent_node(state: SafeCheckState) -> SafeCheckState:
    """NEEDS_HELP / UNKNOWN path: clear, calm message without panicking family."""
    llm = get_llm()
    user = state.get("user", {})
    checkin = state.get("checkin", {})
    family = state.get("family", [])
    name = user.get("displayName") or user.get("email") or "Aile uyeniz"
    status = checkin.get("status", "UNKNOWN")
    note = checkin.get("note") or ""
    lat, lon = checkin.get("latitude"), checkin.get("longitude")

    prompt = (
        "Turkce, kisa ve sakin bir aile bildirimi yaz (en fazla 2 cumle). "
        "Panikletme, net bilgi ver, gereksiz detay ekleme.\n\n"
        f"Kisi: {name}\nDurum: {status}\nNot: {note or '(not yok)'}\nKonum: {lat}, {lon}\nAlici: {len(family)} kisi\n"
    )
    msg = await llm.ainvoke([{"role": "user", "content": prompt}])
    body = getattr(msg, "content", str(msg)).strip()
    title = {
        "NEEDS_HELP": f"YARDIM GEREKIYOR: {name}",
        "UNKNOWN": f"Durum bilinmiyor: {name}",
    }.get(status, f"Durum guncellemesi: {name}")
    return {"title": title, "body": body}


async def summarize_node(state: SafeCheckState) -> SafeCheckState:
    """Count how many delivery targets will receive the message."""
    family = state.get("family", [])
    channels = state.get("channels", [])
    total_targets = sum(
        ("pushover" in channels and bool(m.get("pushoverKey"))) +
        ("email" in channels and bool(m.get("email")))
        for m in family
    )
    return {"summary": f"{len(family)} aile uyesi icin {total_targets} kanal teslimat plani hazirlandi."}


# ---------------------------------------------------------------------------
# Graph construction (ed-donner style: START, conditional edges)
# ---------------------------------------------------------------------------

def build_safe_check_graph():
    g = StateGraph(SafeCheckState)

    g.add_node("triage", triage_node)
    g.add_node("compose_safe", compose_safe_node)
    g.add_node("compose_urgent", compose_urgent_node)
    g.add_node("summarize", summarize_node)

    g.add_edge(START, "triage")
    g.add_conditional_edges(
        "triage",
        _route_by_urgency,
        {
            "compose_safe": "compose_safe",
            "compose_urgent": "compose_urgent",
        },
    )
    g.add_edge("compose_safe", "summarize")
    g.add_edge("compose_urgent", "summarize")
    g.add_edge("summarize", END)

    return g.compile()


_compiled = None


def get_safe_check_graph():
    global _compiled
    if _compiled is None:
        _compiled = build_safe_check_graph()
    return _compiled
