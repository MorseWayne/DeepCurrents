from __future__ import annotations

import importlib
import json

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

    async def get(self, key: str) -> Any | None:
        """获取缓存值，JSON 自动反序列化。不存在或解析失败返回 None。"""
        if self._client is None:
            return None
        try:
            raw = await self._client.get(key)
            if raw is None:
                return None
            return json.loads(raw)
        except (json.JSONDecodeError, Exception):
            return None

    async def set(
        self,
        key: str,
        value: Any,
        *,
        ttl_seconds: int = 900,
    ) -> bool:
        """设置缓存值，JSON 序列化。ttl_seconds 默认 15 分钟。"""
        if self._client is None:
            return False
        try:
            payload = json.dumps(value, ensure_ascii=False, default=str)
            await self._client.setex(key, ttl_seconds, payload)
            return True
        except (TypeError, Exception):
            return False

    async def delete(self, key: str) -> bool:
        """删除缓存键。"""
        if self._client is None:
            return False
        try:
            await self._client.delete(key)
            return True
        except Exception:
            return False

    async def close(self) -> None:
        if self._client is None:
            return
        if self._owns_client:
            if hasattr(self._client, "aclose"):
                await self._client.aclose()
            elif hasattr(self._client, "close"):
                await self._client.close()
        self._client = None
