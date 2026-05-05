"""FastAPI surface for the LangGraph orchestrations.

Run:
    cd graph
    uvicorn seismic_graph.api:app --port 8002 --reload
"""

import asyncio
import json
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, field_validator
from typing import Literal

from .checkpoint import close_checkpointer, get_checkpointer, setup_checkpointer
from .config import DRY_RUN, GRAPH_CHECKPOINT_MODE, GRAPH_PORT, LANGSMITH_PROJECT, LANGSMITH_TRACING
from .graphs.chat_graph import get_chat_graph, reset_chat_graph
from .graphs.building_risk_graph import get_building_risk_graph
from .graphs.notify_graph import get_notify_graph
from .graphs.quake_detail_graph import get_quake_detail_graph
from .graphs.safe_check_graph import get_safe_check_graph
from .mcp.seismic_client import run_mcp_demo
from .mcp.seismic_server import mcp as seismic_mcp
from .spring_client import get_spring_client


seismic_mcp_app = seismic_mcp.streamable_http_app()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    if LANGSMITH_TRACING:
        import os
        os.environ.setdefault("LANGCHAIN_TRACING_V2", "true")
        os.environ.setdefault("LANGCHAIN_PROJECT", LANGSMITH_PROJECT)

    checkpointer = await setup_checkpointer()
    reset_chat_graph()
    get_chat_graph(checkpointer)
    async with seismic_mcp.session_manager.run():
        yield
    await get_spring_client().close()
    await close_checkpointer()


app = FastAPI(title="Seismic Graph Service", version="0.2.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/mcp", seismic_mcp_app)


class ChatRequest(BaseModel):
    question: str
    sessionId: str = "default"
    userContext: dict[str, Any] | None = None


class ChatResponse(BaseModel):
    answer: str
    category: str
    sources: list[str] = Field(default_factory=list)
    sessionId: str


class NotifyRouteRequest(BaseModel):
    event: dict[str, Any]
    users: list[dict[str, Any]]


class NotifyRouteResponse(BaseModel):
    severity: str
    plans: list[dict[str, Any]]


class QuakeDetailRequest(BaseModel):
    eventId: str


class QuakeDetailResponse(BaseModel):
    event: dict[str, Any]
    aftershocks: list[dict[str, Any]]
    similar: list[dict[str, Any]]
    dyfi: dict[str, Any] | None = None
    shakemap: dict[str, Any] | None = None
    depth: str
    summary: str
    riskLevel: str
    recommendations: list[str]


class SafeCheckRequest(BaseModel):
    user: dict[str, Any]
    checkin: dict[str, Any]
    family: list[dict[str, Any]] = Field(default_factory=list)


class SafeCheckResponse(BaseModel):
    urgency: str
    title: str
    body: str
    channels: list[str]
    summary: str


class BuildingRiskRequest(BaseModel):
    building: dict[str, Any]
    location: dict[str, Any] | None = None


class BuildingRiskResponse(BaseModel):
    totalScore: int
    level: str
    label: str
    confidence: str
    componentScores: dict[str, int]
    primaryDrivers: list[str] = Field(default_factory=list)
    buildingDrivers: list[str] = Field(default_factory=list)
    locationDrivers: list[str] = Field(default_factory=list)
    recommendedActions: list[str] = Field(default_factory=list)
    cautions: list[str] = Field(default_factory=list)
    summary: str
    context: dict[str, Any] = Field(default_factory=dict)
    sources: list[str] = Field(default_factory=list)


class McpDemoRequest(BaseModel):
    toolName: str = Field(default="get_recent_earthquakes")
    arguments: dict[str, Any] = Field(default_factory=dict)
    # Legacy convenience fields kept for backwards compatibility
    hours: int = Field(default=24, ge=1, le=168)
    minMagnitude: float = Field(default=1.0, ge=0.0, le=10.0)
    limit: int = Field(default=8, ge=1, le=20)


class McpDemoResponse(BaseModel):
    transport: str
    endpoint: str
    server: dict[str, Any]
    steps: list[dict[str, Any]]
    tools: list[dict[str, Any]]
    selectedTool: str
    arguments: dict[str, Any]
    result: dict[str, Any]
    stderr: str = ""
    explanation: list[str]


@app.get("/health", tags=["System"])
async def health():
    """Health check — verify LangGraph service is running.

    Returns service status, dry-run mode, and configuration details.
    """
    return {
        "status": "ok",
        "dryRun": DRY_RUN,
        "port": GRAPH_PORT,
        "checkpointMode": GRAPH_CHECKPOINT_MODE,
    }


@app.post("/graph/mcp-demo", response_model=McpDemoResponse, tags=["MCP"])
async def mcp_demo_endpoint(req: McpDemoRequest):
    """MCP Inspector — connect to the HTTP MCP endpoint and call any registered tool.

    Accepts any tool name and its arguments so the Angular demo page can
    call all 8 tools interactively for class demonstration.
    """
    args = req.arguments or {}
    if not args and req.toolName == "get_recent_earthquakes":
        args = {"hours": req.hours, "min_magnitude": req.minMagnitude, "limit": req.limit}
    return await run_mcp_demo(tool_name=req.toolName, arguments=args)


@app.post("/graph/chat", response_model=ChatResponse, tags=["Graphs"])
async def chat_endpoint(req: ChatRequest):
    """Chat Graph — stateful multi-turn conversation with context.

    Maintains session state across multiple turns. Detects question category:
    - earthquake_analysis: magnitude, depth, location analysis
    - fault_correlation: fault lines near epicenter
    - risk_assessment: building/infrastructure impact
    - planning: evacuation, emergency response
    - smalltalk: general seismic knowledge

    Uses LLM (Groq LLaMA 3.3 70B) with LangSmith tracing if enabled.
    """
    graph = get_chat_graph(get_checkpointer())
    state = {
        "question": req.question,
        "user_context": req.userContext or {},
    }
    config = {"configurable": {"thread_id": req.sessionId}}
    result = await graph.ainvoke(state, config=config)
    return ChatResponse(
        answer=result.get("answer", ""),
        category=result.get("category", "smalltalk"),
        sources=result.get("sources", []),
        sessionId=req.sessionId,
    )


@app.get("/graph/chat/stream", tags=["Graphs"])
async def chat_stream_endpoint(
    question: str,
    sessionId: str = "default",
    latitude: float | None = None,
    longitude: float | None = None,
):
    """Chat Graph (Streaming) — Server-Sent Events response for token streaming.

    Streams LLM output token-by-token for real-time UI feedback. Optional latitude/longitude
    for location-aware context injection.

    Response events:
    - meta: category, sources, sessionId
    - token: individual LLM output tokens (Türkçe)
    - done: final answer with metadata
    """
    async def _events():
        ctx: dict[str, Any] = {}
        if latitude is not None and longitude is not None:
            ctx = {"latitude": latitude, "longitude": longitude}
        graph = get_chat_graph(get_checkpointer())
        result = await graph.ainvoke(
            {"question": question, "user_context": ctx},
            config={"configurable": {"thread_id": sessionId}},
        )
        meta = {
            "category": result.get("category", "smalltalk"),
            "sources": result.get("sources", []),
            "sessionId": sessionId,
        }
        yield f"event: meta\ndata: {json.dumps(meta, ensure_ascii=False)}\n\n"
        answer = result.get("answer", "")
        for token in answer.split(" "):
            if token:
                yield f"event: token\ndata: {json.dumps(token + ' ', ensure_ascii=False)}\n\n"
                await asyncio.sleep(0.015)
        done = {"answer": answer, **meta}
        yield f"event: done\ndata: {json.dumps(done, ensure_ascii=False)}\n\n"

    return StreamingResponse(_events(), media_type="text/event-stream")


@app.post("/graph/notify-route", response_model=NotifyRouteResponse, tags=["Graphs"])
async def notify_route_endpoint(req: NotifyRouteRequest):
    """Notify Route Graph — LLM-based notification severity routing.

    Routes incoming earthquake events to appropriate notification channels
    and communication plans based on magnitude, depth, proximity to settlements.

    Returns severity level (low, medium, high, critical) and notification plans.
    """
    graph = get_notify_graph()
    result = await graph.ainvoke({"event": req.event, "users": req.users})
    return NotifyRouteResponse(
        severity=result.get("severity", "low"),
        plans=result.get("plans", []),
    )


@app.post("/graph/safe-check", response_model=SafeCheckResponse, tags=["Graphs"])
async def safe_check_endpoint(req: SafeCheckRequest):
    """Safe Check Graph — LLM-driven family safety assessment.

    Analyzes user checkin status, location, family member proximity during earthquake.
    Generates multi-channel alerts (SMS, push, email, siren) based on risk level.

    Returns urgency, alert body, channels, and summary.
    """
    graph = get_safe_check_graph()
    result = await graph.ainvoke({
        "user": req.user,
        "checkin": req.checkin,
        "family": req.family,
    })
    return SafeCheckResponse(
        urgency=result.get("urgency", "moderate"),
        title=result.get("title", ""),
        body=result.get("body", ""),
        channels=result.get("channels", []),
        summary=result.get("summary", ""),
    )


@app.post("/graph/quake-detail", response_model=QuakeDetailResponse, tags=["Graphs"])
async def quake_detail_endpoint(req: QuakeDetailRequest):
    """Quake Detail Graph — Multi-source earthquake enrichment.

    Fetches event details from USGS, computes aftershock probability, finds similar
    historical events, retrieves DYFI (Did You Feel It?) and ShakeMap data.

    Returns event metadata, aftershocks, similar events, depth assessment, risk level.
    """
    graph = get_quake_detail_graph()
    result = await graph.ainvoke({"eventId": req.eventId})
    return QuakeDetailResponse(
        event=result.get("event", {}),
        aftershocks=result.get("aftershocks", []),
        similar=result.get("similar", []),
        dyfi=result.get("dyfi"),
        shakemap=result.get("shakemap"),
        depth=result.get("depth", "standard"),
        summary=result.get("summary", ""),
        riskLevel=result.get("risk_level", "low"),
        recommendations=result.get("recommendations", []),
    )


@app.post("/graph/building-risk", response_model=BuildingRiskResponse, tags=["Graphs"])
async def building_risk_endpoint(req: BuildingRiskRequest):
    """Building Risk Graph — Deterministic + LLM agentic loop (ed-donner pattern).

    **Pipeline:**
    1. collect_context: Parallel fetch fault lines + historical + recent earthquakes (async)
    2. score: Rule-based deterministic scoring (35-component matrix, no LLM)
    3. branch: Route to brief/standard/deep analysis based on totalScore
    4. *_analysis: LLM generates Türkçe risk assessment with structured output
    5. evaluator: LLM judges its own summary; if needed, loops back to score (max 2 retries)

    **Scoring Components:**
    - Structural (35/100): age, floors, system, visible damage, retrofit
    - Soil (15/100): zone classification (ZA-ZF)
    - Fault Proximity (20/100): distance, slip rate, seismic gap
    - Historical Seismicity (15/100): nearby M4.5+ events, max magnitude
    - Observed Damage (20/100): cracks, past damage

    Returns structured analysis, recommendations, drivers, fay context, sources.
    """
    graph = get_building_risk_graph()
    result = await graph.ainvoke({
        "building": req.building,
        "location": req.location,
    })
    return BuildingRiskResponse(
        totalScore=result.get("totalScore", 0),
        level=result.get("level", "orta"),
        label=result.get("label", "Orta risk"),
        confidence=result.get("confidence", "orta"),
        componentScores=result.get("componentScores", {}),
        primaryDrivers=result.get("primaryDrivers", []),
        buildingDrivers=result.get("buildingDrivers", []),
        locationDrivers=result.get("locationDrivers", []),
        recommendedActions=result.get("recommendedActions", []),
        cautions=result.get("cautions", []),
        summary=result.get("summary", ""),
        context=result.get("context", {}),
        sources=result.get("sources", []),
    )
