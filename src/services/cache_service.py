from __future__ import annotations

import importlib

from typing import Any, Dict

from ..utils.logger import get_logger

logger = get_logger("cache-service")


class CacheService:
    def __init__(
        self,
        url: str,
        *,
        timeout_ms: int = 5000,
        client: Any | None = None,
    ):
        self.url = url
        self.timeout_ms = timeout_ms
        self._client = client
        self._owns_client = client is None

    async def connect(self) -> None:
        if self._client is not None:
            return

        try:
            redis = importlib.import_module("redis.asyncio")
        except ImportError as exc:
            raise ImportError(
                "CacheService requires `redis`. Install it via requirements.txt."
            ) from exc

        timeout_seconds = max(self.timeout_ms / 1000, 1)
        self._client = redis.from_url(
            self.url,
            decode_responses=True,
            socket_connect_timeout=timeout_seconds,
            socket_timeout=timeout_seconds,
        )
        logger.info("Redis cache service 已连接。")

    async def health_check(self) -> Dict[str, Any]:
        if self._client is None:
            raise RuntimeError("Cache service not connected")

        result = await self._client.ping()
        return {
            "backend": "redis",
            "healthy": bool(result),
        }

    async def close(self) -> None:
        if self._client is None:
            return
        if self._owns_client:
            if hasattr(self._client, "aclose"):
                await self._client.aclose()
            elif hasattr(self._client, "close"):
                await self._client.close()
        self._client = None
