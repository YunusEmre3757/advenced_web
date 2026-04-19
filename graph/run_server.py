"""Windows-safe launcher for the LangGraph FastAPI service."""

import asyncio
import os
import sys


if sys.platform.startswith("win"):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

import uvicorn

if sys.platform.startswith("win"):
    import uvicorn.loops.asyncio

    uvicorn.loops.asyncio.asyncio_loop_factory = lambda use_subprocess=False: asyncio.SelectorEventLoop


if __name__ == "__main__":
    port = int(os.environ.get("GRAPH_PORT", "8002"))
    uvicorn.run(
        "seismic_graph.api:app",
        host="127.0.0.1",
        port=port,
        reload=False,
        loop="asyncio",
    )
