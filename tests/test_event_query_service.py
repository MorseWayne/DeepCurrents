from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from typing import Any

import pytest

from src.services.event_query_service import EventQueryService


class FakeEventRepository:
    def __init__(self):
        self.events: dict[str, dict[str, Any]] = {}
        self.members_by_event: dict[str, list[dict[str, Any]]] = {}
        self.transitions_by_event: dict[str, list[dict[str, Any]]] = {}
        self.scores_by_event: dict[str, list[dict[str, Any]]] = {}

    async def get_event(self, event_id: str) -> dict[str, Any] | None:
        event = self.events.get(event_id)
        return dict(event) if event else None

    async def list_recent_events(
        self,
        *,
        statuses: Sequence[str] | None = None,
        since: datetime | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        _ = statuses, since, limit
        return [dict(event) for event in self.events.values()]

    async def list_event_members(self, event_id: str) -> list[dict[str, Any]]:
        return [dict(item) for item in self.members_by_event.get(event_id, [])]

    async def list_event_state_transitions(self, event_id: str) -> list[dict[str, Any]]:
        return [dict(item) for item in self.transitions_by_event.get(event_id, [])]

    async def list_event_scores(self, event_id: str) -> list[dict[str, Any]]:
        return [dict(item) for item in self.scores_by_event.get(event_id, [])]


class FakeArticleRepository:
    def __init__(self):
        self.articles: dict[str, dict[str, Any]] = {}
        self.features: dict[str, dict[str, Any]] = {}
        self.dedup_links: dict[str, list[dict[str, Any]]] = {}

    async def get_article(self, article_id: str) -> dict[str, Any] | None:
        article = self.articles.get(article_id)
        return dict(article) if article else None

    async def get_articles_batch(
        self, article_ids: Sequence[str]
    ) -> dict[str, dict[str, Any]]:
        return {
            aid: dict(a)
            for aid in article_ids
            if (a := self.articles.get(aid)) is not None
        }

    async def get_article_features(self, article_id: str) -> dict[str, Any] | None:
        features = self.features.get(article_id)
        return dict(features) if features else None

    async def list_dedup_links(self, article_id: str) -> list[dict[str, Any]]:
        return [dict(item) for item in self.dedup_links.get(article_id, [])]

    async def list_dedup_links_batch(
        self, article_ids: Sequence[str]
    ) -> dict[str, list[dict[str, Any]]]:
        return {
            aid: [dict(item) for item in self.dedup_links.get(aid, [])]
            for aid in article_ids
        }


class FakeEventEnrichmentService:
    def __init__(self, payloads: Mapping[str, Mapping[str, Any]]):
        self.payloads = {key: dict(value) for key, value in payloads.items()}
        self.calls: list[dict[str, Any]] = []

    async def get_event_enrichment(
        self,
        event_id: str,
        *,
        event: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        self.calls.append({"event_id": event_id, "event": dict(event or {})})
        return dict(self.payloads[event_id])


@pytest.mark.asyncio
async def test_event_query_service_lists_events_with_status_time_theme_and_event_filters():
    event_repo = FakeEventRepository()
    article_repo = FakeArticleRepository()
    enrichment = FakeEventEnrichmentService(
        {
            "evt_energy": {
                "regions": [{"name": "red sea"}],
                "assets": [{"name": "brent"}],
                "market_channels": [{"name": "energy"}, {"name": "shipping"}],
                "supporting_sources": [{"source_id": "reuters"}],
                "contradicting_sources": [],
                "last_transition": {"to_state": "escalating", "reason": "impact_scope_expanded"},
            },
            "evt_cb": {
                "regions": [{"name": "turkey"}],
                "assets": [],
                "market_channels": [{"name": "rates"}, {"name": "fx"}],
                "supporting_sources": [{"source_id": "bloomberg"}, {"source_id": "ft"}],
                "contradicting_sources": [],
                "last_transition": {"to_state": "updated", "reason": "material_new_facts"},
            },
        }
    )
    service = EventQueryService(event_repo, article_repo, enrichment)
    event_repo.events = {
        "evt_energy": {
            "event_id": "evt_energy",
            "status": "active",
            "canonical_title": "Red Sea shipping disruption lifts oil",
            "primary_region": "red sea",
            "event_type": "conflict",
            "latest_article_at": datetime(2026, 3, 13, 9, 0, tzinfo=UTC),
            "article_count": 3,
            "source_count": 2,
        },
        "evt_cb": {
            "event_id": "evt_cb",
            "status": "active",
            "canonical_title": "Turkey unexpectedly cuts benchmark rate",
            "primary_region": "turkey",
            "event_type": "central_bank",
            "latest_article_at": datetime(2026, 3, 13, 8, 0, tzinfo=UTC),
            "article_count": 2,
            "source_count": 2,
        },
        "evt_old": {
            "event_id": "evt_old",
            "status": "resolved",
            "canonical_title": "Old resolved event",
            "primary_region": "europe",
            "event_type": "policy",
            "latest_article_at": datetime(2026, 3, 10, 8, 0, tzinfo=UTC),
            "article_count": 4,
            "source_count": 3,
        },
    }

    items = await service.list_events(
        statuses=["active"],
        since=datetime(2026, 3, 13, 7, 30, tzinfo=UTC),
        theme="energy",
    )

    assert len(items) == 1
    assert items[0]["event_id"] == "evt_energy"
    assert items[0]["enrichment_summary"]["market_channels"] == ["energy", "shipping"]
    assert items[0]["last_transition"]["to_state"] == "escalating"

    direct = await service.list_events(event_id="evt_cb", theme="central_banks")
    assert [item["event_id"] for item in direct] == ["evt_cb"]


@pytest.mark.asyncio
async def test_event_query_service_builds_event_timeline():
    event_repo = FakeEventRepository()
    article_repo = FakeArticleRepository()
    enrichment = FakeEventEnrichmentService(
        {
            "evt_1": {
                "regions": [{"name": "red sea"}],
                "assets": [{"name": "brent"}],
                "market_channels": [{"name": "shipping"}],
                "supporting_sources": [{"source_id": "reuters"}],
                "contradicting_sources": [],
                "last_transition": {"to_state": "active", "reason": "event_confirmed"},
            }
        }
    )
    service = EventQueryService(event_repo, article_repo, enrichment)

    event_repo.events["evt_1"] = {
        "event_id": "evt_1",
        "status": "active",
        "canonical_title": "Missile strike disrupts Red Sea shipping",
    }
    event_repo.members_by_event["evt_1"] = [
        {
            "event_id": "evt_1",
            "article_id": "art_1",
            "role": "primary",
            "is_primary": True,
        }
    ]
    event_repo.transitions_by_event["evt_1"] = [
        {"transition_id": "tr_1", "event_id": "evt_1", "to_state": "active"}
    ]
    event_repo.scores_by_event["evt_1"] = [
        {"event_id": "evt_1", "profile": "macro_daily", "total_score": 7.2}
    ]
    article_repo.articles["art_1"] = {
        "article_id": "art_1",
        "source_id": "reuters",
        "title": "Missile strike disrupts Red Sea shipping",
        "published_at": datetime(2026, 3, 13, 9, 0, tzinfo=UTC),
    }
    article_repo.dedup_links["art_1"] = [
        {"link_id": "dup_1", "relation_type": "semantic"}
    ]

    timeline = await service.get_event_timeline("evt_1")

    assert timeline["event"]["event_id"] == "evt_1"
    assert timeline["members"][0]["article_id"] == "art_1"
    assert timeline["members"][0]["dedup_relations_count"] == 1
    assert timeline["transitions"][0]["transition_id"] == "tr_1"
    assert timeline["enrichment"]["regions"][0]["name"] == "red sea"
    assert timeline["scores"][0]["profile"] == "macro_daily"


@pytest.mark.asyncio
async def test_event_query_service_builds_debug_view_with_dedup_links_and_notes():
    event_repo = FakeEventRepository()
    article_repo = FakeArticleRepository()
    enrichment = FakeEventEnrichmentService(
        {
            "evt_2": {
                "regions": [{"name": "turkey"}],
                "assets": [],
                "market_channels": [{"name": "rates"}],
                "supporting_sources": [{"source_id": "bloomberg"}],
                "contradicting_sources": [{"source_id": "wsj"}],
                "last_transition": {
                    "from_state": "active",
                    "to_state": "updated",
                    "reason": "material_new_facts",
                },
            }
        }
    )
    service = EventQueryService(event_repo, article_repo, enrichment)

    event_repo.events["evt_2"] = {
        "event_id": "evt_2",
        "status": "updated",
        "canonical_title": "Turkey unexpectedly cuts benchmark rate",
        "source_count": 2,
    }
    event_repo.members_by_event["evt_2"] = [
        {"event_id": "evt_2", "article_id": "art_cut", "role": "primary", "is_primary": True},
        {"event_id": "evt_2", "article_id": "art_raise", "role": "supporting", "is_primary": False},
    ]
    event_repo.transitions_by_event["evt_2"] = [
        {"transition_id": "tr_2", "event_id": "evt_2", "to_state": "updated"}
    ]
    article_repo.articles = {
        "art_cut": {"article_id": "art_cut", "source_id": "bloomberg", "title": "Turkey unexpectedly cuts benchmark rate"},
        "art_raise": {"article_id": "art_raise", "source_id": "wsj", "title": "Turkey unexpectedly hikes benchmark rate"},
    }
    article_repo.features = {
        "art_cut": {"entities": [{"name": "Turkey", "type": "location"}]},
        "art_raise": {"entities": [{"name": "Turkey", "type": "location"}]},
    }
    article_repo.dedup_links = {
        "art_cut": [{"link_id": "dup_sem_1", "relation_type": "semantic"}],
        "art_raise": [
            {"link_id": "dup_sem_1", "relation_type": "semantic"},
            {"link_id": "dup_exact_1", "relation_type": "exact"},
        ],
    }

    debug_view = await service.get_event_debug_view("evt_2")

    assert {link["link_id"] for link in debug_view["dedup_links"]} == {
        "dup_sem_1",
        "dup_exact_1",
    }
    assert len(debug_view["member_articles"]) == 2
    assert any("conflicting sources present" in note for note in debug_view["debug_notes"])
    assert any("latest transition:" in note for note in debug_view["debug_notes"])
    assert any("dedup links present: exact, semantic" == note for note in debug_view["debug_notes"])
