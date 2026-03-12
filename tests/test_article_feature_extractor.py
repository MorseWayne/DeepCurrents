from datetime import UTC, datetime

import pytest

from src.services.article_feature_extractor import ArticleFeatureExtractor
from src.services.article_models import ArticleRecord


class FakeEmbeddingClient:
    def __init__(self, vector):
        self.vector = vector
        self.calls = []

    async def embed(self, text: str) -> list[float]:
        self.calls.append(text)
        return list(self.vector)


class FakeVectorStore:
    def __init__(self):
        self.ensure_calls = []
        self.upsert_calls = []

    async def ensure_collection(self, collection_name: str, *, vector_size: int, distance: str = "cosine"):
        self.ensure_calls.append((collection_name, vector_size, distance))

    async def upsert_point(self, collection_name: str, *, point_id, vector, payload=None, wait: bool = True):
        self.upsert_calls.append((collection_name, point_id, list(vector), dict(payload or {}), wait))
        return {"status": "acknowledged"}


class FakeArticleRepository:
    def __init__(self):
        self.upsert_calls = []

    async def upsert_article_features(self, features):
        payload = dict(features)
        self.upsert_calls.append(payload)
        return payload


@pytest.mark.asyncio
async def test_article_feature_extractor_extracts_keywords_entities_and_vector_payload():
    repo = FakeArticleRepository()
    vector_store = FakeVectorStore()
    embedding_client = FakeEmbeddingClient([0.1, 0.2, 0.3])
    extractor = ArticleFeatureExtractor(
        repo,
        vector_store,
        embedding_model="bge-m3",
        embedding_client=embedding_client,
    )
    article = ArticleRecord(
        article_id="art_1",
        source_id="reuters",
        canonical_url="https://example.com/oil",
        title="Oil prices jump as OPEC signals tighter supply",
        normalized_title="oil prices jump as opec signals tighter supply",
        content="Oil prices climbed after OPEC officials signaled tighter supply and stronger China demand.",
        clean_content="Oil prices climbed after OPEC officials signaled tighter supply and stronger China demand.",
        language="en",
        simhash="abcd1234",
        quality_score=0.82,
        metadata={"symbols": ["WTI", "BRENT"], "countries": ["China"]},
    )

    extracted = await extractor.extract(article)

    assert extracted["article_id"] == "art_1"
    assert extracted["embedding_model"] == "bge-m3"
    assert extracted["embedding_vector_id"] == "art_1"
    assert extracted["language"] == "en"
    assert extracted["simhash"] == "abcd1234"
    assert extracted["quality_score"] == 0.82
    assert extracted["embedding"] == [0.1, 0.2, 0.3]
    assert "opec" in extracted["keywords"]
    assert "oil" in extracted["keywords"]
    assert {"name": "WTI", "type": "ticker"} in extracted["entities"]
    assert {"name": "China", "type": "location"} in extracted["entities"]
    assert extracted["vector_payload"]["article_id"] == "art_1"
    assert embedding_client.calls and "source:reuters" in embedding_client.calls[0]


@pytest.mark.asyncio
async def test_article_feature_extractor_recomputes_quality_and_persists_outputs():
    repo = FakeArticleRepository()
    vector_store = FakeVectorStore()
    extractor = ArticleFeatureExtractor(
        repo,
        vector_store,
        embedding_model="bge-m3",
        embedding_client=FakeEmbeddingClient([0.5, 0.6]),
    )
    article = ArticleRecord(
        article_id="art_zh",
        source_id="xinhua",
        canonical_url="https://example.com/cn",
        title="中国经济增长动能回升",
        normalized_title="中国经济增长动能回升",
        content="中国经济增长动能回升，制造业和消费数据继续改善。",
        clean_content="中国经济增长动能回升，制造业和消费数据继续改善。",
        language="zh",
        published_at=datetime(2026, 3, 13, tzinfo=UTC),
        simhash="sim-zh",
        quality_score=0.0,
        metadata={"topics": ["宏观", "制造业"]},
    )

    stored = await extractor.extract_and_persist(article)

    assert stored["article_id"] == "art_zh"
    assert stored["embedding_vector_id"] == "art_zh"
    assert stored["quality_score"] > 0
    assert vector_store.ensure_calls == [("article_features", 2, "cosine")]
    collection_name, point_id, vector, payload, wait = vector_store.upsert_calls[0]
    assert collection_name == "article_features"
    assert point_id == "art_zh"
    assert vector == [0.5, 0.6]
    assert payload["language"] == "zh"
    assert any(
        keyword in {"中国", "经济", "增长", "动能", "制造业", "消费", "数据", "改善", "中国经济"}
        for keyword in repo.upsert_calls[0]["keywords"]
    )
    assert {"name": "宏观", "type": "topic"} in repo.upsert_calls[0]["entities"]
    assert wait is True
