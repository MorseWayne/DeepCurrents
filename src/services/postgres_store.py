from __future__ import annotations

import importlib

from typing import Any, Dict

from ..utils.logger import get_logger

logger = get_logger("postgres-store")


class PostgresStore:
    def __init__(
        self,
        dsn: str,
        *,
        timeout_ms: int = 5000,
        pool: Any | None = None,
    ):
        self.dsn = dsn
        self.timeout_ms = timeout_ms
        self._pool = pool
        self._owns_pool = pool is None

    @property
    def pool(self) -> Any | None:
        return self._pool

    async def connect(self) -> None:
        if self._pool is not None:
            return

        try:
            asyncpg = importlib.import_module("asyncpg")
        except ImportError as exc:
            raise ImportError(
                "PostgresStore requires `asyncpg`. Install it via requirements.txt."
            ) from exc

        self._pool = await asyncpg.create_pool(
            dsn=self.dsn,
            command_timeout=max(self.timeout_ms / 1000, 1),
        )
        logger.info("PostgreSQL store 已连接。")

    async def health_check(self) -> Dict[str, Any]:
        if self._pool is None:
            raise RuntimeError("PostgreSQL store not connected")

        value = await self._pool.fetchval("SELECT 1")
        return {
            "backend": "postgresql",
            "healthy": value == 1,
            "result": value,
        }

    async def close(self) -> None:
        if self._pool is None:
            return
        if self._owns_pool and hasattr(self._pool, "close"):
            await self._pool.close()
        self._pool = None
