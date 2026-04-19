"""Notify-route graph — triage an event, decide channels + tone per user, compose message.

Spring sends a candidate event + a user profile list. This graph returns a list of dispatch
plans the scheduler can act on. The graph does NOT send anything — Spring owns delivery.

Graph topology (ed-donner style: START, conditional edges, single-responsibility nodes):

    START
      │
      ▼
    triage          ← compute severity + current hour
      │
      ├─ severity "low"  ──► suppress_all   ← skip LLM for trivial events
      │
      └─ severity ≥ "moderate" ──► plan_users  ← per-user distance/quiet-hour filter
                                        │
                                        ▼
                                     compose    ← LLM writes title+body per active plan
                                        │
                                        ▼
                                       END
"""

from datetime import datetime, timezone
from typing import Any, Literal, TypedDict

from langgraph.graph import END, START, StateGraph

from ..llm import get_llm


Severity = Literal["low", "moderate", "high", "critical"]


class UserProfile(TypedDict, total=False):
    userId: str
    displayName: str
    latitude: float
    longitude: float
    pushoverKey: str
    email: str
    quietHoursStart: int
    quietHoursEnd: int
    hasAnxietyHistory: bool


class EventInput(TypedDict, total=False):
    eventId: str
    magnitude: float
    depthKm: float
    latitude: float
    longitude: float
    location: str
    time: str


class DispatchPlan(TypedDict, total=False):
    userId: str
    channels: list[str]
    tone: str
    title: str
    body: str
    suppress: bool
    reason: str


class NotifyState(TypedDict, total=False):
    event: EventInput
    users: list[UserProfile]
    severity: Severity
    now_hour: int
    plans: list[DispatchPlan]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _severity_of(mag: float, depth: float) -> Severity:
    if mag >= 6.0:
        return "critical"
    if mag >= 5.0:
        return "high"
    if mag >= 4.0:
        return "moderate"
    if mag >= 3.0 and depth <= 15:
        return "moderate"
    return "low"


def _haversine_km(la1: float, lo1: float, la2: float, lo2: float) -> float:
    from math import asin, cos, radians, sin, sqrt
    la1, lo1, la2, lo2 = map(radians, [la1, lo1, la2, lo2])
    dlat, dlon = la2 - la1, lo2 - lo1
    a = sin(dlat / 2) ** 2 + cos(la1) * cos(la2) * sin(dlon / 2) ** 2
    return 6371 * 2 * asin(sqrt(a))


# ---------------------------------------------------------------------------
# Nodes
# ---------------------------------------------------------------------------

async def triage_node(state: NotifyState) -> NotifyState:
    """Single responsibility: compute severity and current UTC hour."""
    ev = state["event"]
    sev = _severity_of(float(ev.get("magnitude", 0)), float(ev.get("depthKm", 0)))
    now_hour = datetime.now(timezone.utc).hour
    return {"severity": sev, "now_hour": now_hour}


def _route_by_severity(state: NotifyState) -> str:
    """Conditional edge: skip LLM entirely for low-severity events."""
    return "suppress_all" if state.get("severity") == "low" else "plan_users"


async def suppress_all_node(state: NotifyState) -> NotifyState:
    """Low-severity shortcut: mark all users suppressed without LLM call."""
    plans: list[DispatchPlan] = [
        {
            "userId": u.get("userId", ""),
            "channels": [], "tone": "n/a", "title": "", "body": "",
            "suppress": True, "reason": f"severity=low, bildirim esigi altinda",
        }
        for u in state.get("users", [])
    ]
    return {"plans": plans}


async def plan_users_node(state: NotifyState) -> NotifyState:
    """Per-user distance filter and quiet-hour check. Sets suppress flag and tone."""
    ev = state["event"]
    sev = state["severity"]
    now_hour = state["now_hour"]
    radius = {"critical": 500.0, "high": 300.0, "moderate": 150.0, "low": 80.0}[sev]
    plans: list[DispatchPlan] = []

    for user in state.get("users", []):
        try:
            dist = _haversine_km(ev["latitude"], ev["longitude"], user["latitude"], user["longitude"])
        except Exception:
            dist = 9999.0

        if dist > radius:
            plans.append({
                "userId": user.get("userId", ""),
                "channels": [], "tone": "n/a", "title": "", "body": "",
                "suppress": True, "reason": f"uzaklik {dist:.0f} km > esik {radius:.0f} km",
            })
            continue

        quiet_start = int(user.get("quietHoursStart", 23))
        quiet_end = int(user.get("quietHoursEnd", 7))
        is_quiet = (quiet_start <= now_hour or now_hour < quiet_end) if quiet_start > quiet_end \
            else (quiet_start <= now_hour < quiet_end)

        if is_quiet and sev in ("low", "moderate"):
            plans.append({
                "userId": user.get("userId", ""),
                "channels": [], "tone": "silent", "title": "", "body": "",
                "suppress": True, "reason": f"sessiz saat ({quiet_start}-{quiet_end}) ve severity={sev}",
            })
            continue

        channels: list[str] = []
        if user.get("pushoverKey"):
            channels.append("pushover")
        if user.get("email"):
            channels.append("email")
        if sev == "critical":
            channels = list({*channels, "email", "pushover"})

        tone: str
        if sev in ("critical", "high"):
            tone = "urgent"
        elif sev == "moderate":
            tone = "informative"
        else:
            tone = "calm"
        if user.get("hasAnxietyHistory") and tone == "urgent":
            tone = "reassuring-urgent"

        plans.append({
            "userId": user.get("userId", ""),
            "channels": channels, "tone": tone, "title": "", "body": "",
            "suppress": False,
            "reason": f"severity={sev} dist={dist:.0f}km quiet={is_quiet}",
            "_context": {"user": user, "event": ev, "distance_km": round(dist, 1)},
        })
    return {"plans": plans}


async def compose_node(state: NotifyState) -> NotifyState:
    """LLM writes title + body only for non-suppressed plans."""
    llm = get_llm()
    ev = state["event"]
    sev = state["severity"]
    out: list[DispatchPlan] = []

    for plan in state.get("plans", []):
        if plan.get("suppress"):
            p = dict(plan)
            p.pop("_context", None)
            out.append(p)
            continue

        ctx = plan.pop("_context", {})
        user = ctx.get("user", {})
        dist = ctx.get("distance_km", 0)
        tone = plan.get("tone", "informative")
        name = user.get("displayName") or "Merhaba"
        prompt = (
            "Turkce, kisa (en fazla 2 cumle) bir deprem bildirim metni yaz. "
            f"Ton: {tone}. Severity: {sev}. "
            f"Kullanici adi: {name}. "
            f"Olay: M{ev.get('magnitude')} {ev.get('location')}, derinlik {ev.get('depthKm')} km, "
            f"kullaniciya uzaklik {dist} km. "
            "Panikletme, net bilgi ver."
        )
        msg = await llm.ainvoke([{"role": "user", "content": prompt}])
        body = getattr(msg, "content", str(msg)).strip()
        title = {
            "critical": f"ACIL: M{ev.get('magnitude')} {ev.get('location')}",
            "high": f"Buyuk deprem: M{ev.get('magnitude')} {ev.get('location')}",
            "moderate": f"Deprem: M{ev.get('magnitude')} {ev.get('location')}",
            "low": f"Hafif sarsinti: M{ev.get('magnitude')} {ev.get('location')}",
        }[sev]
        p = dict(plan)
        p["title"] = title
        p["body"] = body
        out.append(p)

    return {"plans": out}


# ---------------------------------------------------------------------------
# Graph construction (ed-donner style: START, conditional edges)
# ---------------------------------------------------------------------------

def build_notify_graph():
    g = StateGraph(NotifyState)

    g.add_node("triage", triage_node)
    g.add_node("suppress_all", suppress_all_node)
    g.add_node("plan_users", plan_users_node)
    g.add_node("compose", compose_node)

    g.add_edge(START, "triage")
    g.add_conditional_edges(
        "triage",
        _route_by_severity,
        {
            "suppress_all": "suppress_all",
            "plan_users": "plan_users",
        },
    )
    g.add_edge("suppress_all", END)
    g.add_edge("plan_users", "compose")
    g.add_edge("compose", END)

    return g.compile()


_compiled = None


def get_notify_graph():
    global _compiled
    if _compiled is None:
        _compiled = build_notify_graph()
    return _compiled
