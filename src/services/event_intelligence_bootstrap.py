from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Optional

from ..config.settings import Settings
from .cache_service import CacheService
from .postgres_store import PostgresStore
from .schema_bootstrap import SchemaBootstrap
from .vector_store import VectorStore
from ..utils.logger import get_logger

logger = get_logger("event-intelligence-bootstrap")


@dataclass(frozen=True)
class EventIntelligenceRuntimeConfig:
    postgres_dsn: str
    qdrant_url: str
    qdrant_api_key: str
    redis_url: str
    embedding_model: str
    reranker_model: str
    report_profile: str


@dataclass
class EventIntelligenceRuntimeState:
    enabled: bool
    started: bool = False
    config: Optional[EventIntelligenceRuntimeConfig] = None
    stores: dict[str, Any] = field(default_factory=dict)
    health: dict[str, dict[str, Any]] = field(default_factory=dict)


class EventIntelligenceBootstrap:
    def __init__(
        self,
        settings: Settings,
        *,
        postgres_factory: Callable[..., Any] | None = None,
        vector_store_factory: Callable[..., Any] | None = None,
        cache_factory: Callable[..., Any] | None = None,
        schema_bootstrap_factory: Callable[..., Any] | None = None,
    ):
        self.settings = settings
        self._postgres_factory = postgres_factory or PostgresStore
        self._vector_store_factory = vector_store_factory or VectorStore
        self._cache_factory = cache_factory or CacheService
        self._schema_bootstrap_factory = schema_bootstrap_factory or SchemaBootstrap
        self.state = EventIntelligenceRuntimeState(
            enabled=settings.event_intelligence_enabled
        )

    async def start(self) -> EventIntelligenceRuntimeState:
        if self.state.started:
            return self.state

        if not self.settings.event_intelligence_enabled:
            self.state = EventIntelligenceRuntimeState(enabled=False)
            logger.info(
                "Event Intelligence runtime 未启用，采集与报告入口将保持 fail-closed。"
            )
            return self.state

        self.settings.validate_event_intelligence_settings()
        config = EventIntelligenceRuntimeConfig(
            postgres_dsn=self.settings.event_intelligence_postgres_dsn,
            qdrant_url=self.settings.event_intelligence_qdrant_url,
            qdrant_api_key=self.settings.event_intelligence_qdrant_api_key,
            redis_url=self.settings.event_intelligence_redis_url,
            embedding_model=self.settings.event_intelligence_embedding_model,
            reranker_model=self.settings.event_intelligence_reranker_model,
            report_profile=self.settings.event_intelligence_report_profile,
        )
        stores = {
            "postgres": self._postgres_factory(
                config.postgres_dsn,
                timeout_ms=self.settings.event_intelligence_store_timeout_ms,
            ),
            "vector_store": self._vector_store_factory(
                config.qdrant_url,
                api_key=config.qdrant_api_key,
                timeout_ms=self.settings.event_intelligence_store_timeout_ms,
            ),
            "cache": self._cache_factory(
                config.redis_url,
                timeout_ms=self.settings.event_intelligence_store_timeout_ms,
            ),
        }

        health = {}
        connected_stores = {}
        try:
            for name, store in stores.items():
                health[name] = await self._connect_store(name, store)
                connected_stores[name] = store

            postgres_pool = getattr(stores["postgres"], "pool", None)
            schema_bootstrap = self._schema_bootstrap_factory(postgres_pool)
            schema_health = await self._initialize_schema(schema_bootstrap)
            health["postgres"] = {**health["postgres"], **schema_health}
        except Exception:
            await self._close_stores(connected_stores)
            raise

        self.state = EventIntelligenceRuntimeState(
            enabled=True,
            started=True,
            config=config,
            health=health,
        )
        self.state.stores.update(stores)
        logger.info(
            "Event Intelligence runtime bootstrap 已完成基础存储接入与健康检查。"
        )
        return self.state

    async def stop(self) -> None:
        if self.state.started:
            await self._close_stores(self.state.stores)
            logger.info("Event Intelligence runtime bootstrap 已停止。")
        self.state.started = False
        self.state.stores.clear()
        self.state.health.clear()

    async def _connect_store(self, name: str, store: Any) -> Dict[str, Any]:
        retries = max(self.settings.event_intelligence_store_max_retries, 0)
        last_error: Exception | None = None
        for attempt in range(retries + 1):
            try:
                await asyncio.wait_for(
                    store.connect(),
                    timeout=self._store_timeout_seconds(),
                )
                health = await asyncio.wait_for(
                    store.health_check(),
                    timeout=self._store_timeout_seconds(),
                )
                return health
            except Exception as exc:
                last_error = exc
                if hasattr(store, "close"):
                    await store.close()
                if attempt == retries or not self._should_retry(exc):
                    raise RuntimeError(f"{name} store startup failed: {exc}") from exc
                logger.warning(
                    f"{name} store 启动失败，准备重试 ({attempt + 1}/{retries}): {exc}"
                )
                await asyncio.sleep(0.1 * (2**attempt))

        raise RuntimeError(f"{name} store startup failed: {last_error}")

    def _store_timeout_seconds(self) -> float:
        return max(self.settings.event_intelligence_store_timeout_ms / 1000, 1)

    def _should_retry(self, exc: Exception) -> bool:
        return isinstance(exc, (asyncio.TimeoutError, ConnectionError, OSError))

    async def _initialize_schema(self, schema_bootstrap: Any) -> Dict[str, Any]:
        try:
            return await asyncio.wait_for(
                schema_bootstrap.initialize(),
                timeout=self._store_timeout_seconds(),
            )
        except Exception as exc:
            raise RuntimeError(f"schema bootstrap failed: {exc}") from exc

    async def _close_stores(self, stores: Dict[str, Any]) -> None:
        for store in stores.values():
            if hasattr(store, "close"):
                await store.close()
