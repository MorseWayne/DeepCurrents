from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from typing import Any
from unittest.mock import patch

import pytest

from src.services.event_ranker import EventRanker


class FakeEventRepository:
    def __init__(self):
        self.events: dict[str, dict[str, Any]] = {}
        self.event_lists: list[dict[str, Any]] = []
        self.upserted_scores: list[dict[str, Any]] = []

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
        return [dict(item) for item in self.event_lists]

    async def upsert_event_score(self, score: Mapping[str, Any]) -> dict[str, Any]:
        payload = dict(score)
        self.upserted_scores.append(payload)
        return payload


class FakeArticleRepository:
    def __init__(self):
        self.articles: dict[str, dict[str, Any]] = {}

    async def get_article(self, article_id: str) -> dict[str, Any] | None:
        row = self.articles.get(article_id)
        return dict(row) if row else None


class FakeEventQueryService:
    def __init__(self):
        self.timelines: dict[str, dict[str, Any]] = {}
        self.list_result: list[dict[str, Any]] = []
        self.list_calls: list[dict[str, Any]] = []

    async def get_event_timeline(self, event_id: str) -> dict[str, Any]:
        return dict(self.timelines[event_id])

    async def list_events(
        self,
        *,
        event_id: str | None = None,
        statuses: Sequence[str] | None = None,
        since: datetime | None = None,
        theme: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        self.list_calls.append(
            {
                "event_id": event_id,
                "statuses": list(statuses or []),
                "since": since,
                "theme": theme,
                "limit": limit,
            }
        )
        return [dict(item) for item in self.list_result]


def make_timeline(
    *,
    event_id: str,
    status: str,
    event_type: str,
    latest_article_at: datetime,
    started_at: datetime,
    article_count: int,
    source_count: int,
    supporting_sources: list[dict[str, Any]],
    contradicting_sources: list[dict[str, Any]],
    market_channels: list[dict[str, Any]],
    assets: list[dict[str, Any]],
    members: list[dict[str, Any]],
    transitions: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "event": {
            "event_id": event_id,
            "status": status,
            "event_type": event_type,
            "canonical_title": f"title-{event_id}",
            "latest_article_at": latest_article_at,
            "started_at": started_at,
            "article_count": article_count,
            "source_count": source_count,
        },
        "members": members,
        "transitions": transitions,
        "enrichment": {
            "event_type": event_type,
            "market_channels": market_channels,
            "assets": assets,
            "supporting_sources": supporting_sources,
            "contradicting_sources": contradicting_sources,
            "source_count": source_count,
            "member_count": article_count,
            "last_transition": transitions[-1] if transitions else {},
        },
        "scores": [],
    }


@pytest.mark.asyncio
async def test_event_ranker_scores_event_and_persists_all_dimensions():
    event_repo = FakeEventRepository()
    article_repo = FakeArticleRepository()
    query_service = FakeEventQueryService()
    ranker = EventRanker(
        event_repo,
        article_repo,
        query_service,
        reference_now=datetime(2026, 3, 13, 12, 0, tzinfo=UTC),
    )

    article_repo.articles = {
        "art_1": {"article_id": "art_1", "tier": 1, "source_type": "wire"},
        "art_2": {"article_id": "art_2", "tier": 2, "source_type": "news"},
    }
    query_service.timelines["evt_1"] = make_timeline(
        event_id="evt_1",
        status="escalating",
        event_type="conflict",
        latest_article_at=datetime(2026, 3, 13, 11, 0, tzinfo=UTC),
        started_at=datetime(2026, 3, 13, 8, 0, tzinfo=UTC),
        article_count=4,
        source_count=2,
        supporting_sources=[{"source_id": "reuters"}, {"source_id": "ap"}],
        contradicting_sources=[],
        market_channels=[{"name": "energy"}, {"name": "shipping"}],
        assets=[{"name": "brent"}],
        members=[
            {"article_id": "art_1"},
            {"article_id": "art_2"},
        ],
        transitions=[
            {
                "from_state": "active",
                "to_state": "escalating",
                "reason": "impact_scope_expanded",
                "created_at": datetime(2026, 3, 13, 10, 30, tzinfo=UTC),
            }
        ],
    )

    score = await ranker.score_event("evt_1")

    assert score["event_id"] == "evt_1"
    assert score["profile"] == "macro_daily"
    assert score["threat_score"] > 0.7
    assert score["market_impact_score"] > 0.6
    assert score["corroboration_score"] > 0.5
    assert score["source_quality_score"] > 0.8
    assert score["uncertainty_score"] == pytest.approx(0.0)
    assert score["total_score"] > 0.5
    explanation = event_repo.upserted_scores[0]["payload"]["explanation"]
    assert explanation["profile"]["name"] == "macro_daily"
    assert explanation["dimension_scores"]["threat_score"] == pytest.approx(
        score["threat_score"]
    )
    assert explanation["weighted_contributions"]["uncertainty_penalty"] == pytest.approx(
        0.0
    )
    assert explanation["event_facts"]["event_type"] == "conflict"
    assert explanation["top_drivers"]
    assert "escalating_event" in explanation["risk_flags"]


@pytest.mark.asyncio
async def test_event_ranker_ranks_high_impact_event_above_low_value_single_source_event():
    event_repo = FakeEventRepository()
    article_repo = FakeArticleRepository()
    query_service = FakeEventQueryService()
    ranker = EventRanker(
        event_repo,
        article_repo,
        query_service,
        reference_now=datetime(2026, 3, 13, 12, 0, tzinfo=UTC),
    )

    article_repo.articles = {
        "art_hi_1": {"article_id": "art_hi_1", "tier": 1, "source_type": "wire"},
        "art_hi_2": {"article_id": "art_hi_2", "tier": 2, "source_type": "wire"},
        "art_lo_1": {"article_id": "art_lo_1", "tier": 4, "source_type": "blog"},
    }
    query_service.list_result = [
        {"event_id": "evt_low"},
        {"event_id": "evt_high"},
    ]
    query_service.timelines["evt_high"] = make_timeline(
        event_id="evt_high",
        status="updated",
        event_type="central_bank",
        latest_article_at=datetime(2026, 3, 13, 11, 30, tzinfo=UTC),
        started_at=datetime(2026, 3, 13, 9, 0, tzinfo=UTC),
        article_count=3,
        source_count=2,
        supporting_sources=[{"source_id": "bloomberg"}, {"source_id": "ft"}],
        contradicting_sources=[],
        market_channels=[{"name": "rates"}, {"name": "fx"}],
        assets=[],
        members=[{"article_id": "art_hi_1"}, {"article_id": "art_hi_2"}],
        transitions=[
            {
                "from_state": "active",
                "to_state": "updated",
                "reason": "material_new_facts",
                "created_at": datetime(2026, 3, 13, 11, 10, tzinfo=UTC),
            }
        ],
    )
    query_service.timelines["evt_low"] = make_timeline(
        event_id="evt_low",
        status="active",
        event_type="general",
        latest_article_at=datetime(2026, 3, 13, 6, 0, tzinfo=UTC),
        started_at=datetime(2026, 3, 13, 1, 0, tzinfo=UTC),
        article_count=6,
        source_count=1,
        supporting_sources=[{"source_id": "blog"}],
        contradicting_sources=[],
        market_channels=[],
        assets=[],
        members=[{"article_id": "art_lo_1"}],
        transitions=[
            {
                "from_state": "new",
                "to_state": "active",
                "reason": "event_confirmed",
                "created_at": datetime(2026, 3, 13, 2, 0, tzinfo=UTC),
            }
        ],
    )

    with patch("src.services.event_ranker.log_stage_metrics") as mock_log_metrics:
        ranked = await ranker.rank_events(statuses=["active", "updated"], limit=5)

    assert [item["event_id"] for item in ranked] == ["evt_high", "evt_low"]
    assert ranked[0]["total_score"] > ranked[1]["total_score"]
    assert query_service.list_calls[0]["limit"] == 5
    mock_log_metrics.assert_called_once()
    logged_metrics = mock_log_metrics.call_args.args[2]
    assert logged_metrics["events_considered"] == 2
    assert logged_metrics["events_ranked"] == 2
    assert logged_metrics["single_source_event_ratio"] == pytest.approx(0.5)


@pytest.mark.asyncio
async def test_event_ranker_applies_profiles_with_reproducible_different_ordering():
    event_repo = FakeEventRepository()
    article_repo = FakeArticleRepository()
    query_service = FakeEventQueryService()
    ranker = EventRanker(
        event_repo,
        article_repo,
        query_service,
        reference_now=datetime(2026, 3, 13, 12, 0, tzinfo=UTC),
    )

    article_repo.articles = {
        "art_macro_1": {"article_id": "art_macro_1", "tier": 1, "source_type": "wire"},
        "art_macro_2": {
            "article_id": "art_macro_2",
            "tier": 1,
            "source_type": "official",
        },
        "art_risk_1": {"article_id": "art_risk_1", "tier": 3, "source_type": "news"},
        "art_risk_2": {"article_id": "art_risk_2", "tier": 3, "source_type": "news"},
    }
    query_service.list_result = [
        {"event_id": "evt_risk"},
        {"event_id": "evt_macro"},
    ]
    query_service.timelines["evt_macro"] = make_timeline(
        event_id="evt_macro",
        status="updated",
        event_type="central_bank",
        latest_article_at=datetime(2026, 3, 13, 11, 15, tzinfo=UTC),
        started_at=datetime(2026, 3, 13, 9, 0, tzinfo=UTC),
        article_count=4,
        source_count=3,
        supporting_sources=[
            {"source_id": "bloomberg"},
            {"source_id": "ft"},
            {"source_id": "wsj"},
        ],
        contradicting_sources=[],
        market_channels=[{"name": "rates"}, {"name": "fx"}, {"name": "credit"}],
        assets=[{"name": "usd"}, {"name": "us10y"}],
        members=[
            {"article_id": "art_macro_1"},
            {"article_id": "art_macro_2"},
        ],
        transitions=[
            {
                "from_state": "active",
                "to_state": "updated",
                "reason": "material_new_facts",
                "created_at": datetime(2026, 3, 13, 11, 10, tzinfo=UTC),
            }
        ],
    )
    query_service.timelines["evt_risk"] = make_timeline(
        event_id="evt_risk",
        status="escalating",
        event_type="conflict",
        latest_article_at=datetime(2026, 3, 13, 11, 50, tzinfo=UTC),
        started_at=datetime(2026, 3, 13, 11, 0, tzinfo=UTC),
        article_count=5,
        source_count=3,
        supporting_sources=[
            {"source_id": "reuters"},
            {"source_id": "ap"},
        ],
        contradicting_sources=[{"source_id": "official_denial"}],
        market_channels=[{"name": "energy"}],
        assets=[],
        members=[
            {"article_id": "art_risk_1"},
            {"article_id": "art_risk_2"},
        ],
        transitions=[
            {
                "from_state": "active",
                "to_state": "updated",
                "reason": "material_new_facts",
                "created_at": datetime(2026, 3, 13, 11, 20, tzinfo=UTC),
            },
            {
                "from_state": "updated",
                "to_state": "escalating",
                "reason": "impact_scope_expanded",
                "created_at": datetime(2026, 3, 13, 11, 45, tzinfo=UTC),
            },
        ],
    )

    ranked_macro = await ranker.rank_events(limit=5, profile="macro_daily")
    ranked_risk_first = await ranker.rank_events(limit=5, profile="risk_daily")
    ranked_risk_second = await ranker.rank_events(limit=5, profile="risk_daily")

    assert [item["event_id"] for item in ranked_macro] == ["evt_macro", "evt_risk"]
    assert [item["event_id"] for item in ranked_risk_first] == [
        "evt_risk",
        "evt_macro",
    ]
    assert [item["event_id"] for item in ranked_risk_first] == [
        item["event_id"] for item in ranked_risk_second
    ]


@pytest.mark.asyncio
async def test_event_ranker_penalizes_uncertain_single_source_conflicting_event():
    event_repo = FakeEventRepository()
    article_repo = FakeArticleRepository()
    query_service = FakeEventQueryService()
    ranker = EventRanker(
        event_repo,
        article_repo,
        query_service,
        reference_now=datetime(2026, 3, 13, 12, 0, tzinfo=UTC),
    )

    article_repo.articles = {
        "art_1": {"article_id": "art_1", "tier": 3, "source_type": "news"},
    }
    query_service.timelines["evt_conflict"] = make_timeline(
        event_id="evt_conflict",
        status="updated",
        event_type="central_bank",
        latest_article_at=datetime(2026, 3, 13, 10, 0, tzinfo=UTC),
        started_at=datetime(2026, 3, 13, 9, 30, tzinfo=UTC),
        article_count=1,
        source_count=1,
        supporting_sources=[{"source_id": "unknown"}],
        contradicting_sources=[{"source_id": "unknown"}],
        market_channels=[{"name": "rates"}],
        assets=[],
        members=[{"article_id": "art_1"}],
        transitions=[
            {
                "from_state": "active",
                "to_state": "updated",
                "reason": "material_new_facts",
                "created_at": datetime(2026, 3, 13, 9, 50, tzinfo=UTC),
            }
        ],
    )

    score = await ranker.score_event("evt_conflict")

    assert score["uncertainty_score"] >= 0.5
    assert score["corroboration_score"] < 0.3
    assert score["total_score"] < 0.45


@pytest.mark.asyncio
async def test_event_ranker_rejects_unknown_profile():
    event_repo = FakeEventRepository()
    article_repo = FakeArticleRepository()
    query_service = FakeEventQueryService()
    ranker = EventRanker(
        event_repo,
        article_repo,
        query_service,
        reference_now=datetime(2026, 3, 13, 12, 0, tzinfo=UTC),
    )

    with pytest.raises(ValueError, match="Unknown scoring profile: missing_profile"):
        await ranker.score_event("evt_unknown", profile="missing_profile")
