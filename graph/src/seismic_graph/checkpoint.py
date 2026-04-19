"""LangGraph checkpoint lifecycle.

The service uses Postgres by default so chat thread state survives process restarts.
Set GRAPH_CHECKPOINT_MODE=memory only for isolated local demos.
"""

from contextlib import AbstractAsyncContextManager
import asyncio
import sys
from typing import Any

from langgraph.checkpoint.memory import MemorySaver

from .config import GRAPH_CHECKPOINT_MODE, GRAPH_DATABASE_URL


if sys.platform.startswith("win"):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

_checkpointer: Any | None = None
_ctx: AbstractAsyncContextManager | None = None


async def setup_checkpointer() -> Any:
    global _checkpointer, _ctx
    if _checkpointer is not None:
        return _checkpointer

    if GRAPH_CHECKPOINT_MODE == "memory":
        _checkpointer = MemorySaver()
        return _checkpointer

    from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

    _ctx = AsyncPostgresSaver.from_conn_string(GRAPH_DATABASE_URL)
    _checkpointer = await _ctx.__aenter__()
    await _checkpointer.setup()
    return _checkpointer


def get_checkpointer() -> Any:
    if _checkpointer is None:
        raise RuntimeError("LangGraph checkpointer is not initialized")
    return _checkpointer


async def close_checkpointer() -> None:
    global _checkpointer, _ctx
    if _ctx is not None:
        await _ctx.__aexit__(None, None, None)
    _checkpointer = None
    _ctx = None
