from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from typing import Any

import pytest

from src.services.article_models import ArticleRecord
from src.services.event_builder import EventBuilder


class FakeEventRepository:
    def __init__(self):
        self.events: list[dict[str, Any]] = []
        self.members_by_event: dict[str, list[dict[str, Any]]] = {}
        self.created_events: list[dict[str, Any]] = []
        self.updated_events: list[dict[str, Any]] = []
        self.added_members: list[dict[str, Any]] = []
        self.upserted_scores: list[dict[str, Any]] = []
        self.transitions: list[dict[str, Any]] = []

    async def list_recent_events(
        self,
        *,
        statuses: Sequence[str] | None = None,
        since: datetime | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        _ = statuses, since, limit
        return list(self.events)

    async def create_event(self, event: Mapping[str, Any]) -> dict[str, Any]:
        payload = dict(event)
        self.created_events.append(payload)
        self.events.append(payload)
        self.members_by_event.setdefault(payload["event_id"], [])
        return payload

    async def update_event(
        self,
        event_id: str,
        fields: Mapping[str, Any],
    ) -> dict[str, Any]:
        payload = dict(fields)
        payload["event_id"] = event_id
        self.updated_events.append(payload)
        for event in self.events:
            if event.get("event_id") == event_id:
                event.update(fields)
                return dict(event)
        return payload

    async def add_event_member(self, member: Mapping[str, Any]) -> dict[str, Any]:
        payload = dict(member)
        self.added_members.append(payload)
        self.members_by_event.setdefault(payload["event_id"], []).append(payload)
        return payload

    async def list_event_members(self, event_id: str) -> list[dict[str, Any]]:
        return [dict(member) for member in self.members_by_event.get(event_id, [])]

    async def upsert_event_score(self, score: dict[str, Any]) -> dict[str, Any]:
        payload = dict(score)
        self.upserted_scores.append(payload)
        return payload

    async def record_state_transition(
        self, transition: Mapping[str, Any]
    ) -> dict[str, Any]:
        payload = dict(transition)
        self.transitions.append(payload)
        return payload


class FakeArticleRepository:
    def __init__(self):
        self.rows: dict[str, dict[str, Any]] = {}
        self.features: dict[str, dict[str, Any]] = {}

    async def get_article(self, article_id: str) -> dict[str, Any] | None:
        row = self.rows.get(article_id)
        return dict(row) if row else None

    async def get_article_features(self, article_id: str) -> dict[str, Any] | None:
        row = self.features.get(article_id)
        return dict(row) if row else None


class FakeVectorStore:
    def __init__(self, *, results: Sequence[Mapping[str, Any]] | None = None):
        self.results = [dict(item) for item in (results or [])]
        self.calls: list[dict[str, Any]] = []

    async def query_similar_points(
        self,
        collection_name: str,
        *,
        query_vector: Sequence[float],
        limit: int = 10,
        score_threshold: float | None = None,
        with_payload: bool | Sequence[str] = True,
    ) -> list[dict[str, Any]]:
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
        "published_at": datetime(2026, 3, 13, 8, 0, tzinfo=UTC),
        "ingested_at": datetime(2026, 3, 13, 8, 5, tzinfo=UTC),
        "language": "en",
        "tier": 1,
        "source_type": "wire",
    }
    base.update(overrides)
    return ArticleRecord(**base)


@pytest.mark.asyncio
async def test_event_builder_creates_new_event_when_no_candidates_match():
    event_repo = FakeEventRepository()
    article_repo = FakeArticleRepository()
    builder = EventBuilder(event_repo, article_repo, title_similarity_threshold=0.85)

    result = await builder.assign_article_to_event(make_article())

    assert result["created"] is True
    assert result["event"]["event_id"].startswith("evt_")
    assert (
        result["event"]["canonical_title"] == "oil prices surge after refinery outage"
    )
    assert result["event"]["started_at"] == datetime(2026, 3, 13, 8, 0, tzinfo=UTC)
    assert result["event"]["latest_article_at"] == datetime(
        2026, 3, 13, 8, 0, tzinfo=UTC
    )
    assert result["event"]["article_count"] == 1
    assert result["member"]["role"] == "primary"
    assert result["member"]["is_primary"] is True
    assert result["transition"]["to_state"] == "new"
    assert result["transition"]["reason"] == "event_created"
    assert event_repo.created_events
    assert len(event_repo.transitions) == 1


@pytest.mark.asyncio
async def test_event_builder_attaches_article_to_best_recent_event_without_transition():
    event_repo = FakeEventRepository()
    article_repo = FakeArticleRepository()

    event_repo.events = [
        {
            "event_id": "evt_match",
            "status": "active",
            "canonical_title": "oil prices surge after refinery outage",
            "started_at": datetime(2026, 3, 13, 7, 30, tzinfo=UTC),
            "latest_article_at": datetime(2026, 3, 13, 7, 45, tzinfo=UTC),
            "article_count": 2,
        },
        {
            "event_id": "evt_other",
            "status": "active",
            "canonical_title": "copper inventory rises",
            "started_at": datetime(2026, 3, 13, 7, 0, tzinfo=UTC),
            "latest_article_at": datetime(2026, 3, 13, 7, 20, tzinfo=UTC),
            "article_count": 4,
        },
    ]
    event_repo.members_by_event = {
        "evt_match": [
            {
                "event_id": "evt_match",
                "article_id": "art_old_1",
                "is_primary": True,
                "role": "primary",
            },
            {
                "event_id": "evt_match",
                "article_id": "art_old_2",
                "is_primary": False,
                "role": "supporting",
            },
        ]
    }
    article_repo.rows = {
        "art_old_1": {"article_id": "art_old_1", "source_id": "ap"},
        "art_old_2": {"article_id": "art_old_2", "source_id": "reuters"},
    }

    builder = EventBuilder(event_repo, article_repo, title_similarity_threshold=0.85)
    result = await builder.assign_article_to_event(make_article())

    assert result["created"] is False
    assert result["event"]["event_id"] == "evt_match"
    assert result["member"]["event_id"] == "evt_match"
    assert result["member"]["article_id"] == "art_new"
    assert result["member"]["role"] == "supporting"
    assert result["member"]["is_primary"] is False

    assert event_repo.updated_events[0]["article_count"] == 3
    assert event_repo.updated_events[0]["source_count"] == 2
    assert event_repo.updated_events[0]["status"] == "active"
    assert result["transition"] is None
    assert event_repo.updated_events[0]["started_at"] == datetime(
        2026, 3, 13, 7, 30, tzinfo=UTC
    )
    assert event_repo.updated_events[0]["latest_article_at"] == datetime(
        2026, 3, 13, 8, 0, tzinfo=UTC
    )


@pytest.mark.asyncio
async def test_event_builder_uses_semantic_and_entity_signals_to_merge_and_activate():
    event_repo = FakeEventRepository()
    article_repo = FakeArticleRepository()
    vector_store = FakeVectorStore(
        results=[
            {
                "id": "art_old_1",
                "score": 0.94,
                "payload": {"article_id": "art_old_1"},
            }
        ]
    )

    event_repo.events = [
        {
            "event_id": "evt_red_sea",
            "status": "new",
            "canonical_title": "attack near bab al-mandab raises shipping risks",
            "started_at": datetime(2026, 3, 13, 1, 0, tzinfo=UTC),
            "latest_article_at": datetime(2026, 3, 13, 1, 35, tzinfo=UTC),
            "article_count": 1,
        }
    ]
    event_repo.members_by_event = {
        "evt_red_sea": [
            {
                "event_id": "evt_red_sea",
                "article_id": "art_old_1",
                "is_primary": True,
                "role": "primary",
            }
        ]
    }
    article_repo.rows = {
        "art_old_1": {
            "article_id": "art_old_1",
            "source_id": "al-jazeera",
            "title": "Attack near Bab al-Mandab raises shipping risks",
            "clean_content": "Attack near Bab al-Mandab raises shipping risks in the Red Sea.",
        }
    }
    article_repo.features = {
        "art_old_1": {
            "entities": [
                {"name": "Red Sea", "type": "location"},
                {"name": "Bab al-Mandab", "type": "location"},
            ]
        }
    }

    builder = EventBuilder(
        event_repo,
        article_repo,
        vector_store,
        title_similarity_threshold=0.85,
    )
    article = make_article(
        title="Missile strike disrupts Red Sea shipping",
        normalized_title="missile strike disrupts red sea shipping",
        content="Missile strike disrupts Red Sea shipping near Bab al-Mandab.",
        clean_content="Missile strike disrupts Red Sea shipping near Bab al-Mandab.",
    )
    result = await builder.assign_article_to_event(
        article,
        extracted_features={
            "embedding": [0.1, 0.2, 0.3],
            "entities": [
                {"name": "Red Sea", "type": "location"},
                {"name": "Bab al-Mandab", "type": "location"},
            ],
        },
    )

    assert result["created"] is False
    assert result["event"]["event_id"] == "evt_red_sea"
    assert result["event"]["status"] == "active"
    assert result["transition"]["from_state"] == "new"
    assert result["transition"]["to_state"] == "active"
    assert result["transition"]["reason"] == "event_confirmed"
    assert result["merge_signals"]["semantic_support"] == pytest.approx(0.94)
    assert result["merge_signals"]["entity_overlap"] == pytest.approx(1.0)
    assert vector_store.calls[0]["collection_name"] == "article_features"


@pytest.mark.asyncio
async def test_event_builder_rejects_conflicting_policy_direction_even_with_strong_similarity():
    event_repo = FakeEventRepository()
    article_repo = FakeArticleRepository()
    vector_store = FakeVectorStore(
        results=[
            {
                "id": "art_old_1",
                "score": 0.97,
                "payload": {"article_id": "art_old_1"},
            }
        ]
    )
    event_repo.events = [
        {
            "event_id": "evt_rates",
            "status": "active",
            "canonical_title": "turkey unexpectedly hikes benchmark rate",
            "started_at": datetime(2026, 3, 13, 5, 30, tzinfo=UTC),
            "latest_article_at": datetime(2026, 3, 13, 6, 5, tzinfo=UTC),
            "article_count": 3,
        }
    ]
    event_repo.members_by_event = {
        "evt_rates": [
            {
                "event_id": "evt_rates",
                "article_id": "art_old_1",
                "is_primary": True,
                "role": "primary",
            }
        ]
    }
    article_repo.rows = {
        "art_old_1": {
            "article_id": "art_old_1",
            "source_id": "bloomberg",
            "title": "Turkey unexpectedly hikes benchmark rate",
            "clean_content": "Turkey unexpectedly hikes benchmark rate after inflation concerns.",
        }
    }
    article_repo.features = {
        "art_old_1": {
            "entities": [
                {"name": "Turkey", "type": "location"},
                {"name": "Central Bank", "type": "org"},
            ]
        }
    }

    builder = EventBuilder(event_repo, article_repo, vector_store)
    article = make_article(
        title="Turkey unexpectedly cuts benchmark rate",
        normalized_title="turkey unexpectedly cuts benchmark rate",
        content="Turkey unexpectedly cuts benchmark rate after market pressure.",
        clean_content="Turkey unexpectedly cuts benchmark rate after market pressure.",
        source_id="financial-times",
    )
    result = await builder.assign_article_to_event(
        article,
        extracted_features={
            "embedding": [0.4, 0.5, 0.6],
            "entities": [
                {"name": "Turkey", "type": "location"},
                {"name": "Central Bank", "type": "org"},
            ],
        },
    )

    assert result["created"] is True
    assert result["event"]["event_id"] != "evt_rates"
    assert event_repo.updated_events == []
    assert event_repo.transitions[-1]["to_state"] == "new"


@pytest.mark.asyncio
async def test_event_builder_extract_and_persist_upserts_score_when_quality_present():
    event_repo = FakeEventRepository()
    article_repo = FakeArticleRepository()
    builder = EventBuilder(event_repo, article_repo, title_similarity_threshold=0.85)

    result = await builder.extract_and_persist(
        make_article(),
        extracted_features={
            "quality_score": 0.73,
            "keywords": ["oil"],
            "entities": [{"name": "OPEC", "type": "org"}],
        },
    )

    assert result["created"] is True
    assert result["score"]["event_id"] == result["event"]["event_id"]
    assert result["score"]["profile"] == "ingestion_v1"
    assert result["score"]["source_quality_score"] == pytest.approx(0.73)
    assert event_repo.upserted_scores[0]["payload"]["keywords"] == ["oil"]


@pytest.mark.asyncio
async def test_event_builder_extract_and_persist_skips_score_without_quality_signal():
    event_repo = FakeEventRepository()
    article_repo = FakeArticleRepository()
    builder = EventBuilder(event_repo, article_repo, title_similarity_threshold=0.85)

    result = await builder.extract_and_persist(
        make_article(),
        extracted_features={"keywords": ["oil"]},
    )

    assert result["created"] is True
    assert result["score"] is None
    assert event_repo.upserted_scores == []
