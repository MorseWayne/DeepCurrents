import pytest

from src.config.settings import Settings
from src.services.event_intelligence_bootstrap import EventIntelligenceBootstrap


class StubStore:
    def __init__(self, *args, **kwargs):
        self.connected = False
        self.closed = False
        self.connect_calls = 0
        self.health_calls = 0

    async def connect(self):
        self.connect_calls += 1
        self.connected = True

    async def health_check(self):
        self.health_calls += 1
        return {"backend": "stub", "healthy": True}

    async def close(self):
        self.closed = True


class RetryableStore(StubStore):
    failures_before_success = 1

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.remaining_failures = self.failures_before_success

    async def connect(self):
        self.connect_calls += 1
        if self.remaining_failures > 0:
            self.remaining_failures -= 1
            raise ConnectionError("temporary failure")
        self.connected = True


class FatalStore(StubStore):
    async def connect(self):
        self.connect_calls += 1
        raise ImportError("missing dependency")


class HealthFailureStore(StubStore):
    async def health_check(self):
        self.health_calls += 1
        raise ConnectionError("health check failed")


class StubSchemaBootstrap:
    def __init__(self, pool):
        self.pool = pool
        self.initialize_calls = 0

    async def initialize(self):
        self.initialize_calls += 1
        return {"schema_ready": True, "table_count": 12}


class FailingSchemaBootstrap(StubSchemaBootstrap):
    async def initialize(self):
        self.initialize_calls += 1
        raise RuntimeError("ddl failed")


def require_stub_store(store: object) -> StubStore:
    assert isinstance(store, StubStore)
    return store


@pytest.mark.asyncio
async def test_event_intelligence_bootstrap_disabled_by_default():
    settings = Settings(event_intelligence_enabled=False)
    bootstrap = EventIntelligenceBootstrap(settings)

    state = await bootstrap.start()

    assert state.enabled is False
    assert state.started is False


@pytest.mark.asyncio
async def test_event_intelligence_bootstrap_validates_required_settings():
    settings = Settings(
        event_intelligence_enabled=True,
        event_intelligence_postgres_dsn="",
        event_intelligence_qdrant_url="",
        event_intelligence_redis_url="",
    )
    bootstrap = EventIntelligenceBootstrap(settings)

    with pytest.raises(ValueError):
        await bootstrap.start()


@pytest.mark.asyncio
async def test_event_intelligence_bootstrap_prepares_runtime_state():
    settings = Settings(
        event_intelligence_enabled=True,
        event_intelligence_postgres_dsn="postgresql://localhost:5432/deepcurrents",
        event_intelligence_qdrant_url="http://localhost:6333",
        event_intelligence_redis_url="redis://localhost:6379/0",
        event_intelligence_qdrant_api_key="",
    )
    bootstrap = EventIntelligenceBootstrap(
        settings,
        postgres_factory=StubStore,
        vector_store_factory=StubStore,
        cache_factory=StubStore,
        schema_bootstrap_factory=StubSchemaBootstrap,
    )

    state = await bootstrap.start()

    assert state.enabled is True
    assert state.started is True
    assert state.config is not None
    assert set(state.stores) == {"postgres", "vector_store", "cache"}
    assert state.health == {
        "postgres": {
            "backend": "stub",
            "healthy": True,
            "schema_ready": True,
            "table_count": 12,
        },
        "vector_store": {"backend": "stub", "healthy": True},
        "cache": {"backend": "stub", "healthy": True},
    }

    stores = list(state.stores.values())
    await bootstrap.stop()
    assert state.started is False
    assert all(getattr(store, "closed", False) for store in stores)


@pytest.mark.asyncio
async def test_event_intelligence_bootstrap_start_is_idempotent():
    settings = Settings(
        event_intelligence_enabled=True,
        event_intelligence_postgres_dsn="postgresql://localhost:5432/deepcurrents",
        event_intelligence_qdrant_url="http://localhost:6333",
        event_intelligence_redis_url="redis://localhost:6379/0",
    )
    bootstrap = EventIntelligenceBootstrap(
        settings,
        postgres_factory=StubStore,
        vector_store_factory=StubStore,
        cache_factory=StubStore,
        schema_bootstrap_factory=StubSchemaBootstrap,
    )

    first_state = await bootstrap.start()
    second_state = await bootstrap.start()
    postgres_store = require_stub_store(first_state.stores["postgres"])
    vector_store = require_stub_store(first_state.stores["vector_store"])
    cache_store = require_stub_store(first_state.stores["cache"])

    assert first_state is second_state
    assert postgres_store.connect_calls == 1
    assert vector_store.connect_calls == 1
    assert cache_store.connect_calls == 1


@pytest.mark.asyncio
async def test_event_intelligence_bootstrap_retries_retryable_failures():
    settings = Settings(
        event_intelligence_enabled=True,
        event_intelligence_postgres_dsn="postgresql://localhost:5432/deepcurrents",
        event_intelligence_qdrant_url="http://localhost:6333",
        event_intelligence_redis_url="redis://localhost:6379/0",
        event_intelligence_store_max_retries=1,
    )
    bootstrap = EventIntelligenceBootstrap(
        settings,
        postgres_factory=RetryableStore,
        vector_store_factory=StubStore,
        cache_factory=StubStore,
        schema_bootstrap_factory=StubSchemaBootstrap,
    )

    state = await bootstrap.start()
    postgres_store = require_stub_store(state.stores["postgres"])

    assert postgres_store.connect_calls == 2
    assert state.health["postgres"] == {
        "backend": "stub",
        "healthy": True,
        "schema_ready": True,
        "table_count": 12,
    }


@pytest.mark.asyncio
async def test_event_intelligence_bootstrap_fails_fast_on_import_errors():
    settings = Settings(
        event_intelligence_enabled=True,
        event_intelligence_postgres_dsn="postgresql://localhost:5432/deepcurrents",
        event_intelligence_qdrant_url="http://localhost:6333",
        event_intelligence_redis_url="redis://localhost:6379/0",
        event_intelligence_store_max_retries=3,
    )
    bootstrap = EventIntelligenceBootstrap(
        settings,
        postgres_factory=FatalStore,
        vector_store_factory=StubStore,
        cache_factory=StubStore,
        schema_bootstrap_factory=StubSchemaBootstrap,
    )

    with pytest.raises(RuntimeError, match="postgres store startup failed"):
        await bootstrap.start()


@pytest.mark.asyncio
async def test_event_intelligence_bootstrap_cleans_up_partial_start_failures():
    created_stores = {}

    def build_store(name):
        def factory(*args, **kwargs):
            store = HealthFailureStore() if name == "vector_store" else StubStore()
            created_stores[name] = store
            return store

        return factory

    settings = Settings(
        event_intelligence_enabled=True,
        event_intelligence_postgres_dsn="postgresql://localhost:5432/deepcurrents",
        event_intelligence_qdrant_url="http://localhost:6333",
        event_intelligence_redis_url="redis://localhost:6379/0",
    )
    bootstrap = EventIntelligenceBootstrap(
        settings,
        postgres_factory=build_store("postgres"),
        vector_store_factory=build_store("vector_store"),
        cache_factory=build_store("cache"),
        schema_bootstrap_factory=StubSchemaBootstrap,
    )

    with pytest.raises(RuntimeError, match="vector_store store startup failed"):
        await bootstrap.start()

    assert created_stores["postgres"].closed is True
    assert created_stores["vector_store"].closed is True
    assert created_stores["cache"].closed is False
    assert bootstrap.state.started is False
    assert bootstrap.state.stores == {}


@pytest.mark.asyncio
async def test_event_intelligence_bootstrap_cleans_up_on_schema_failure():
    created_stores = {}

    def build_store(name):
        def factory(*args, **kwargs):
            store = StubStore()
            created_stores[name] = store
            return store

        return factory

    settings = Settings(
        event_intelligence_enabled=True,
        event_intelligence_postgres_dsn="postgresql://localhost:5432/deepcurrents",
        event_intelligence_qdrant_url="http://localhost:6333",
        event_intelligence_redis_url="redis://localhost:6379/0",
    )
    bootstrap = EventIntelligenceBootstrap(
        settings,
        postgres_factory=build_store("postgres"),
        vector_store_factory=build_store("vector_store"),
        cache_factory=build_store("cache"),
        schema_bootstrap_factory=FailingSchemaBootstrap,
    )

    with pytest.raises(RuntimeError, match="schema bootstrap failed"):
        await bootstrap.start()

    assert created_stores["postgres"].closed is True
    assert created_stores["vector_store"].closed is True
    assert created_stores["cache"].closed is True
