import pytest

from src.services.schema_bootstrap import SchemaBootstrap


class FakeTransaction:
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False


class FakeConnection:
    def __init__(self):
        self.executed = []
        self.transaction_calls = 0

    def transaction(self):
        self.transaction_calls += 1
        return FakeTransaction()

    async def execute(self, sql):
        self.executed.append(sql)


class FakeAcquire:
    def __init__(self, connection):
        self.connection = connection

    async def __aenter__(self):
        return self.connection

    async def __aexit__(self, exc_type, exc, tb):
        return False


class FakePool:
    def __init__(self):
        self.connection = FakeConnection()
        self.acquire_calls = 0

    def acquire(self):
        self.acquire_calls += 1
        return FakeAcquire(self.connection)


@pytest.mark.asyncio
async def test_schema_bootstrap_executes_full_ddl_script():
    pool = FakePool()
    bootstrap = SchemaBootstrap(pool)

    health = await bootstrap.initialize()

    assert pool.acquire_calls == 1
    assert pool.connection.transaction_calls == 1
    assert len(pool.connection.executed) == 1

    sql = pool.connection.executed[0]
    for table_name in SchemaBootstrap.TABLE_NAMES:
        assert f"CREATE TABLE IF NOT EXISTS {table_name}" in sql

    assert "CREATE INDEX IF NOT EXISTS idx_articles_published_at" in sql
    assert "REFERENCES events(event_id) ON DELETE CASCADE" in sql
    assert health == {
        "backend": "postgresql",
        "healthy": True,
        "schema_ready": True,
        "table_count": 12,
    }


@pytest.mark.asyncio
async def test_schema_bootstrap_is_safe_to_run_multiple_times():
    pool = FakePool()
    bootstrap = SchemaBootstrap(pool)

    await bootstrap.initialize()
    await bootstrap.initialize()

    assert pool.acquire_calls == 2
    assert len(pool.connection.executed) == 2


@pytest.mark.asyncio
async def test_schema_bootstrap_requires_connected_pool():
    bootstrap = SchemaBootstrap(None)

    with pytest.raises(RuntimeError, match="connected PostgreSQL pool"):
        await bootstrap.initialize()
