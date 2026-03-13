from __future__ import annotations

from datetime import UTC, datetime
import json
from typing import Any, Sequence
from unittest.mock import patch

import pytest

from src.services.event_summarizer import EventSummarizer


class FakeBriefRepository:
    def __init__(self, *, stringify_brief_json: bool = False):
        self.upserted: list[dict[str, Any]] = []
        self.stringify_brief_json = stringify_brief_json

    async def upsert_event_brief(self, brief: dict[str, Any]) -> dict[str, Any]:
        payload = dict(brief)
        if self.stringify_brief_json:
            payload["brief_json"] = json.dumps(payload["brief_json"], ensure_ascii=False)
        self.upserted.append(payload)
        return payload


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


class FakeEvidenceSelector:
    def __init__(self):
        self.event_packages: dict[str, dict[str, Any]] = {}
        self.ranked_packages: list[dict[str, Any]] = []
        self.event_calls: list[dict[str, Any]] = []
        self.ranked_calls: list[dict[str, Any]] = []

    async def select_event_evidence(
        self,
        event_id: str,
        *,
        profile: str = "macro_daily",
        limit: int | None = None,
    ) -> dict[str, Any]:
        self.event_calls.append({"event_id": event_id, "profile": profile, "limit": limit})
        return dict(self.event_packages[event_id])

    async def select_ranked_event_evidence(
        self,
        *,
        statuses: Sequence[str] | None = None,
        since: datetime | None = None,
        theme: str | None = None,
        profile: str = "macro_daily",
        per_event_limit: int = 4,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        self.ranked_calls.append(
            {
                "statuses": list(statuses or []),
                "since": since,
                "theme": theme,
                "profile": profile,
                "per_event_limit": per_event_limit,
                "limit": limit,
            }
        )
        return [dict(item) for item in self.ranked_packages[:limit]]


class FakeAIService:
    def __init__(self, response: str):
        self.response = response
        self.calls: list[dict[str, Any]] = []

    async def call_agent(
        self, name: str, system_prompt: str, user_content: str, use_json: bool = True
    ) -> str:
        self.calls.append(
            {
                "name": name,
                "system_prompt": system_prompt,
                "user_content": user_content,
                "use_json": use_json,
            }
        )
        return self.response


def make_score(
    *,
    profile: str,
    total_score: float,
    novelty_score: float,
    corroboration_score: float,
    source_quality_score: float,
    uncertainty_score: float,
    top_drivers: list[str],
) -> dict[str, Any]:
    return {
        "profile": profile,
        "total_score": total_score,
        "novelty_score": novelty_score,
        "corroboration_score": corroboration_score,
        "source_quality_score": source_quality_score,
        "uncertainty_score": uncertainty_score,
        "payload": {
            "explanation": {
                "top_drivers": [
                    {"dimension": driver, "contribution": 0.2}
                    for driver in top_drivers
                ]
            }
        },
    }


def make_timeline(
    *,
    event_id: str,
    status: str,
    event_type: str,
    canonical_title: str,
    article_count: int,
    source_count: int,
    channels: list[str],
    regions: list[str],
    assets: list[str],
    transitions: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "event": {
            "event_id": event_id,
            "status": status,
            "event_type": event_type,
            "canonical_title": canonical_title,
            "article_count": article_count,
            "source_count": source_count,
            "latest_article_at": datetime(2026, 3, 13, 12, 0, tzinfo=UTC),
        },
        "members": [],
        "transitions": transitions,
        "enrichment": {
            "event_type": event_type,
            "regions": [{"name": item} for item in regions],
            "market_channels": [{"name": item} for item in channels],
            "assets": [{"name": item} for item in assets],
            "source_count": source_count,
            "member_count": article_count,
        },
        "scores": [],
    }


@pytest.mark.asyncio
async def test_event_summarizer_persists_rule_based_event_brief():
    brief_repo = FakeBriefRepository()
    query_service = FakeEventQueryService()
    evidence_selector = FakeEvidenceSelector()
    summarizer = EventSummarizer(brief_repo, query_service, evidence_selector)

    query_service.timelines["evt_shipping"] = make_timeline(
        event_id="evt_shipping",
        status="escalating",
        event_type="conflict",
        canonical_title="Missile strike disrupts Red Sea shipping lane",
        article_count=4,
        source_count=3,
        channels=["energy", "shipping"],
        regions=["red sea"],
        assets=["brent"],
        transitions=[
            {
                "to_state": "escalating",
                "reason": "impact_scope_expanded",
            }
        ],
    )
    evidence_selector.event_packages["evt_shipping"] = {
        "event_id": "evt_shipping",
        "profile": "risk_daily",
        "event_score": make_score(
            profile="risk_daily",
            total_score=0.91,
            novelty_score=0.82,
            corroboration_score=0.86,
            source_quality_score=0.9,
            uncertainty_score=0.08,
            top_drivers=["market_impact_score", "threat_score"],
        ),
        "supporting_evidence": [
            {
                "article_id": "art_1",
                "source_id": "reuters",
                "title": "Missile strike disrupts Red Sea shipping lane",
            },
            {
                "article_id": "art_2",
                "source_id": "ap",
                "title": "Oil rises as carriers reroute around Red Sea",
            },
        ],
        "contradicting_evidence": [],
    }

    with patch("src.services.event_summarizer.log_stage_metrics") as mock_log_metrics:
        brief = await summarizer.summarize_event(
            "evt_shipping",
            profile="risk_daily",
            evidence_limit=2,
        )

    brief_json = brief["brief_json"]
    assert brief["event_id"] == "evt_shipping"
    assert brief["model"] == "rule_template_v1"
    assert brief_json["canonicalTitle"] == "Missile strike disrupts Red Sea shipping lane"
    assert brief_json["stateChange"] == "escalated"
    assert brief_json["marketChannels"] == ["energy", "shipping"]
    assert brief_json["regions"] == ["red sea"]
    assert brief_json["assets"] == ["brent"]
    assert brief_json["novelty"] == "high"
    assert brief_json["corroboration"] == "strong"
    assert brief_json["confidence"] > 0.85
    assert brief_json["evidenceRefs"] == ["art_1", "art_2"]
    assert any(
        "Missile strike disrupts Red Sea shipping lane" in fact
        for fact in brief_json["coreFacts"]
    )
    assert "market impact" in brief_json["whyItMatters"]
    assert summarizer.last_brief_metrics["briefs_generated"] == 1
    mock_log_metrics.assert_called_once()


@pytest.mark.asyncio
async def test_event_summarizer_uses_llm_brief_when_json_response_parses():
    brief_repo = FakeBriefRepository()
    query_service = FakeEventQueryService()
    evidence_selector = FakeEvidenceSelector()
    ai_service = FakeAIService(
        json.dumps(
            {
                "canonicalTitle": "LLM rewrite of shipping disruption",
                "stateChange": "escalated",
                "coreFacts": ["Rerouting is lifting freight and energy risk premiums."],
                "whyItMatters": "Supply disruption matters for commodities.",
                "analysis": "Risk is concentrated in shipping and crude logistics.",
                "confidence": 0.93,
            }
        )
    )
    summarizer = EventSummarizer(
        brief_repo,
        query_service,
        evidence_selector,
        ai_service=ai_service,
    )

    query_service.timelines["evt_shipping"] = make_timeline(
        event_id="evt_shipping",
        status="escalating",
        event_type="conflict",
        canonical_title="Missile strike disrupts Red Sea shipping lane",
        article_count=4,
        source_count=3,
        channels=["energy", "shipping"],
        regions=["red sea"],
        assets=["brent"],
        transitions=[
            {
                "to_state": "escalating",
                "reason": "impact_scope_expanded",
            }
        ],
    )
    evidence_selector.event_packages["evt_shipping"] = {
        "event_id": "evt_shipping",
        "profile": "risk_daily",
        "event_score": make_score(
            profile="risk_daily",
            total_score=0.91,
            novelty_score=0.82,
            corroboration_score=0.86,
            source_quality_score=0.9,
            uncertainty_score=0.08,
            top_drivers=["market_impact_score", "threat_score"],
        ),
        "supporting_evidence": [
            {
                "article_id": "art_1",
                "source_id": "reuters",
                "title": "Missile strike disrupts Red Sea shipping lane",
            },
        ],
        "contradicting_evidence": [],
    }

    with patch("src.services.event_summarizer.logger.warning") as mock_warning:
        brief = await summarizer.summarize_event(
            "evt_shipping",
            profile="risk_daily",
            evidence_limit=1,
        )

    brief_json = brief["brief_json"]
    assert brief_json["canonicalTitle"] == "LLM rewrite of shipping disruption"
    assert brief_json["whyItMatters"] == "Supply disruption matters for commodities."
    assert brief_json["analysis"] == "Risk is concentrated in shipping and crude logistics."
    assert brief_json["confidence"] == pytest.approx(0.93)
    assert ai_service.calls[0]["name"] == "EventSummarizer"
    assert ai_service.calls[0]["use_json"] is True
    mock_warning.assert_not_called()


@pytest.mark.asyncio
async def test_event_summarizer_captures_contradictions_in_brief_json():
    brief_repo = FakeBriefRepository()
    query_service = FakeEventQueryService()
    evidence_selector = FakeEvidenceSelector()
    summarizer = EventSummarizer(brief_repo, query_service, evidence_selector)

    query_service.timelines["evt_rates"] = make_timeline(
        event_id="evt_rates",
        status="updated",
        event_type="central_bank",
        canonical_title="Central bank surprises market with policy shift",
        article_count=3,
        source_count=2,
        channels=["rates", "fx"],
        regions=["turkey"],
        assets=["try"],
        transitions=[
            {
                "to_state": "updated",
                "reason": "material_new_facts",
            }
        ],
    )
    evidence_selector.event_packages["evt_rates"] = {
        "event_id": "evt_rates",
        "profile": "macro_daily",
        "event_score": make_score(
            profile="macro_daily",
            total_score=0.73,
            novelty_score=0.58,
            corroboration_score=0.62,
            source_quality_score=0.74,
            uncertainty_score=0.41,
            top_drivers=["novelty_score", "market_impact_score"],
        ),
        "supporting_evidence": [
            {
                "article_id": "art_cut",
                "source_id": "reuters",
                "title": "Central bank cuts benchmark rate by 25 bps",
            }
        ],
        "contradicting_evidence": [
            {
                "article_id": "art_raise",
                "source_id": "wsj",
                "title": "Officials signal possible rate hike instead",
            }
        ],
    }

    brief = await summarizer.summarize_event("evt_rates")

    brief_json = brief["brief_json"]
    assert brief_json["stateChange"] == "updated"
    assert brief_json["contradictions"] == [
        {
            "articleId": "art_raise",
            "sourceId": "wsj",
            "title": "Officials signal possible rate hike instead",
        }
    ]
    assert brief_json["evidenceRefs"] == ["art_cut", "art_raise"]
    assert "contradictory reporting remains active" in brief_json["whyItMatters"]


@pytest.mark.asyncio
async def test_event_summarizer_summarizes_ranked_events_in_order_and_logs_metrics():
    brief_repo = FakeBriefRepository()
    query_service = FakeEventQueryService()
    evidence_selector = FakeEvidenceSelector()
    summarizer = EventSummarizer(brief_repo, query_service, evidence_selector)

    query_service.timelines["evt_1"] = make_timeline(
        event_id="evt_1",
        status="escalating",
        event_type="conflict",
        canonical_title="Drone attack disrupts export terminal",
        article_count=4,
        source_count=3,
        channels=["energy"],
        regions=["middle east"],
        assets=["brent"],
        transitions=[{"to_state": "escalating", "reason": "impact_scope_expanded"}],
    )
    query_service.timelines["evt_2"] = make_timeline(
        event_id="evt_2",
        status="updated",
        event_type="central_bank",
        canonical_title="Central bank signals slower easing path",
        article_count=3,
        source_count=2,
        channels=["rates", "fx"],
        regions=["europe"],
        assets=["eur"],
        transitions=[{"to_state": "updated", "reason": "material_new_facts"}],
    )
    evidence_selector.ranked_packages = [
        {
            "event_id": "evt_1",
            "profile": "risk_daily",
            "event_score": make_score(
                profile="risk_daily",
                total_score=0.88,
                novelty_score=0.77,
                corroboration_score=0.8,
                source_quality_score=0.84,
                uncertainty_score=0.14,
                top_drivers=["threat_score", "market_impact_score"],
            ),
            "supporting_evidence": [
                {
                    "article_id": "art_1",
                    "source_id": "reuters",
                    "title": "Drone attack disrupts export terminal",
                }
            ],
            "contradicting_evidence": [],
        },
        {
            "event_id": "evt_2",
            "profile": "risk_daily",
            "event_score": make_score(
                profile="risk_daily",
                total_score=0.64,
                novelty_score=0.49,
                corroboration_score=0.68,
                source_quality_score=0.79,
                uncertainty_score=0.22,
                top_drivers=["market_impact_score", "novelty_score"],
            ),
            "supporting_evidence": [
                {
                    "article_id": "art_2",
                    "source_id": "bloomberg",
                    "title": "Central bank signals slower easing path",
                }
            ],
            "contradicting_evidence": [
                {
                    "article_id": "art_3",
                    "source_id": "ft",
                    "title": "Officials downplay urgency of near-term easing",
                }
            ],
        },
    ]

    with patch("src.services.event_summarizer.log_stage_metrics") as mock_log_metrics:
        briefs = await summarizer.summarize_ranked_events(
            statuses=["updated", "escalating"],
            profile="risk_daily",
            evidence_limit=2,
            limit=2,
        )

    assert [item["event_id"] for item in briefs] == ["evt_1", "evt_2"]
    assert evidence_selector.ranked_calls[0]["profile"] == "risk_daily"
    assert summarizer.last_brief_metrics["briefs_generated"] == 2
    assert summarizer.last_brief_metrics["contradiction_brief_ratio"] == pytest.approx(
        0.5
    )
    mock_log_metrics.assert_called_once()
    assert mock_log_metrics.call_args.args[1] == "brief"


@pytest.mark.asyncio
async def test_event_summarizer_metrics_tolerate_string_backed_brief_json():
    brief_repo = FakeBriefRepository(stringify_brief_json=True)
    query_service = FakeEventQueryService()
    evidence_selector = FakeEvidenceSelector()
    summarizer = EventSummarizer(brief_repo, query_service, evidence_selector)

    query_service.timelines["evt_1"] = make_timeline(
        event_id="evt_1",
        status="escalating",
        event_type="conflict",
        canonical_title="Drone attack disrupts export terminal",
        article_count=4,
        source_count=3,
        channels=["energy"],
        regions=["middle east"],
        assets=["brent"],
        transitions=[{"to_state": "escalating", "reason": "impact_scope_expanded"}],
    )
    evidence_selector.ranked_packages = [
        {
            "event_id": "evt_1",
            "profile": "risk_daily",
            "event_score": make_score(
                profile="risk_daily",
                total_score=0.88,
                novelty_score=0.77,
                corroboration_score=0.8,
                source_quality_score=0.84,
                uncertainty_score=0.14,
                top_drivers=["threat_score", "market_impact_score"],
            ),
            "supporting_evidence": [
                {
                    "article_id": "art_1",
                    "source_id": "reuters",
                    "title": "Drone attack disrupts export terminal",
                }
            ],
            "contradicting_evidence": [],
        }
    ]

    briefs = await summarizer.summarize_ranked_events(profile="risk_daily", limit=1)

    assert isinstance(briefs[0]["brief_json"], str)
    assert summarizer.last_brief_metrics["briefs_generated"] == 1
    assert summarizer.last_brief_metrics["avg_confidence"] > 0.0
    assert summarizer.last_brief_metrics["avg_total_score"] == pytest.approx(0.88)
    assert summarizer.last_brief_metrics["avg_evidence_ref_count"] == pytest.approx(1.0)
