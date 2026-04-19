"""LLM singleton with DRY_RUN fallback and structured output support.

Pattern mirrors ed-donner/agents: LLM is built once at import time and reused
across all graph nodes — no per-call instantiation overhead.

Temperature guide:
  0.0 — deterministic/structured output (building risk analysis, evaluator)
  0.3 — balanced default (quake detail, notify, safe check)
  0.7 — creative/conversational (chat smalltalk)
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
    """Returns sensible default Pydantic model instances in DRY_RUN mode."""

    def __init__(self, schema: Type[T]):
        self._schema = schema

    def _make_defaults(self) -> dict:
        """Build field defaults so DRY_RUN responses are non-empty."""
        defaults: dict = {}
        for name, field in self._schema.model_fields.items():
            ann = field.annotation
            origin = getattr(ann, "__origin__", None)
            if ann is str or ann == "str":
                defaults[name] = f"[DRY_RUN] {name}"
            elif ann is bool:
                defaults[name] = True
            elif origin is list:
                defaults[name] = [f"[DRY_RUN] {name}[0]"]
            elif hasattr(ann, "__args__") and str in getattr(ann, "__args__", ()):
                # Literal[...] — pick first option
                args = ann.__args__
                defaults[name] = args[0] if args else ""
        return defaults

    async def ainvoke(self, messages: list[Any]) -> Any:
        return self._schema.model_construct(**self._make_defaults())

    def invoke(self, messages: list[Any]) -> Any:
        return self._schema.model_construct(**self._make_defaults())


def _build_real_llm(temperature: float = 0.3):
    from langchain_groq import ChatGroq
    return ChatGroq(model=GROQ_MODEL, api_key=GROQ_API_KEY, temperature=temperature)


# Cache per temperature so we don't instantiate duplicate clients
_llm_cache: dict[float, Any] = {}


def get_llm(temperature: float = 0.3) -> Any:
    if DRY_RUN:
        return _DryRunLLM()
    if temperature not in _llm_cache:
        _llm_cache[temperature] = _build_real_llm(temperature)
    return _llm_cache[temperature]


def get_structured_llm(schema: Type[T], temperature: float = 0.0) -> Any:
    """Returns an LLM bound to a Pydantic schema for guaranteed structured output.

    Defaults to temperature=0.0 for deterministic structured outputs.
    """
    if DRY_RUN:
        return _DryRunStructured(schema)
    return get_llm(temperature).with_structured_output(schema)
