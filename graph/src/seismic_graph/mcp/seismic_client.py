"""HTTP MCP client used by Graph workflows and the MCP inspector page."""

import json
from typing import Any



import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

from ..config import MCP_SERVER_URL


async def run_mcp_demo(
    tool_name: str = "get_recent_earthquakes",
    arguments: dict[str, Any] | None = None,
    # Legacy convenience params — used when tool_name is get_recent_earthquakes
    hours: int = 24,
    min_magnitude: float = 1.0,
    limit: int = 8,
) -> dict[str, Any]:
    """Discover tools and call one tool through the long-running MCP endpoint.

    Args:
        tool_name: Name of the MCP tool to call (must match a registered tool).
        arguments: Explicit argument dict. When None and tool_name is
                   'get_recent_earthquakes', the legacy hours/min_magnitude/limit
                   params are used to build the dict automatically.
    """
    if arguments is None:
        if tool_name == "get_recent_earthquakes":
            arguments = {"hours": hours, "min_magnitude": min_magnitude, "limit": limit}
        else:
            arguments = {}

    async with _mcp_session() as session:
        init = await session.initialize()
        tools_result = await session.list_tools()
        tool_result = await session.call_tool(tool_name, arguments)

    tools = [_tool_to_dict(tool) for tool in tools_result.tools]
    result_payload = _extract_tool_payload(tool_result)
    is_error = bool(getattr(tool_result, "isError", False))

    return {
        "transport": "streamable-http",
        "endpoint": MCP_SERVER_URL,
        "server": {
            "name": init.serverInfo.name,
            "version": init.serverInfo.version,
            "protocolVersion": init.protocolVersion,
            "instructions": init.instructions,
        },
        "steps": [
            {
                "name": "connect",
                "label": "MCP HTTP bağlantısı kuruldu",
                "status": "ok",
                "detail": MCP_SERVER_URL,
            },
            {
                "name": "initialize",
                "label": "MCP initialize",
                "status": "ok",
                "detail": f"protocol {init.protocolVersion} · {init.serverInfo.name}",
            },
            {
                "name": "tools_list",
                "label": "tools/list",
                "status": "ok" if tools else "empty",
                "detail": f"{len(tools)} tool keşfedildi: {', '.join(t['name'] for t in tools)}",
            },
            {
                "name": "tools_call",
                "label": f"tools/call {tool_name}",
                "status": "error" if is_error else "ok",
                "detail": f"args: {json.dumps(arguments, ensure_ascii=False)}",
            },
            {
                "name": "result",
                "label": "Yapılandırılmış sonuç",
                "status": "ok" if result_payload else "empty",
                "detail": "JSON sonuç Graph API ve Angular UI'ye iletildi",
            },
        ],
        "tools": tools,
        "selectedTool": tool_name,
        "arguments": arguments,
        "result": result_payload,
        "stderr": "",
        "explanation": [
            "MCP sunucusu graph servisinin içinde HTTP endpoint olarak mount edilmiş durumda.",
            "MCP istemcisi tools/list ile mevcut tool şemalarını runtime'da keşfeder.",
            "Seçilen tool, tools/call ile streamable HTTP üzerinden çağrılır.",
            "AI Assistant da aynı MCP endpoint'ini gerçek veri ve risk sorularında kullanır.",
            "Claude Desktop veya Cursor gibi dış MCP host'lar da bu endpoint'e bağlanabilir.",
        ],
    }


async def call_mcp_tool(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    """Call one seismic MCP tool over the graph service's HTTP MCP endpoint."""
    async with _mcp_session() as session:
        init = await session.initialize()
        tool_result = await session.call_tool(name, arguments)

    return {
        "server": {
            "name": init.serverInfo.name,
            "version": init.serverInfo.version,
            "protocolVersion": init.protocolVersion,
        },
        "tool": name,
        "arguments": arguments,
        "isError": bool(tool_result.isError),
        "result": _extract_tool_payload(tool_result),
        "stderr": "",
    }


class _mcp_session:
    def __init__(self):
        self._http_client: httpx.AsyncClient | None = None
        self._transport = None
        self._session: ClientSession | None = None

    async def __aenter__(self) -> ClientSession:
        self._http_client = httpx.AsyncClient(timeout=httpx.Timeout(12.0, read=60.0))
        self._transport = streamable_http_client(MCP_SERVER_URL, http_client=self._http_client)
        read_stream, write_stream, _ = await self._transport.__aenter__()
        self._session = ClientSession(read_stream, write_stream)
        return await self._session.__aenter__()

    async def __aexit__(self, exc_type, exc, tb) -> None:
        if self._session is not None:
            await self._session.__aexit__(exc_type, exc, tb)
        if self._transport is not None:
            await self._transport.__aexit__(exc_type, exc, tb)
        if self._http_client is not None:
            await self._http_client.aclose()


def _tool_to_dict(tool: Any) -> dict[str, Any]:
    return {
        "name": tool.name,
        "title": tool.title,
        "description": tool.description,
        "inputSchema": tool.inputSchema,
        "outputSchema": tool.outputSchema,
    }


def _extract_tool_payload(tool_result: Any) -> dict[str, Any]:
    if getattr(tool_result, "structuredContent", None) is not None:
        return tool_result.structuredContent

    text_blocks = [
        block.text
        for block in getattr(tool_result, "content", [])
        if getattr(block, "type", None) == "text" and getattr(block, "text", None)
    ]
    if not text_blocks:
        return {}

    first = text_blocks[0]
    try:
        payload = json.loads(first)
        return payload if isinstance(payload, dict) else {"value": payload}
    except json.JSONDecodeError:
        return {"text": "\n".join(text_blocks)}

