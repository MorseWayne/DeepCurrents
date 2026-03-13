from __future__ import annotations

import importlib
import json

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
            init=self._configure_connection_codecs,
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

    async def _configure_connection_codecs(self, connection: Any) -> None:
        for typename in ("json", "jsonb"):
            await connection.set_type_codec(
                typename,
                schema="pg_catalog",
                encoder=_encode_json_codec_value,
                decoder=_decode_json_codec_value,
            )


def _encode_json_codec_value(value: Any) -> str:
    if isinstance(value, bytes):
        text = value.decode("utf-8", errors="ignore").strip()
    elif isinstance(value, str):
        text = value.strip()
    else:
        return json.dumps(value, ensure_ascii=False, default=str)

    if not text:
        return json.dumps(value, ensure_ascii=False, default=str)

    try:
        json.loads(text)
    except json.JSONDecodeError:
        return json.dumps(value, ensure_ascii=False, default=str)
    return text


def _decode_json_codec_value(value: str) -> Any:
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return value
