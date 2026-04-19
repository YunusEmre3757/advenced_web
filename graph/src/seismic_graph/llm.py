"""LLM singleton with DRY_RUN fallback and structured output support.

Pattern mirrors ed-donner/agents: LLM is built once at import time and reused
across all graph nodes — no per-call instantiation overhead.
"""

from typing import Any, Type, TypeVar
from pydantic import BaseModel

from .config import DRY_RUN, GROQ_API_KEY, GROQ_MODEL

T = TypeVar("T", bound=BaseModel)


class _DryRunLLM:
    """Deterministic echo for tests / no-API-key dev."""

    async def ainvoke(self, messages: list[Any]) -> Any:
        last = messages[-1] if messages else None
        content = getattr(last, "content", None) or (last.get("content") if isinstance(last, dict) else "")
        preview = (content or "")[:180]

        class _Msg:
            def __init__(self, c: str):
                self.content = c

        return _Msg(f"[DRY_RUN cevap - GROQ_API_KEY tanimli degil]\nSoru izi: {preview}")

    def invoke(self, messages: list[Any]) -> Any:
        import asyncio
        return asyncio.get_event_loop().run_until_complete(self.ainvoke(messages))

    def with_structured_output(self, schema: Type[T]) -> "_DryRunStructured[T]":
        return _DryRunStructured(schema)


class _DryRunStructured:
    """Returns a zero-filled Pydantic model instance in DRY_RUN mode."""

    def __init__(self, schema: Type[T]):
        self._schema = schema

    async def ainvoke(self, messages: list[Any]) -> Any:
        return self._schema.model_construct()

    def invoke(self, messages: list[Any]) -> Any:
        return self._schema.model_construct()


def _build_real_llm():
    from langchain_groq import ChatGroq
    return ChatGroq(model=GROQ_MODEL, api_key=GROQ_API_KEY, temperature=0.3)


# Single instance — built once, reused by all nodes (ed-donner pattern)
_llm: Any = None


def get_llm() -> Any:
    global _llm
    if _llm is None:
        _llm = _DryRunLLM() if DRY_RUN else _build_real_llm()
    return _llm


def get_structured_llm(schema: Type[T]) -> Any:
    """Returns an LLM bound to a Pydantic schema for guaranteed structured output."""
    llm = get_llm()
    if DRY_RUN:
        return _DryRunStructured(schema)
    return llm.with_structured_output(schema)
