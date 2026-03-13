import pytest

from src.services.cache_service import CacheService
from src.services.postgres_store import PostgresStore
from src.services.vector_store import VectorStore


class FakePool:
    def __init__(self):
        self.closed = False

    async def fetchval(self, query):
        assert query == "SELECT 1"
        return 1

    async def close(self):
        self.closed = True


class FakeCodecConnection:
    def __init__(self):
        self.codec_calls = []

    async def set_type_codec(
        self,
        typename,
        *,
        schema="public",
        encoder,
        decoder,
        format="text",
    ):
        self.codec_calls.append(
            {
                "typename": typename,
                "schema": schema,
                "encoder": encoder,
                "decoder": decoder,
                "format": format,
            }
        )


class FakeAsyncpgModule:
    def __init__(self):
        self.pool = FakePool()
        self.codec_connection = FakeCodecConnection()
        self.create_pool_calls = []

    async def create_pool(self, **kwargs):
        self.create_pool_calls.append(kwargs)
        await kwargs["init"](self.codec_connection)
        return self.pool


class FakeRedisClient:
    def __init__(self):
        self.closed = False

    async def ping(self):
        return True

    async def aclose(self):
        self.closed = True


class FakeQdrantCollections:
    def __init__(self, size):
        self.collections = [object() for _ in range(size)]


class FakeVectorParams:
    def __init__(self, *, size, distance):
        self.size = size
        self.distance = distance


class FakePointStruct:
    def __init__(self, *, id, vector, payload):
        self.id = id
        self.vector = vector
        self.payload = payload


class FakeDistance:
    COSINE = "cosine"
    DOT = "dot"
    EUCLID = "euclid"
    MANHATTAN = "manhattan"


class FakeModels:
    VectorParams = FakeVectorParams
    PointStruct = FakePointStruct
    Distance = FakeDistance


class FakeQdrantClient:
    def __init__(self):
        self.closed = False
        self.collection_exists_calls = []
        self.create_collection_calls = []
        self.create_collection_error = None
        self.upsert_calls = []
        self.query_points_calls = []
        self.existing_collections = set()

    async def get_collections(self):
        return FakeQdrantCollections(2)

    async def collection_exists(self, *, collection_name):
        self.collection_exists_calls.append(collection_name)
        return collection_name in self.existing_collections

    async def create_collection(self, *, collection_name, vectors_config):
        self.create_collection_calls.append((collection_name, vectors_config))
        if self.create_collection_error is not None:
            self.existing_collections.add(collection_name)
            error = self.create_collection_error
            self.create_collection_error = None
            raise error
        self.existing_collections.add(collection_name)

    async def upsert(self, *, collection_name, wait, points):
        self.upsert_calls.append((collection_name, wait, points))
        return {"status": "acknowledged"}

    async def query_points(
        self,
        *,
        collection_name,
        query,
        limit,
        with_payload,
        with_vectors,
        score_threshold,
    ):
        self.query_points_calls.append(
            {
                "collection_name": collection_name,
                "query": query,
                "limit": limit,
                "with_payload": with_payload,
                "with_vectors": with_vectors,
                "score_threshold": score_threshold,
            }
        )
        return type(
            "FakeQueryResult",
            (),
            {
                "points": [
                    type(
                        "FakePoint",
                        (),
                        {
                            "id": "art_2",
                            "score": 0.91,
                            "payload": {"article_id": "art_2"},
                        },
                    )()
                ]
            },
        )()

    async def close(self):
        self.closed = True


@pytest.mark.asyncio
async def test_postgres_store_keeps_injected_pool_open():
    pool = FakePool()
    store = PostgresStore("postgresql://localhost/test", pool=pool)

    await store.connect()
    health = await store.health_check()
    await store.close()

    assert health == {"backend": "postgresql", "healthy": True, "result": 1}
    assert pool.closed is False


@pytest.mark.asyncio
async def test_postgres_store_registers_json_codecs_on_created_pool(monkeypatch):
    fake_asyncpg = FakeAsyncpgModule()
    monkeypatch.setattr(
        "src.services.postgres_store.importlib.import_module",
        lambda name: fake_asyncpg,
    )

    store = PostgresStore("postgresql://localhost/test")
    await store.connect()

    assert len(fake_asyncpg.create_pool_calls) == 1
    create_pool_call = fake_asyncpg.create_pool_calls[0]
    assert create_pool_call["dsn"] == "postgresql://localhost/test"
    assert create_pool_call["command_timeout"] == 5
    assert callable(create_pool_call["init"])
    assert fake_asyncpg.codec_connection.codec_calls == [
        {
            "typename": "json",
            "schema": "pg_catalog",
            "encoder": fake_asyncpg.codec_connection.codec_calls[0]["encoder"],
            "decoder": fake_asyncpg.codec_connection.codec_calls[0]["decoder"],
            "format": "text",
        },
        {
            "typename": "jsonb",
            "schema": "pg_catalog",
            "encoder": fake_asyncpg.codec_connection.codec_calls[1]["encoder"],
            "decoder": fake_asyncpg.codec_connection.codec_calls[1]["decoder"],
            "format": "text",
        },
    ]


@pytest.mark.asyncio
async def test_cache_service_keeps_injected_client_open():
    client = FakeRedisClient()
    store = CacheService("redis://localhost/0", client=client)

    await store.connect()
    health = await store.health_check()
    await store.close()

    assert health == {"backend": "redis", "healthy": True}
    assert client.closed is False


@pytest.mark.asyncio
async def test_vector_store_keeps_injected_client_open():
    client = FakeQdrantClient()
    store = VectorStore("http://localhost:6333", client=client)
    store._models = FakeModels

    await store.connect()
    health = await store.health_check()
    await store.close()

    assert health == {"backend": "qdrant", "healthy": True, "collections": 2}
    assert client.closed is False


@pytest.mark.asyncio
async def test_vector_store_creates_collection_and_upserts_point():
    client = FakeQdrantClient()
    store = VectorStore("http://localhost:6333", client=client)
    store._models = FakeModels

    await store.connect()
    await store.ensure_collection("article_features", vector_size=3)
    result = await store.upsert_point(
        "article_features",
        point_id="art_1",
        vector=[0.1, 0.2, 0.3],
        payload={"article_id": "art_1"},
    )

    assert client.collection_exists_calls == ["article_features"]
    assert len(client.create_collection_calls) == 1
    collection_name, vectors_config = client.create_collection_calls[0]
    assert collection_name == "article_features"
    assert vectors_config.size == 3
    assert vectors_config.distance == FakeDistance.COSINE
    assert result == {"status": "acknowledged"}
    upsert_collection, wait, points = client.upsert_calls[0]
    assert upsert_collection == "article_features"
    assert wait is True
    assert points[0].id == "art_1"
    assert points[0].vector == [0.1, 0.2, 0.3]
    assert points[0].payload == {"article_id": "art_1"}


@pytest.mark.asyncio
async def test_vector_store_ignores_collection_exists_race():
    client = FakeQdrantClient()
    client.create_collection_error = RuntimeError(
        "Wrong input: Collection `article_features` already exists!"
    )
    store = VectorStore("http://localhost:6333", client=client)
    store._models = FakeModels

    await store.connect()
    await store.ensure_collection("article_features", vector_size=3)

    assert client.collection_exists_calls == ["article_features"]
    assert len(client.create_collection_calls) == 1
    assert "article_features" in client.existing_collections


@pytest.mark.asyncio
async def test_vector_store_queries_similar_points():
    client = FakeQdrantClient()
    store = VectorStore("http://localhost:6333", client=client)
    store._models = FakeModels

    await store.connect()
    result = await store.query_similar_points(
        "article_features",
        query_vector=[0.2, 0.3, 0.4],
        limit=3,
        score_threshold=0.8,
        with_payload=True,
    )

    assert client.query_points_calls == [
        {
            "collection_name": "article_features",
            "query": [0.2, 0.3, 0.4],
            "limit": 3,
            "with_payload": True,
            "with_vectors": False,
            "score_threshold": 0.8,
        }
    ]
    assert result == [
        {"id": "art_2", "score": 0.91, "payload": {"article_id": "art_2"}}
    ]
