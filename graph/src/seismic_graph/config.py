"""Runtime config — loaded from env or .env."""

import os
from pathlib import Path


def _load_dotenv() -> None:
    env_path = Path(__file__).resolve().parents[2] / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


_load_dotenv()

GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
GROQ_MODEL = os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile")
SPRING_BASE_URL = os.environ.get("SPRING_BASE_URL", "http://localhost:8080")
GRAPH_PORT = int(os.environ.get("GRAPH_PORT", "8002"))
GRAPH_DATABASE_URL = os.environ.get(
    "GRAPH_DATABASE_URL",
    "postgresql://seismic:seismic_dev_only@localhost:5432/seismic",
)
GRAPH_CHECKPOINT_MODE = os.environ.get("GRAPH_CHECKPOINT_MODE", "postgres").lower()

# LangSmith tracing — set LANGCHAIN_TRACING_V2=true in .env to enable
LANGSMITH_TRACING = os.environ.get("LANGCHAIN_TRACING_V2", "false").lower() == "true"
LANGSMITH_PROJECT = os.environ.get("LANGCHAIN_PROJECT", "seismic-command")

DRY_RUN = not GROQ_API_KEY
