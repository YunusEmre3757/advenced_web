"""
SeismicCrew — main entry point.

Usage
-----
    # default: last 24 hours, min magnitude 2.0
    crewai run

    # custom window
    python -m seismic_crew.main --hours 48 --min-magnitude 3.0

Environment variables required
-------------------------------
    OPENAI_API_KEY   – OpenAI API key used by CrewAI agents
    GROQ_API_KEY     – (optional) Groq key if you override the LLM to Groq

The Seismic Command backend must be running at http://localhost:8080.
Start it with:
    cd ../backend && ./mvnw spring-boot:run
"""

import argparse
import os
import sys
import warnings
from datetime import datetime

# Fix Windows console encoding for Unicode/emoji output
if sys.platform == "win32":
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
            sys.stderr.reconfigure(encoding="utf-8")
        except Exception:
            pass

# Suppress pysbd SyntaxWarning on Python 3.12+
warnings.filterwarnings("ignore", category=SyntaxWarning, module="pysbd")

from seismic_crew.crew import SeismicCrew


# ---------------------------------------------------------------------------
# Fallback dataset used when the backend is unreachable during development
# ---------------------------------------------------------------------------
FALLBACK_EARTHQUAKES = [
    {
        "id": "FALLBACK-001",
        "location": "MARMARA DENIZI (Fallback)",
        "magnitude": 4.2,
        "depthKm": 10.5,
        "latitude": 40.85,
        "longitude": 28.60,
        "time": "2024-01-15T08:32:00Z",
    },
    {
        "id": "FALLBACK-002",
        "location": "ERZINCAN (Fallback)",
        "magnitude": 3.8,
        "depthKm": 7.0,
        "latitude": 39.75,
        "longitude": 39.50,
        "time": "2024-01-15T06:14:00Z",
    },
    {
        "id": "FALLBACK-003",
        "location": "KAHRAMANMARAS (Fallback)",
        "magnitude": 3.5,
        "depthKm": 8.0,
        "latitude": 37.57,
        "longitude": 36.94,
        "time": "2024-01-15T04:55:00Z",
    },
]


def run(hours: int = 24, min_magnitude: float = 2.0) -> None:
    """Kick off the SeismicCrew pipeline.

    Parameters
    ----------
    hours : int
        How many hours of earthquake history to analyse (1–168).
    min_magnitude : float
        Minimum magnitude filter for the query window (0.0–10.0).
    """
    report_date = datetime.now().strftime("%Y-%m-%d %H:%M UTC")

    inputs = {
        "hours": hours,
        "min_magnitude": min_magnitude,
        "report_date": report_date,
        "backend_url": "http://localhost:8080",
        # Fallback data used by the data_collector if the backend is down
        "fallback_earthquakes": FALLBACK_EARTHQUAKES,
    }

    print("\n" + "=" * 60)
    print("  Seismic Command — CrewAI Pipeline")
    print(f"  Date     : {report_date}")
    print(f"  Window   : last {hours} hours")
    print(f"  Min mag  : M{min_magnitude}")
    print("=" * 60 + "\n")

    result = SeismicCrew().crew().kickoff(inputs=inputs)

    print("\n" + "=" * 60)
    print("  Pipeline complete — report.md has been saved.")
    print("=" * 60 + "\n")
    print(result)


def train(n_iterations: int = 3, filename: str = "training.pkl") -> None:
    """Train the crew for n_iterations (CrewAI built-in training)."""
    inputs = {
        "hours": 24,
        "min_magnitude": 2.0,
        "report_date": datetime.now().strftime("%Y-%m-%d %H:%M UTC"),
        "backend_url": "http://localhost:8080",
        "fallback_earthquakes": FALLBACK_EARTHQUAKES,
    }
    try:
        SeismicCrew().crew().train(
            n_iterations=n_iterations,
            filename=filename,
            inputs=inputs,
        )
    except Exception as e:
        raise RuntimeError(f"Training failed: {e}") from e


def replay(task_id: str) -> None:
    """Replay a specific task from its saved state."""
    try:
        SeismicCrew().crew().replay(task_id=task_id)
    except Exception as e:
        raise RuntimeError(f"Replay failed: {e}") from e


def test(n_iterations: int = 1, openai_model: str = "gpt-4o-mini") -> None:
    """Run the crew in test mode."""
    inputs = {
        "hours": 24,
        "min_magnitude": 2.0,
        "report_date": datetime.now().strftime("%Y-%m-%d %H:%M UTC"),
        "backend_url": "http://localhost:8080",
        "fallback_earthquakes": FALLBACK_EARTHQUAKES,
    }
    try:
        SeismicCrew().crew().test(
            n_iterations=n_iterations,
            openai_model_name=openai_model,
            inputs=inputs,
        )
    except Exception as e:
        raise RuntimeError(f"Test failed: {e}") from e


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Run the Seismic Command CrewAI pipeline."
    )
    parser.add_argument(
        "--hours",
        type=int,
        default=24,
        help="Hours of earthquake history to analyse (default: 24)",
    )
    parser.add_argument(
        "--min-magnitude",
        type=float,
        default=2.0,
        dest="min_magnitude",
        help="Minimum magnitude filter (default: 2.0)",
    )
    args = parser.parse_args()
    run(hours=args.hours, min_magnitude=args.min_magnitude)
