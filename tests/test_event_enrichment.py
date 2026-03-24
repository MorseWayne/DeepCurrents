from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from typing import Any

import pytest

from src.services.event_enrichment import EventEnrichmentService


class FakeEventRepository:
    def __init__(self):
        self.events: dict[str, dict[str, Any]] = {}
        self.members_by_event: dict[str, list[dict[str, Any]]] = {}
        self.transitions_by_event: dict[str, list[dict[str, Any]]] = {}
        self.update_calls: list[tuple[str, dict[str, Any]]] = []

    async def get_event(self, event_id: str) -> dict[str, Any] | None:
        event = self.events.get(event_id)
        return dict(event) if event else None

    async def update_event(
        self,
        event_id: str,
        fields: Mapping[str, Any],
    ) -> dict[str, Any]:
        payload = dict(fields)
        self.update_calls.append((event_id, payload))
        event = self.events.setdefault(event_id, {"event_id": event_id})
        event.update(payload)
        return dict(event)

    async def list_event_members(self, event_id: str) -> list[dict[str, Any]]:
        return [dict(item) for item in self.members_by_event.get(event_id, [])]

    async def list_event_state_transitions(self, event_id: str) -> list[dict[str, Any]]:
        return [dict(item) for item in self.transitions_by_event.get(event_id, [])]


class FakeArticleRepository:
    def __init__(self):
        self.articles: dict[str, dict[str, Any]] = {}
        self.features: dict[str, dict[str, Any]] = {}

    async def get_article(self, article_id: str) -> dict[str, Any] | None:
        row = self.articles.get(article_id)
        return dict(row) if row else None

    async def get_article_features(self, article_id: str) -> dict[str, Any] | None:
        row = self.features.get(article_id)
        return dict(row) if row else None


@pytest.mark.asyncio
async def test_event_enrichment_aggregates_structured_labels_and_persists_them():
    event_repo = FakeEventRepository()
    article_repo = FakeArticleRepository()
    service = EventEnrichmentService(event_repo, article_repo)

    event_repo.events["evt_1"] = {"event_id": "evt_1", "status": "active", "metadata": {}}
    event_repo.members_by_event["evt_1"] = [
        {"event_id": "evt_1", "article_id": "art_1"},
        {"event_id": "evt_1", "article_id": "art_2"},
    ]
    event_repo.transitions_by_event["evt_1"] = [
        {
            "transition_id": "tr_1",
            "event_id": "evt_1",
            "to_state": "escalating",
            "reason": "impact_scope_expanded",
            "trigger_article_id": "art_2",
            "created_at": datetime(2026, 3, 13, 8, 0, tzinfo=UTC),
            "metadata": {},
        }
    ]
    article_repo.articles = {
        "art_1": {
            "article_id": "art_1",
            "source_id": "reuters",
            "title": "Missile strike disrupts Red Sea shipping",
            "clean_content": "Missile strike disrupts Red Sea shipping and lifts Brent crude.",
            "metadata": {"regions": ["Red Sea"], "assets": ["Brent"], "source": "Reuters"},
        },
        "art_2": {
            "article_id": "art_2",
            "source_id": "ap",
            "title": "Bab al-Mandab attack raises Brent shipping costs",
            "clean_content": "Attack near Bab al-Mandab raises Brent shipping costs again.",
            "metadata": {"locations": ["Bab al-Mandab"], "assets": ["Brent"], "source": "AP"},
        },
    }
    article_repo.features = {
        "art_1": {
            "entities": [
                {"name": "Red Sea", "type": "location"},
                {"name": "Brent", "type": "ticker"},
            ]
        },
        "art_2": {
            "entities": [
                {"name": "Bab al-Mandab", "type": "location"},
                {"name": "Brent", "type": "ticker"},
            ]
        },
    }

    result = await service.enrich_event("evt_1")

    enrichment = result["enrichment"]
    assert result["event"]["primary_region"] == "red sea"
    assert result["event"]["event_type"] == "conflict"
    assert enrichment["regions"][0]["name"] == "red sea"
    assert enrichment["assets"][0]["name"] == "brent"
    channel_names = {item["name"] for item in enrichment["market_channels"]}
    assert {"shipping", "commodities", "energy"} <= channel_names
    assert [item["source_id"] for item in enrichment["supporting_sources"]] == [
        "ap",
        "reuters",
    ]
    assert enrichment["contradicting_sources"] == []
    assert result["event"]["metadata"]["enrichment"]["event_type"] == "conflict"


@pytest.mark.asyncio
async def test_event_enrichment_marks_conflicting_sources_separately():
    event_repo = FakeEventRepository()
    article_repo = FakeArticleRepository()
    service = EventEnrichmentService(event_repo, article_repo)

    event_repo.events["evt_2"] = {"event_id": "evt_2", "status": "updated", "metadata": {}}
    event_repo.members_by_event["evt_2"] = [
        {"event_id": "evt_2", "article_id": "art_cut"},
        {"event_id": "evt_2", "article_id": "art_raise"},
    ]
    event_repo.transitions_by_event["evt_2"] = [
        {
            "transition_id": "tr_2",
            "event_id": "evt_2",
            "to_state": "updated",
            "reason": "material_new_facts",
            "trigger_article_id": "art_raise",
            "metadata": {
                "merge_signals": {
                    "conflict": True,
                    "conflict_reason": "rate_hike_vs_rate_cut",
                }
            },
        }
    ]
    article_repo.articles = {
        "art_cut": {
            "article_id": "art_cut",
            "source_id": "bloomberg",
            "title": "Turkey unexpectedly cuts benchmark rate",
            "clean_content": "Turkey unexpectedly cuts benchmark rate amid growth concerns.",
            "metadata": {"source": "Bloomberg"},
        },
        "art_raise": {
            "article_id": "art_raise",
            "source_id": "wsj",
            "title": "Turkey unexpectedly hikes benchmark rate",
            "clean_content": "Turkey unexpectedly hikes benchmark rate to defend the lira.",
            "metadata": {"source": "WSJ"},
        },
    }
    article_repo.features = {
        "art_cut": {"entities": [{"name": "Turkey", "type": "location"}]},
        "art_raise": {"entities": [{"name": "Turkey", "type": "location"}]},
    }

    result = await service.enrich_event("evt_2")

    enrichment = result["enrichment"]
    assert result["event"]["event_type"] == "central_bank"
    assert [item["source_id"] for item in enrichment["supporting_sources"]] == [
        "bloomberg"
    ]
    assert [item["source_id"] for item in enrichment["contradicting_sources"]] == [
        "wsj"
    ]


@pytest.mark.asyncio
async def test_event_enrichment_query_reuses_stored_enrichment_without_recomputing():
    event_repo = FakeEventRepository()
    article_repo = FakeArticleRepository()
    service = EventEnrichmentService(event_repo, article_repo)
    event_repo.events["evt_3"] = {
        "event_id": "evt_3",
        "metadata": {"enrichment": {"event_type": "macro_data", "regions": []}},
    }

    enrichment = await service.get_event_enrichment("evt_3")

    assert enrichment == {"event_type": "macro_data", "regions": []}
    assert event_repo.update_calls == []


@pytest.mark.asyncio
async def test_enrich_event_sentiment_no_assets():
    """事件无关联资产时，情绪评分应为 None"""
    from src.services.event_enrichment import enrich_event_sentiment

    event = {"assets": [], "id": "e1"}
    result = await enrich_event_sentiment(event, av_service=None)
    assert result.get("sentiment_score") is None


@pytest.mark.asyncio
async def test_enrich_event_sentiment_with_score():
    """正常路径：有 assets 且 AV 返回数据时，sentiment_score 为浮点数"""
    from src.services.alpha_vantage_service import (
        AlphaVantageService, NewsArticleSentiment
    )
    from src.services.event_enrichment import enrich_event_sentiment
    from unittest.mock import AsyncMock

    mock_av = AsyncMock(spec=AlphaVantageService)
    mock_av.get_news_sentiment.return_value = [
        NewsArticleSentiment(
            title="T", url="u", source="s", published="",
            ticker="SPY", sentiment_score=0.6, relevance=1.0
        )
    ]

    event = {"assets": ["SPY", "QQQ"], "id": "e2"}
    result = await enrich_event_sentiment(event, av_service=mock_av)

    assert abs(result["sentiment_score"] - 0.6) < 0.01
    assert result["sentiment_label"] == "bullish"
