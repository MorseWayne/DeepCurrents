from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Sequence
from unittest.mock import patch

import pytest

from src.services.evidence_selector import EvidenceSelector


class FakeArticleRepository:
    def __init__(self):
        self.articles: dict[str, dict[str, Any]] = {}
        self.features: dict[str, dict[str, Any]] = {}

    async def get_article(self, article_id: str) -> dict[str, Any] | None:
        article = self.articles.get(article_id)
        return dict(article) if article else None

    async def get_article_features(self, article_id: str) -> dict[str, Any] | None:
        features = self.features.get(article_id)
        return dict(features) if features else None


class FakeEventQueryService:
    def __init__(self):
        self.timelines: dict[str, dict[str, Any]] = {}

    async def get_event_timeline(self, event_id: str) -> dict[str, Any]:
        timeline = self.timelines.get(event_id)
        if timeline is None:
            raise ValueError(f"missing timeline: {event_id}")
        return {
            "event": dict(timeline.get("event", {})),
            "members": [dict(item) for item in timeline.get("members", [])],
            "transitions": [dict(item) for item in timeline.get("transitions", [])],
            "enrichment": dict(timeline.get("enrichment", {})),
            "scores": [dict(item) for item in timeline.get("scores", [])],
        }


class FakeEventRanker:
    def __init__(self):
        self.scored_events: dict[str, dict[str, Any]] = {}
        self.ranked_result: list[dict[str, Any]] = []
        self.score_calls: list[dict[str, Any]] = []
        self.rank_calls: list[dict[str, Any]] = []

    async def score_event(
        self,
        event_id: str,
        *,
        profile: str = "macro_daily",
    ) -> dict[str, Any]:
        self.score_calls.append({"event_id": event_id, "profile": profile})
        score = self.scored_events.get(event_id)
        if score is None:
            raise ValueError(f"missing score: {event_id}")
        return dict(score)

    async def rank_events(
        self,
        *,
        statuses: Sequence[str] | None = None,
        since: datetime | None = None,
        theme: str | None = None,
        limit: int = 100,
        profile: str = "macro_daily",
    ) -> list[dict[str, Any]]:
        self.rank_calls.append(
            {
                "statuses": list(statuses or []),
                "since": since,
                "theme": theme,
                "limit": limit,
                "profile": profile,
            }
        )
        return [
            {
                "event_id": item["event_id"],
                "total_score": item["total_score"],
                "score": dict(item["score"]),
                "event": dict(item.get("event", {})),
            }
            for item in self.ranked_result[:limit]
        ]


def make_score(event_id: str, *, profile: str, total_score: float) -> dict[str, Any]:
    return {
        "event_id": event_id,
        "profile": profile,
        "threat_score": 0.7,
        "market_impact_score": 0.8,
        "novelty_score": 0.6,
        "corroboration_score": 0.75,
        "source_quality_score": 0.85,
        "velocity_score": 0.65,
        "uncertainty_score": 0.2,
        "total_score": total_score,
        "payload": {
            "explanation": {
                "risk_flags": ["escalating_event"],
                "top_drivers": [
                    {"dimension": "market_impact_score", "contribution": 0.19}
                ],
            }
        },
    }


def make_timeline(
    *,
    event_id: str,
    event_type: str,
    status: str,
    latest_article_at: datetime,
    members: list[dict[str, Any]],
    supporting_sources: list[dict[str, Any]],
    contradicting_sources: list[dict[str, Any]] | None = None,
    transitions: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "event": {
            "event_id": event_id,
            "event_type": event_type,
            "status": status,
            "canonical_title": f"title-{event_id}",
            "latest_article_at": latest_article_at,
        },
        "members": members,
        "transitions": transitions or [],
        "enrichment": {
            "event_type": event_type,
            "supporting_sources": supporting_sources,
            "contradicting_sources": contradicting_sources or [],
            "last_transition": transitions[-1] if transitions else {},
        },
        "scores": [],
    }


@pytest.mark.asyncio
async def test_evidence_selector_prefers_diverse_high_signal_supporting_articles():
    article_repo = FakeArticleRepository()
    query_service = FakeEventQueryService()
    ranker = FakeEventRanker()
    selector = EvidenceSelector(article_repo, query_service, ranker)

    ranker.scored_events["evt_cb"] = make_score(
        "evt_cb",
        profile="macro_daily",
        total_score=0.86,
    )
    query_service.timelines["evt_cb"] = make_timeline(
        event_id="evt_cb",
        event_type="central_bank",
        status="updated",
        latest_article_at=datetime(2026, 3, 13, 11, 50, tzinfo=UTC),
        members=[
            {
                "article_id": "art_primary",
                "source_id": "reuters",
                "title": "Fed cuts rates by 50 bps amid slowdown fears",
                "published_at": datetime(2026, 3, 13, 11, 50, tzinfo=UTC),
                "role": "primary",
                "is_primary": True,
                "dedup_relations_count": 0,
            },
            {
                "article_id": "art_policy",
                "source_id": "treasury",
                "title": "Treasury approves $200 billion support package",
                "published_at": datetime(2026, 3, 13, 11, 30, tzinfo=UTC),
                "role": "supporting",
                "is_primary": False,
                "dedup_relations_count": 0,
            },
            {
                "article_id": "art_dup",
                "source_id": "reuters",
                "title": "Fed cuts rates by 50 bps as growth slows",
                "published_at": datetime(2026, 3, 13, 11, 40, tzinfo=UTC),
                "role": "supporting",
                "is_primary": False,
                "dedup_relations_count": 3,
            },
            {
                "article_id": "art_blog",
                "source_id": "macro_blog",
                "title": "Why the rate cut matters",
                "published_at": datetime(2026, 3, 13, 10, 0, tzinfo=UTC),
                "role": "supporting",
                "is_primary": False,
                "dedup_relations_count": 0,
            },
        ],
        supporting_sources=[
            {"source_id": "reuters"},
            {"source_id": "treasury"},
            {"source_id": "macro_blog"},
        ],
    )
    article_repo.articles = {
        "art_primary": {
            "article_id": "art_primary",
            "source_id": "reuters",
            "canonical_url": "https://example.com/fed-primary",
            "title": "Fed cuts rates by 50 bps amid slowdown fears",
            "clean_content": "The Federal Reserve cut its benchmark rate by 50 bps after growth slowed.",
            "published_at": datetime(2026, 3, 13, 11, 50, tzinfo=UTC),
            "tier": 1,
            "source_type": "wire",
        },
        "art_policy": {
            "article_id": "art_policy",
            "source_id": "treasury",
            "canonical_url": "https://example.com/treasury-package",
            "title": "Treasury approves $200 billion support package",
            "clean_content": "The treasury approved a 200 billion liquidity package to support markets.",
            "published_at": datetime(2026, 3, 13, 11, 30, tzinfo=UTC),
            "tier": 1,
            "source_type": "official",
        },
        "art_dup": {
            "article_id": "art_dup",
            "source_id": "reuters",
            "canonical_url": "https://example.com/fed-dup",
            "title": "Fed cuts rates by 50 bps as growth slows",
            "clean_content": "The Federal Reserve cut rates by 50 bps in line with primary coverage.",
            "published_at": datetime(2026, 3, 13, 11, 40, tzinfo=UTC),
            "tier": 1,
            "source_type": "wire",
        },
        "art_blog": {
            "article_id": "art_blog",
            "source_id": "macro_blog",
            "canonical_url": "https://example.com/blog-opinion",
            "title": "Why the rate cut matters",
            "clean_content": "An opinionated take with limited new information.",
            "published_at": datetime(2026, 3, 13, 10, 0, tzinfo=UTC),
            "tier": 4,
            "source_type": "blog",
        },
    }
    article_repo.features = {
        "art_primary": {
            "keywords": ["fed", "rates", "50 bps", "slowdown"],
            "entities": [{"name": "Federal Reserve", "type": "organization"}],
        },
        "art_policy": {
            "keywords": ["treasury", "package", "liquidity", "markets"],
            "entities": [{"name": "Treasury", "type": "organization"}],
        },
        "art_dup": {
            "keywords": ["fed", "rates", "50 bps", "slowdown"],
            "entities": [{"name": "Federal Reserve", "type": "organization"}],
        },
        "art_blog": {
            "keywords": ["analysis", "cut", "markets"],
            "entities": [{"name": "United States", "type": "country"}],
        },
    }

    package = await selector.select_event_evidence("evt_cb", limit=2)

    assert [item["article_id"] for item in package["supporting_evidence"]] == [
        "art_primary",
        "art_policy",
    ]
    assert package["contradicting_evidence"] == []
    assert package["event_score"]["total_score"] == pytest.approx(0.86)
    assert "independent_source" in package["supporting_evidence"][1]["selection_reasons"]
    assert any("de-prioritized 2 redundant articles" in note for note in package["coverage_notes"])


@pytest.mark.asyncio
async def test_evidence_selector_preserves_contradicting_evidence_when_conflict_exists():
    article_repo = FakeArticleRepository()
    query_service = FakeEventQueryService()
    ranker = FakeEventRanker()
    selector = EvidenceSelector(article_repo, query_service, ranker)

    ranker.scored_events["evt_conflict"] = make_score(
        "evt_conflict",
        profile="macro_daily",
        total_score=0.73,
    )
    query_service.timelines["evt_conflict"] = make_timeline(
        event_id="evt_conflict",
        event_type="central_bank",
        status="updated",
        latest_article_at=datetime(2026, 3, 13, 9, 30, tzinfo=UTC),
        members=[
            {
                "article_id": "art_cut",
                "source_id": "reuters",
                "title": "Central bank cuts benchmark rate by 25 bps",
                "published_at": datetime(2026, 3, 13, 9, 0, tzinfo=UTC),
                "role": "primary",
                "is_primary": True,
                "dedup_relations_count": 0,
            },
            {
                "article_id": "art_raise",
                "source_id": "wsj",
                "title": "Officials signal possible rate hike instead",
                "published_at": datetime(2026, 3, 13, 9, 10, tzinfo=UTC),
                "role": "supporting",
                "is_primary": False,
                "dedup_relations_count": 0,
            },
            {
                "article_id": "art_follow",
                "source_id": "bloomberg",
                "title": "Banks brace for policy surprise after central bank comments",
                "published_at": datetime(2026, 3, 13, 9, 20, tzinfo=UTC),
                "role": "supporting",
                "is_primary": False,
                "dedup_relations_count": 0,
            },
        ],
        supporting_sources=[{"source_id": "reuters"}, {"source_id": "bloomberg"}],
        contradicting_sources=[{"source_id": "wsj"}],
        transitions=[
            {
                "transition_id": "tr_conflict",
                "event_id": "evt_conflict",
                "trigger_article_id": "art_raise",
                "metadata": {
                    "merge_signals": {
                        "conflict": True,
                        "conflict_reason": "rate_hike_vs_rate_cut",
                    }
                },
            }
        ],
    )
    article_repo.articles = {
        "art_cut": {
            "article_id": "art_cut",
            "source_id": "reuters",
            "title": "Central bank cuts benchmark rate by 25 bps",
            "clean_content": "Reuters reported a 25 bps rate cut after the meeting.",
            "published_at": datetime(2026, 3, 13, 9, 0, tzinfo=UTC),
            "tier": 1,
            "source_type": "wire",
        },
        "art_raise": {
            "article_id": "art_raise",
            "source_id": "wsj",
            "title": "Officials signal possible rate hike instead",
            "clean_content": "WSJ reported officials discussing a possible rate hike instead of a cut.",
            "published_at": datetime(2026, 3, 13, 9, 10, tzinfo=UTC),
            "tier": 2,
            "source_type": "news",
        },
        "art_follow": {
            "article_id": "art_follow",
            "source_id": "bloomberg",
            "title": "Banks brace for policy surprise after central bank comments",
            "clean_content": "Banks are adjusting rate expectations after the policy comments.",
            "published_at": datetime(2026, 3, 13, 9, 20, tzinfo=UTC),
            "tier": 1,
            "source_type": "news",
        },
    }
    article_repo.features = {
        "art_cut": {
            "keywords": ["central bank", "rate cut", "25 bps"],
            "entities": [{"name": "Central Bank", "type": "organization"}],
        },
        "art_raise": {
            "keywords": ["officials", "rate hike", "policy"],
            "entities": [{"name": "Central Bank", "type": "organization"}],
        },
        "art_follow": {
            "keywords": ["banks", "policy", "surprise"],
            "entities": [{"name": "Banks", "type": "organization"}],
        },
    }

    package = await selector.select_event_evidence("evt_conflict", limit=3)

    assert [item["article_id"] for item in package["contradicting_evidence"]] == [
        "art_raise"
    ]
    assert "contradicting_narrative" in package["contradicting_evidence"][0]["selection_reasons"]
    assert len(package["supporting_evidence"]) == 2
    assert any("retained 1 contradicting articles" in note for note in package["coverage_notes"])
    assert selector.last_evidence_metrics["contradiction_retention_rate"] == pytest.approx(
        1.0
    )


@pytest.mark.asyncio
async def test_evidence_selector_builds_packages_for_ranked_events_in_rank_order():
    article_repo = FakeArticleRepository()
    query_service = FakeEventQueryService()
    ranker = FakeEventRanker()
    selector = EvidenceSelector(article_repo, query_service, ranker)

    query_service.timelines["evt_1"] = make_timeline(
        event_id="evt_1",
        event_type="conflict",
        status="escalating",
        latest_article_at=datetime(2026, 3, 13, 11, 0, tzinfo=UTC),
        members=[
            {
                "article_id": "art_1",
                "source_id": "reuters",
                "title": "Missile strike disrupts shipping lane",
                "published_at": datetime(2026, 3, 13, 11, 0, tzinfo=UTC),
                "role": "primary",
                "is_primary": True,
                "dedup_relations_count": 0,
            }
        ],
        supporting_sources=[{"source_id": "reuters"}],
    )
    query_service.timelines["evt_2"] = make_timeline(
        event_id="evt_2",
        event_type="central_bank",
        status="updated",
        latest_article_at=datetime(2026, 3, 13, 10, 0, tzinfo=UTC),
        members=[
            {
                "article_id": "art_2",
                "source_id": "bloomberg",
                "title": "Central bank signals measured easing cycle",
                "published_at": datetime(2026, 3, 13, 10, 0, tzinfo=UTC),
                "role": "primary",
                "is_primary": True,
                "dedup_relations_count": 0,
            }
        ],
        supporting_sources=[{"source_id": "bloomberg"}],
    )
    article_repo.articles = {
        "art_1": {
            "article_id": "art_1",
            "source_id": "reuters",
            "title": "Missile strike disrupts shipping lane",
            "clean_content": "A new strike disrupted the route and shipping costs rose 12%.",
            "published_at": datetime(2026, 3, 13, 11, 0, tzinfo=UTC),
            "tier": 1,
            "source_type": "wire",
        },
        "art_2": {
            "article_id": "art_2",
            "source_id": "bloomberg",
            "title": "Central bank signals measured easing cycle",
            "clean_content": "Officials signaled a measured easing cycle after inflation cooled.",
            "published_at": datetime(2026, 3, 13, 10, 0, tzinfo=UTC),
            "tier": 1,
            "source_type": "news",
        },
    }
    article_repo.features = {
        "art_1": {"keywords": ["shipping", "strike", "12%"], "entities": []},
        "art_2": {"keywords": ["central bank", "easing"], "entities": []},
    }
    ranker.ranked_result = [
        {
            "event_id": "evt_1",
            "total_score": 0.91,
            "score": make_score("evt_1", profile="risk_daily", total_score=0.91),
            "event": {"event_id": "evt_1"},
        },
        {
            "event_id": "evt_2",
            "total_score": 0.67,
            "score": make_score("evt_2", profile="risk_daily", total_score=0.67),
            "event": {"event_id": "evt_2"},
        },
    ]

    with patch("src.services.evidence_selector.log_stage_metrics") as mock_log_metrics:
        packages = await selector.select_ranked_event_evidence(
            statuses=["active", "updated", "escalating"],
            profile="risk_daily",
            per_event_limit=1,
            limit=2,
        )

    assert [item["event_id"] for item in packages] == ["evt_1", "evt_2"]
    assert packages[0]["event_score"]["profile"] == "risk_daily"
    assert packages[0]["supporting_evidence"][0]["article_id"] == "art_1"
    assert packages[1]["supporting_evidence"][0]["article_id"] == "art_2"
    assert ranker.rank_calls[0]["profile"] == "risk_daily"
    mock_log_metrics.assert_called_once()
    logged_metrics = mock_log_metrics.call_args.args[2]
    assert logged_metrics["events_considered"] == 2
    assert logged_metrics["event_card_entry_ratio"] == pytest.approx(1.0)
    assert logged_metrics["evidence_compression_ratio"] == pytest.approx(1.0)
