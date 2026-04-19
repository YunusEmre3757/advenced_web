"""Thin client for Spring backend endpoints."""

import logging
from typing import Any

import httpx

from .config import SPRING_BASE_URL

logger = logging.getLogger(__name__)


class SpringClient:
    def __init__(self, base_url: str = SPRING_BASE_URL, timeout: float = 10.0):
        self.base_url = base_url.rstrip("/")
        self._client = httpx.AsyncClient(timeout=timeout)

    async def close(self) -> None:
        await self._client.aclose()

    async def recent_earthquakes(self, hours: int = 24, min_magnitude: float = 1.0, limit: int = 100) -> list[dict]:
        url = f"{self.base_url}/api/earthquakes/recent"
        try:
            r = await self._client.get(url, params={"hours": hours, "minMagnitude": min_magnitude, "limit": limit})
            r.raise_for_status()
            return r.json()
        except httpx.TimeoutException:
            logger.warning("Spring timeout: %s", url)
            return []
        except Exception as exc:
            logger.error("Spring error [%s]: %s", url, exc)
            return []

    async def historical_events(self, years: int = 50, min_magnitude: float = 4.5) -> list[dict]:
        url = f"{self.base_url}/api/historical/events"
        try:
            r = await self._client.get(url, params={"years": years, "minMagnitude": min_magnitude})
            r.raise_for_status()
            return r.json()
        except httpx.TimeoutException:
            logger.warning("Spring timeout: %s", url)
            return []
        except Exception as exc:
            logger.error("Spring error [%s]: %s", url, exc)
            return []

    async def fault_lines(self, bbox: tuple[float, float, float, float], simplify: float = 0.01) -> dict[str, Any] | None:
        url = f"{self.base_url}/api/fault-lines"
        try:
            bbox_value = ",".join(str(v) for v in bbox)
            r = await self._client.get(url, params={"bbox": bbox_value, "simplify": simplify})
            r.raise_for_status()
            return r.json()
        except httpx.TimeoutException:
            logger.warning("Spring timeout: %s", url)
            return None
        except Exception as exc:
            logger.error("Spring error [%s]: %s", url, exc)
            return None

    async def earthquake_detail(self, event_id: str) -> dict | None:
        url = f"{self.base_url}/api/earthquakes/{event_id}"
        try:
            r = await self._client.get(url)
            r.raise_for_status()
            return r.json()
        except httpx.TimeoutException:
            logger.warning("Spring timeout: %s", url)
            return None
        except Exception as exc:
            logger.error("Spring error [%s]: %s", url, exc)
            return None

    async def aftershocks(self, event_id: str, limit: int = 12) -> list[dict]:
        url = f"{self.base_url}/api/earthquakes/{event_id}/aftershocks"
        try:
            r = await self._client.get(url, params={"limit": limit})
            r.raise_for_status()
            return r.json()
        except httpx.TimeoutException:
            logger.warning("Spring timeout: %s", url)
            return []
        except Exception as exc:
            logger.error("Spring error [%s]: %s", url, exc)
            return []

    async def similar_historical(self, event_id: str, limit: int = 8) -> list[dict]:
        url = f"{self.base_url}/api/earthquakes/{event_id}/similar"
        try:
            r = await self._client.get(url, params={"limit": limit})
            r.raise_for_status()
            return r.json()
        except httpx.TimeoutException:
            logger.warning("Spring timeout: %s", url)
            return []
        except Exception as exc:
            logger.error("Spring error [%s]: %s", url, exc)
            return []

    async def dyfi(self, event_id: str) -> dict | None:
        url = f"{self.base_url}/api/earthquakes/{event_id}/dyfi"
        try:
            r = await self._client.get(url)
            if r.status_code == 204 or not r.content:
                return None
            r.raise_for_status()
            return r.json()
        except httpx.TimeoutException:
            logger.warning("Spring timeout: %s", url)
            return None
        except Exception as exc:
            logger.error("Spring error [%s]: %s", url, exc)
            return None

    async def shakemap(self, event_id: str) -> dict | None:
        url = f"{self.base_url}/api/earthquakes/{event_id}/shakemap"
        try:
            r = await self._client.get(url)
            if r.status_code == 204 or not r.content:
                return None
            r.raise_for_status()
            return r.json()
        except httpx.TimeoutException:
            logger.warning("Spring timeout: %s", url)
            return None
        except Exception as exc:
            logger.error("Spring error [%s]: %s", url, exc)
            return None


_client: SpringClient | None = None


def get_spring_client() -> SpringClient:
    global _client
    if _client is None:
        _client = SpringClient()
    return _client
