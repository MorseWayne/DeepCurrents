from __future__ import annotations

from datetime import UTC, datetime

import pytest

from src.services.article_models import ArticleRecord
from src.services.semantic_deduper import SemanticDeduper


class FakeRepository:
    def __init__(self):
        self.exact_candidates = []
        self.recent_candidates = []
        self.features = {}
        self.created_links = []

    async def find_articles_by_exact_hash(self, exact_hash: str, *, limit: int = 20):
        return list(self.exact_candidates)

    async def list_recent_articles(self, *, since=None, limit: int = 100):
        return list(self.recent_candidates)

    async def get_article_features(self, article_id: str):
        return self.features.get(article_id)

    async def create_dedup_link(self, link):
        self.created_links.append(dict(link))
        return dict(link)


class FakeVectorStore:
    def __init__(self, results=None):
        self.results = results or []
        self.calls = []

    async def query_similar_points(
        self,
        collection_name: str,
        *,
        query_vector,
        limit: int = 10,
        score_threshold: float | None = None,
        with_payload=True,
    ):
        self.calls.append(
            {
                "collection_name": collection_name,
                "query_vector": list(query_vector),
                "limit": limit,
                "score_threshold": score_threshold,
                "with_payload": with_payload,
            }
        )
        return list(self.results)


def make_article(**overrides) -> ArticleRecord:
    base = {
        "article_id": "art_new",
        "source_id": "reuters",
        "canonical_url": "https://example.com/new",
        "title": "Oil prices surge after refinery outage",
        "normalized_title": "oil prices surge after refinery outage",
        "content": "Oil prices surge after refinery outage in Europe.",
        "clean_content": "Oil prices surge after refinery outage in Europe.",
        "published_at": datetime(2026, 3, 13, 0, 0, tzinfo=UTC),
        "language": "en",
        "tier": 1,
        "source_type": "wire",
        "exact_hash": "aaaaaaaaaaaaaaaa",
        "simhash": "ffffffffffffffff",
    }
    base.update(overrides)
    return ArticleRecord(**base)


@pytest.mark.asyncio
async def test_semantic_deduper_links_exact_and_near_duplicates():
    repository = FakeRepository()
    repository.exact_candidates = [
        {"article_id": "art_exact", "exact_hash": "aaaaaaaaaaaaaaaa"}
    ]
    repository.recent_candidates = [
        {
            "article_id": "art_exact",
            "title": "Oil prices surge after refinery outage",
            "normalized_title": "oil prices surge after refinery outage",
            "simhash": "ffffffffffffffff",
        },
        {
            "article_id": "art_near",
            "title": "Oil jumps after refinery outage in Europe",
            "normalized_title": "oil jumps after refinery outage in europe",
            "simhash": "fffffffffffffff0",
        },
    ]
    deduper = SemanticDeduper(repository, vector_store=None)

    links = await deduper.link_cheap_duplicates(make_article())

    assert [link["relation_type"] for link in links] == ["exact", "near"]
    assert repository.created_links[0]["left_article_id"] == "art_exact"
    assert repository.created_links[0]["right_article_id"] == "art_new"
    assert repository.created_links[1]["relation_type"] == "near"
    assert repository.created_links[1]["reason"]["simhash_similarity"] >= 0.9


@pytest.mark.asyncio
async def test_semantic_deduper_links_semantic_candidates_with_entity_overlap():
    repository = FakeRepository()
    repository.recent_candidates = [
        {
            "article_id": "art_peer",
            "title": "Brent rises after Europe refinery disruption",
            "normalized_title": "brent rises after europe refinery disruption",
            "published_at": datetime(2026, 3, 13, 1, 0, tzinfo=UTC),
        }
    ]
    repository.features = {
        "art_new": {"entities": [{"name": "Europe", "type": "location"}]},
        "art_peer": {"entities": [{"name": "Europe", "type": "location"}]},
    }
    vector_store = FakeVectorStore(
        results=[
            {"id": "art_peer", "score": 0.88, "payload": {"article_id": "art_peer"}}
        ]
    )
    deduper = SemanticDeduper(repository, vector_store)

    links = await deduper.link_semantic_duplicates(
        make_article(),
        embedding=[0.1, 0.2, 0.3],
    )

    assert len(links) == 1
    assert links[0]["relation_type"] == "semantic"
    assert links[0]["reason"]["entity_overlap"] == 1.0
    assert vector_store.calls[0]["collection_name"] == "article_features"


@pytest.mark.asyncio
async def test_semantic_deduper_skips_semantic_candidates_without_signal():
    repository = FakeRepository()
    repository.recent_candidates = [
        {
            "article_id": "art_far",
            "title": "Copper steady in Asia",
            "normalized_title": "copper steady in asia",
            "published_at": datetime(2026, 3, 13, 1, 0, tzinfo=UTC),
        }
    ]
    repository.features = {
        "art_new": {"entities": [{"name": "Europe", "type": "location"}]},
        "art_far": {"entities": [{"name": "Asia", "type": "location"}]},
    }
    vector_store = FakeVectorStore(
        results=[{"id": "art_far", "score": 0.84, "payload": {"article_id": "art_far"}}]
    )
    deduper = SemanticDeduper(repository, vector_store)

    links = await deduper.link_semantic_duplicates(
        make_article(),
        embedding=[0.1, 0.2, 0.3],
    )

    assert links == []
    assert repository.created_links == []
