from __future__ import annotations

from datetime import UTC, date, datetime
import json
from typing import Any, Sequence
from unittest.mock import patch

import pytest

from src.services.report_context_builder import (
    ReportContextBuilder,
    estimate_tokens,
)
from src.utils.market_data import build_market_context_snapshot


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


class FakeThemeSummarizer:
    def __init__(self):
        self.ranked_briefs: list[dict[str, Any]] = []
        self.calls: list[dict[str, Any]] = []

    async def summarize_ranked_themes(
        self,
        *,
        statuses: Sequence[str] | None = None,
        since: datetime | None = None,
        profile: str = "macro_daily",
        report_date: date | None = None,
        event_limit: int = 20,
        max_themes: int = 8,
        evidence_limit: int = 4,
        version: str | None = None,
    ) -> list[dict[str, Any]]:
        self.calls.append(
            {
                "statuses": list(statuses or []),
                "since": since,
                "profile": profile,
                "report_date": report_date,
                "event_limit": event_limit,
                "max_themes": max_themes,
                "evidence_limit": evidence_limit,
                "version": version,
            }
        )
        return [dict(item) for item in self.ranked_briefs[:max_themes]]


def make_event_brief(
    *,
    event_id: str,
    title: str,
    state_change: str,
    event_type: str,
    total_score: float,
    confidence: float,
    channels: list[str],
    regions: list[str],
    assets: list[str],
    why: str | None = None,
    facts: list[str] | None = None,
    contradictions: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "brief_id": f"brief_{event_id}_v1",
        "event_id": event_id,
        "brief_json": {
            "eventId": event_id,
            "canonicalTitle": title,
            "stateChange": state_change,
            "coreFacts": facts or [title],
            "whyItMatters": why or f"{title} affects {', '.join(channels)}.",
            "marketChannels": channels,
            "regions": regions,
            "assets": assets,
            "confidence": confidence,
            "totalScore": total_score,
            "eventType": event_type,
            "contradictions": contradictions or [],
            "generatedAt": datetime(2026, 3, 13, 12, 0, tzinfo=UTC).isoformat(),
        },
    }


def make_theme_brief(
    *,
    theme_key: str,
    display_name: str,
    theme_score: float,
    event_count: int,
    summary: str,
    threads: list[str],
    regions: list[str],
    channels: list[str],
    event_refs: list[str],
    bucket_type: str = "taxonomy",
) -> dict[str, Any]:
    return {
        "theme_brief_id": f"theme_brief_{theme_key}_2026-03-13_v1",
        "theme_key": theme_key,
        "brief_json": {
            "themeKey": theme_key,
            "displayName": display_name,
            "bucketType": bucket_type,
            "reportDate": "2026-03-13",
            "profile": "macro_daily",
            "summary": summary,
            "coreThreads": threads,
            "eventRefs": event_refs,
            "regions": regions,
            "marketChannels": channels,
            "assets": [],
            "eventCount": event_count,
            "themeScore": theme_score,
        },
    }


def test_report_context_builder_selects_events_and_taxonomy_themes_with_budget():
    builder = ReportContextBuilder()
    event_briefs = [
        make_event_brief(
            event_id="evt_geo",
            title="Missile strike disrupts export route",
            state_change="escalated",
            event_type="conflict",
            total_score=0.92,
            confidence=0.86,
            channels=["energy", "shipping"],
            regions=["middle east"],
            assets=["brent"],
        ),
        make_event_brief(
            event_id="evt_rates",
            title="Central bank warns easing path may slow",
            state_change="updated",
            event_type="central_bank",
            total_score=0.74,
            confidence=0.8,
            channels=["rates", "fx"],
            regions=["europe"],
            assets=["eur"],
            contradictions=[
                {
                    "articleId": "art_1",
                    "sourceId": "ft",
                    "title": "Officials dispute urgency of cuts",
                }
            ],
        ),
    ]
    theme_briefs = [
        make_theme_brief(
            theme_key="energy",
            display_name="Energy",
            theme_score=0.84,
            event_count=2,
            summary="Energy theme is driven by shipping and outage risks.",
            threads=[
                "Shipping disruption is lifting freight and crude costs.",
                "Refining constraints are tightening supply.",
            ],
            regions=["middle east"],
            channels=["energy", "shipping"],
            event_refs=["evt_geo"],
        ),
        make_theme_brief(
            theme_key="central_banks",
            display_name="Central Banks",
            theme_score=0.73,
            event_count=1,
            summary="Central banks remain cautious on inflation persistence.",
            threads=["Policy guidance is pushing rates and FX repricing."],
            regions=["europe"],
            channels=["rates", "fx"],
            event_refs=["evt_rates"],
        ),
        make_theme_brief(
            theme_key="region:middle_east",
            display_name="Region: Middle East",
            theme_score=0.61,
            event_count=1,
            summary="Regional bucket for shipping tension.",
            threads=["Regional risk remains elevated."],
            regions=["middle east"],
            channels=["energy"],
            event_refs=["evt_geo"],
            bucket_type="region",
        ),
    ]

    with patch(
        "src.services.report_context_builder.log_stage_metrics"
    ) as mock_log_metrics:
        context = builder.build_context(
            event_briefs=event_briefs,
            theme_briefs=theme_briefs,
            market_context=build_market_context_snapshot(
                [
                    {"symbol": "CL=F", "price": 72.4, "changePercent": 1.4},
                    {"symbol": "DX-Y.NYB", "price": 104.2, "changePercent": 0.6},
                    {"symbol": "^GSPC", "price": 5080.0, "changePercent": -0.9},
                ],
                as_of="2026-03-13T08:00:00+00:00",
            ),
            token_budget=1600,
            profile="risk_daily",
        )

    selected_event_ids = [item["event_id"] for item in context["selected_event_briefs"]]
    selected_theme_keys = [
        item["brief_json"]["themeKey"] for item in context["selected_theme_briefs"]
    ]
    assert selected_event_ids == ["evt_geo", "evt_rates"]
    assert selected_theme_keys == ["energy", "central_banks"]
    assert "region:middle_east" in context["truncation_summary"]["dropped_theme_keys"]
    assert context["coverage_summary"]["theme_keys"] == ["energy", "central_banks"]
    assert (
        "Missile strike disrupts export route"
        in context["prompt_sections"]["event_briefs_text"]
    )
    assert "[THEME BRIEFS]" in context["prompt_sections"]["theme_briefs_text"]
    assert context["budget_summary"]["policy_name"] == "risk_daily"
    assert context["budget_summary"]["quota"]["max_events_per_theme"] == 5
    assert "Cross-asset signals:" in context["prompt_sections"]["market_context_text"]
    assert "Top movers up:" in context["prompt_sections"]["market_context_text"]
    assert builder.last_context_metrics["events_selected"] == 2
    mock_log_metrics.assert_called_once()
    assert mock_log_metrics.call_args.args[1] == "context"


def test_report_context_builder_tolerates_string_backed_brief_json():
    builder = ReportContextBuilder()
    event_brief = make_event_brief(
        event_id="evt_geo",
        title="Missile strike disrupts export route",
        state_change="escalated",
        event_type="conflict",
        total_score=0.92,
        confidence=0.86,
        channels=["energy", "shipping"],
        regions=["middle east"],
        assets=["brent"],
    )
    theme_brief = make_theme_brief(
        theme_key="energy",
        display_name="Energy",
        theme_score=0.84,
        event_count=1,
        summary="Energy theme is driven by shipping and outage risks.",
        threads=["Shipping disruption is lifting freight and crude costs."],
        regions=["middle east"],
        channels=["energy", "shipping"],
        event_refs=["evt_geo"],
    )
    event_brief["brief_json"] = json.dumps(
        event_brief["brief_json"], ensure_ascii=False
    )
    theme_brief["brief_json"] = json.dumps(
        theme_brief["brief_json"], ensure_ascii=False
    )

    context = builder.build_context(
        event_briefs=[event_brief],
        theme_briefs=[theme_brief],
        market_context="Brent +1.2%",
        token_budget=800,
        profile="macro_daily",
    )

    assert len(context["selected_event_briefs"]) == 1
    assert context["selected_event_briefs"][0]["brief_json"]["eventId"] == "evt_geo"
    assert len(context["selected_theme_briefs"]) == 1
    assert context["selected_theme_briefs"][0]["brief_json"]["themeKey"] == "energy"


def test_report_context_builder_drops_theme_before_event_and_compacts_event():
    builder = ReportContextBuilder()
    long_facts = [
        "Pipeline outage extended again with export flows cut and diesel inventories under pressure."
    ] * 4
    event_briefs = [
        make_event_brief(
            event_id="evt_energy",
            title="Pipeline outage tightens diesel supply",
            state_change="new",
            event_type="supply_disruption",
            total_score=0.88,
            confidence=0.83,
            channels=["energy", "commodities"],
            regions=["middle east"],
            assets=["diesel"],
            why="Supply disruption is repricing diesel cracks and regional shipping costs.",
            facts=long_facts,
        )
    ]
    theme_briefs = [
        make_theme_brief(
            theme_key="energy",
            display_name="Energy",
            theme_score=0.81,
            event_count=1,
            summary="Energy theme remains active across outage and freight channels.",
            threads=long_facts,
            regions=["middle east"],
            channels=["energy"],
            event_refs=["evt_energy"],
        )
    ]

    context = builder.build_context(
        event_briefs=event_briefs,
        theme_briefs=theme_briefs,
        market_context="Brent +1.4%; diesel cracks wider.",
        token_budget=110,
    )

    assert context["selected_event_briefs"][0]["render_mode"] == "compact"
    assert context["selected_theme_briefs"] == []
    assert context["truncation_summary"]["dropped_theme_keys"] == ["energy"]
    assert estimate_tokens(context["prompt_sections"]["combined_context_text"]) <= 110
    assert context["truncation_summary"]["compressed_event_ids"] == ["evt_energy"]


def test_report_context_builder_enforces_theme_and_region_diversity():
    builder = ReportContextBuilder()
    event_briefs = [
        make_event_brief(
            event_id="evt_1",
            title="Strike hits Red Sea route",
            state_change="new",
            event_type="conflict",
            total_score=0.95,
            confidence=0.88,
            channels=["energy", "shipping"],
            regions=["middle east"],
            assets=["brent"],
        ),
        make_event_brief(
            event_id="evt_2",
            title="Second attack deepens freight rerouting",
            state_change="escalated",
            event_type="conflict",
            total_score=0.9,
            confidence=0.84,
            channels=["energy", "shipping"],
            regions=["middle east"],
            assets=["brent"],
        ),
        make_event_brief(
            event_id="evt_3",
            title="Third strike keeps insurers on alert",
            state_change="updated",
            event_type="conflict",
            total_score=0.86,
            confidence=0.82,
            channels=["energy", "shipping"],
            regions=["middle east"],
            assets=["brent"],
        ),
        make_event_brief(
            event_id="evt_4",
            title="Port authority warns of more delays",
            state_change="updated",
            event_type="conflict",
            total_score=0.8,
            confidence=0.79,
            channels=["shipping"],
            regions=["middle east"],
            assets=[],
        ),
        make_event_brief(
            event_id="evt_rates",
            title="Central bank slows pace of easing",
            state_change="updated",
            event_type="central_bank",
            total_score=0.73,
            confidence=0.81,
            channels=["rates", "fx"],
            regions=["europe"],
            assets=["eur"],
        ),
    ]

    context = builder.build_context(
        event_briefs=event_briefs,
        theme_briefs=[],
        market_context="",
        token_budget=1800,
    )

    selected_event_ids = [item["event_id"] for item in context["selected_event_briefs"]]
    assert selected_event_ids == ["evt_1", "evt_2", "evt_3", "evt_4", "evt_rates"]
    assert context["truncation_summary"]["dropped_event_ids"] == []


def test_report_context_builder_applies_profile_budget_and_region_theme_limits():
    builder = ReportContextBuilder()
    event_briefs = [
        make_event_brief(
            event_id="evt_macro",
            title="Inflation surprise reprices front-end rates",
            state_change="new",
            event_type="macro_data",
            total_score=0.87,
            confidence=0.82,
            channels=["rates", "fx"],
            regions=["united states"],
            assets=["usd"],
        )
    ]
    theme_briefs = [
        make_theme_brief(
            theme_key="macro_data",
            display_name="Macro Data",
            theme_score=0.78,
            event_count=1,
            summary="Macro data is driving front-end repricing.",
            threads=["Inflation and payrolls remain the main catalyst."],
            regions=["united states"],
            channels=["rates", "fx"],
            event_refs=["evt_macro"],
        ),
        make_theme_brief(
            theme_key="region:united_states",
            display_name="Region: United States",
            theme_score=0.72,
            event_count=1,
            summary="Regional macro bucket remains active.",
            threads=["US macro surprises continue to drive rates."],
            regions=["united states"],
            channels=["rates"],
            event_refs=["evt_macro"],
            bucket_type="region",
        ),
        make_theme_brief(
            theme_key="region:global",
            display_name="Region: Global",
            theme_score=0.68,
            event_count=1,
            summary="Global cross-asset spillover remains in focus.",
            threads=["Dollar and rates spill over into global assets."],
            regions=["global"],
            channels=["fx"],
            event_refs=["evt_macro"],
            bucket_type="region",
        ),
    ]

    risk_context = builder.build_context(
        event_briefs=event_briefs,
        theme_briefs=theme_briefs,
        market_context="UST2Y +9bp\nDXY firmer",
        token_budget=1000,
        profile="risk_daily",
    )
    strategy_context = builder.build_context(
        event_briefs=event_briefs,
        theme_briefs=theme_briefs,
        market_context="UST2Y +9bp\nDXY firmer",
        token_budget=1000,
        profile="strategy_am",
    )

    risk_themes = [item["theme_key"] for item in risk_context["selected_theme_briefs"]]
    strategy_themes = [
        item["theme_key"] for item in strategy_context["selected_theme_briefs"]
    ]

    assert risk_context["budget_summary"]["event_budget"] == 700
    assert risk_context["budget_summary"]["market_budget"] == 200
    assert strategy_context["budget_summary"]["event_budget"] == 450
    assert strategy_context["budget_summary"]["market_budget"] == 350
    assert "macro_data" in risk_themes
    assert "macro_data" in strategy_themes
    assert sum(1 for item in strategy_themes if item.startswith("region:")) <= 1
    assert (
        "region:united_states"
        in strategy_context["truncation_summary"]["dropped_theme_keys"]
    )


@pytest.mark.asyncio
async def test_report_context_builder_builds_from_summarizer_services():
    event_summarizer = FakeEventSummarizer()
    theme_summarizer = FakeThemeSummarizer()
    builder = ReportContextBuilder(event_summarizer, theme_summarizer)

    event_summarizer.ranked_briefs = [
        make_event_brief(
            event_id="evt_macro",
            title="Inflation surprise reprices front-end rates",
            state_change="new",
            event_type="macro_data",
            total_score=0.87,
            confidence=0.82,
            channels=["rates", "fx"],
            regions=["united states"],
            assets=["usd"],
        )
    ]
    theme_summarizer.ranked_briefs = [
        make_theme_brief(
            theme_key="macro_data",
            display_name="Macro Data",
            theme_score=0.77,
            event_count=1,
            summary="Macro data surprises are driving front-end repricing.",
            threads=["Inflation and payrolls remain the key event cluster."],
            regions=["united states"],
            channels=["rates", "fx"],
            event_refs=["evt_macro"],
        )
    ]

    context = await builder.build_context_from_services(
        statuses=["new", "updated"],
        profile="strategy_am",
        token_budget=1200,
        market_context=["UST2Y +9bp", "DXY firmer"],
        event_limit=5,
        theme_limit=3,
        evidence_limit=2,
        report_date=date(2026, 3, 13),
        version="v2",
    )

    assert event_summarizer.calls[0]["profile"] == "strategy_am"
    assert event_summarizer.calls[0]["limit"] == 5
    assert theme_summarizer.calls[0]["max_themes"] == 3
    assert context["selected_event_briefs"][0]["event_id"] == "evt_macro"
    assert context["selected_theme_briefs"][0]["brief_json"]["themeKey"] == "macro_data"
