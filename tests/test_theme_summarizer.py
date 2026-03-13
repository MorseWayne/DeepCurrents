from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any, Sequence
from unittest.mock import patch

import pytest

from src.services.theme_summarizer import ThemeSummarizer


class FakeBriefRepository:
    def __init__(self):
        self.upserted: list[dict[str, Any]] = []

    async def upsert_theme_brief(self, brief: dict[str, Any]) -> dict[str, Any]:
        payload = dict(brief)
        self.upserted.append(payload)
        return payload


class FakeEventSummarizer:
    def __init__(self):
        self.ranked_briefs: list[dict[str, Any]] = []
        self.calls: list[dict[str, Any]] = []

    async def summarize_ranked_events(
        self,
        *,
        statuses: Sequence[str] | None = None,
        since: datetime | None = None,
        theme: str | None = None,
        profile: str = "macro_daily",
        limit: int = 20,
        evidence_limit: int = 4,
        version: str | None = None,
    ) -> list[dict[str, Any]]:
        self.calls.append(
            {
                "statuses": list(statuses or []),
                "since": since,
                "theme": theme,
                "profile": profile,
                "limit": limit,
                "evidence_limit": evidence_limit,
                "version": version,
            }
        )
        return [dict(item) for item in self.ranked_briefs[:limit]]


def make_event_brief(
    *,
    event_id: str,
    canonical_title: str,
    state_change: str,
    event_type: str,
    channels: list[str],
    regions: list[str],
    assets: list[str],
    total_score: float,
    confidence: float,
    contradictions: list[dict[str, Any]] | None = None,
    why_it_matters: str | None = None,
) -> dict[str, Any]:
    return {
        "brief_id": f"brief_{event_id}_v1",
        "event_id": event_id,
        "version": "v1",
        "summary": canonical_title,
        "brief_json": {
            "eventId": event_id,
            "canonicalTitle": canonical_title,
            "stateChange": state_change,
            "coreFacts": [canonical_title],
            "whyItMatters": why_it_matters
            or f"{canonical_title} matters for {', '.join(channels) or 'cross-asset sentiment'}.",
            "marketChannels": channels,
            "regions": regions,
            "assets": assets,
            "confidence": confidence,
            "novelty": "high",
            "corroboration": "strong",
            "evidenceRefs": [f"art_{event_id}"],
            "contradictions": contradictions or [],
            "profile": "macro_daily",
            "eventType": event_type,
            "status": state_change,
            "totalScore": total_score,
            "lastTransition": {"toState": state_change, "reason": "material_new_facts"},
            "generatedAt": datetime(2026, 3, 13, 12, 0, tzinfo=UTC).isoformat(),
        },
    }


@pytest.mark.asyncio
async def test_theme_summarizer_persists_energy_theme_brief():
    brief_repo = FakeBriefRepository()
    event_summarizer = FakeEventSummarizer()
    summarizer = ThemeSummarizer(brief_repo, event_summarizer)

    event_summarizer.ranked_briefs = [
        make_event_brief(
            event_id="evt_shipping",
            canonical_title="Red Sea strike lifts freight and oil costs",
            state_change="escalated",
            event_type="conflict",
            channels=["energy", "shipping", "commodities"],
            regions=["middle east", "red sea"],
            assets=["brent"],
            total_score=0.91,
            confidence=0.89,
        ),
        make_event_brief(
            event_id="evt_outage",
            canonical_title="Pipeline outage tightens diesel supply",
            state_change="updated",
            event_type="supply_disruption",
            channels=["energy", "commodities"],
            regions=["middle east"],
            assets=["diesel"],
            total_score=0.76,
            confidence=0.78,
            contradictions=[
                {
                    "articleId": "art_counter",
                    "sourceId": "ft",
                    "title": "Officials say pipeline flows remain stable",
                }
            ],
        ),
        make_event_brief(
            event_id="evt_rates",
            canonical_title="Central bank warns on sticky inflation",
            state_change="updated",
            event_type="central_bank",
            channels=["rates", "fx"],
            regions=["europe"],
            assets=["eur"],
            total_score=0.62,
            confidence=0.74,
        ),
    ]

    with patch("src.services.theme_summarizer.log_stage_metrics") as mock_log_metrics:
        brief = await summarizer.summarize_theme(
            "energy",
            profile="risk_daily",
            report_date=date(2026, 3, 13),
            event_limit=10,
        )

    brief_json = brief["brief_json"]
    assert brief["theme_key"] == "energy"
    assert brief["report_date"] == date(2026, 3, 13)
    assert brief_json["themeKey"] == "energy"
    assert brief_json["bucketType"] == "taxonomy"
    assert brief_json["displayName"] == "Energy"
    assert brief_json["eventCount"] == 2
    assert brief_json["eventRefs"] == ["evt_shipping", "evt_outage"]
    assert brief_json["topEvents"][0]["eventId"] == "evt_shipping"
    assert brief_json["marketChannels"][:2] == ["energy", "commodities"]
    assert "2 events" in brief_json["summary"]
    assert brief_json["contradictionEventCount"] == 1
    assert summarizer.last_theme_metrics["themes_generated"] == 1
    assert event_summarizer.calls[0]["profile"] == "risk_daily"
    assert event_summarizer.calls[0]["limit"] == 10
    mock_log_metrics.assert_called_once()
    assert mock_log_metrics.call_args.args[1] == "theme_brief"


@pytest.mark.asyncio
async def test_theme_summarizer_builds_ranked_theme_briefs_with_region_bucket():
    brief_repo = FakeBriefRepository()
    event_summarizer = FakeEventSummarizer()
    summarizer = ThemeSummarizer(brief_repo, event_summarizer)

    event_summarizer.ranked_briefs = [
        make_event_brief(
            event_id="evt_1",
            canonical_title="Missile strike disrupts Red Sea exports",
            state_change="escalated",
            event_type="conflict",
            channels=["energy", "shipping"],
            regions=["middle east"],
            assets=["brent"],
            total_score=0.93,
            confidence=0.88,
        ),
        make_event_brief(
            event_id="evt_2",
            canonical_title="Refinery outage keeps crude flows tight",
            state_change="new",
            event_type="supply_disruption",
            channels=["energy", "commodities"],
            regions=["middle east"],
            assets=["wti"],
            total_score=0.82,
            confidence=0.81,
        ),
    ]

    briefs = await summarizer.summarize_ranked_themes(
        profile="macro_daily",
        report_date=date(2026, 3, 13),
        max_themes=5,
    )

    theme_keys = [item["theme_key"] for item in briefs]
    assert {"energy", "geopolitics", "region:middle_east"} <= set(theme_keys)
    assert theme_keys[-1] == "region:middle_east"

    region_brief = next(item for item in briefs if item["theme_key"] == "region:middle_east")
    region_json = region_brief["brief_json"]
    assert region_json["displayName"] == "Region: Middle East"
    assert region_json["bucketType"] == "region"
    assert region_json["eventCount"] == 2
    assert region_json["regions"] == ["middle east"]
    assert summarizer.last_theme_metrics["themes_generated"] == len(briefs)
    assert summarizer.last_theme_metrics["region_theme_ratio"] == pytest.approx(
        1 / len(briefs)
    )


@pytest.mark.asyncio
async def test_theme_summarizer_raises_when_theme_has_no_matching_events():
    brief_repo = FakeBriefRepository()
    event_summarizer = FakeEventSummarizer()
    summarizer = ThemeSummarizer(brief_repo, event_summarizer)

    event_summarizer.ranked_briefs = [
        make_event_brief(
            event_id="evt_rates",
            canonical_title="Central bank slows pace of easing",
            state_change="updated",
            event_type="central_bank",
            channels=["rates", "fx"],
            regions=["europe"],
            assets=["eur"],
            total_score=0.71,
            confidence=0.79,
        )
    ]

    with pytest.raises(ValueError, match="theme not found or empty: cyber"):
        await summarizer.summarize_theme("cyber")
