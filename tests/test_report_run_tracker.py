from __future__ import annotations

from datetime import date
from typing import Any

import pytest

from src.services.report_models import DailyReport
from src.services.report_run_tracker import ReportRunTracker


class FakeReportRepository:
    def __init__(self):
        self.report_runs: dict[str, dict[str, Any]] = {}
        self.links_by_run: dict[str, list[dict[str, Any]]] = {}
        self.create_calls: list[dict[str, Any]] = []
        self.update_calls: list[dict[str, Any]] = []

    async def create_report_run(self, report_run: dict[str, Any]) -> dict[str, Any]:
        stored = dict(report_run)
        self.report_runs[stored["report_run_id"]] = stored
        self.create_calls.append(stored)
        return dict(stored)

    async def get_report_run(self, report_run_id: str) -> dict[str, Any] | None:
        run = self.report_runs.get(report_run_id)
        return dict(run) if run else None

    async def get_report_run_by_date(
        self, profile: str, report_date: date | None
    ) -> dict[str, Any] | None:
        for run in self.report_runs.values():
            if run.get("profile") == profile and run.get("report_date") == report_date:
                return dict(run)
        return None

    async def get_latest_report_run(
        self, profile: str, *, status: str = "completed"
    ) -> dict[str, Any] | None:
        matches = [
            run
            for run in self.report_runs.values()
            if run.get("profile") == profile and run.get("status") == status
        ]
        if not matches:
            return None
        matches.sort(key=lambda item: (item.get("report_date"), item.get("report_run_id")))
        return dict(matches[-1])

    async def update_report_run(
        self, report_run_id: str, fields: dict[str, Any]
    ) -> dict[str, Any]:
        current = dict(self.report_runs.get(report_run_id, {}))
        current.update(fields)
        current["report_run_id"] = report_run_id
        self.report_runs[report_run_id] = current
        self.update_calls.append({"report_run_id": report_run_id, **fields})
        return dict(current)

    async def replace_report_event_links(
        self, report_run_id: str, links: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        stored_links = [dict(item) for item in links]
        self.links_by_run[report_run_id] = stored_links
        return [dict(item) for item in stored_links]

    async def list_report_event_links(self, report_run_id: str) -> list[dict[str, Any]]:
        return [dict(item) for item in self.links_by_run.get(report_run_id, [])]


def make_report() -> DailyReport:
    return DailyReport(
        date="2026-03-13",
        intelligenceDigest=[],
        executiveSummary="事件驱动的风险溢价重新计入。",
        globalEvents=[],
        economicAnalysis="能源与航运扰动抬升通胀尾部风险。",
        investmentTrends=[
            {
                "assetClass": "Brent",
                "trend": "Bullish",
                "rationale": "供应风险溢价抬升",
            }
        ],
        riskAssessment="若冲突升级，油价与运价波动会继续放大。",
    )


def make_context_package() -> dict[str, Any]:
    return {
        "profile": "risk_daily",
        "token_budget": 900,
        "input_summary": {"event_count": 3, "theme_count": 2},
        "selected_event_briefs": [
            {
                "event_id": "evt_energy",
                "brief_id": "brief_evt_energy_v1",
                "brief_version": "v1",
                "render_mode": "full",
                "brief_json": {
                    "eventId": "evt_energy",
                    "canonicalTitle": "Export route disruption lifts crude risk premium",
                    "stateChange": "escalated",
                    "whyItMatters": "Shipping disruption is lifting energy risk.",
                    "regions": ["middle east"],
                    "marketChannels": ["energy", "shipping"],
                    "assets": ["brent"],
                    "totalScore": 0.94,
                    "confidence": 0.88,
                    "lastTransition": {"toState": "escalating", "reason": "risk spread"},
                    "evidenceRefs": ["art_1", "art_2"],
                    "contradictions": [],
                },
            },
            {
                "event_id": "evt_rates",
                "brief_id": "brief_evt_rates_v1",
                "brief_version": "v1",
                "render_mode": "compact",
                "brief_json": {
                    "eventId": "evt_rates",
                    "canonicalTitle": "ECB repricing extends after hawkish guidance",
                    "stateChange": "updated",
                    "whyItMatters": "Rates and FX reprice as easing path is questioned.",
                    "regions": ["europe"],
                    "marketChannels": ["rates_fx"],
                    "assets": ["eur"],
                    "totalScore": 0.72,
                    "confidence": 0.79,
                    "lastTransition": {"toState": "updated", "reason": "new guidance"},
                    "evidenceRefs": ["art_3"],
                    "contradictions": [{"articleId": "art_4"}],
                },
            },
        ],
        "selected_theme_briefs": [
            {
                "theme_key": "energy",
                "theme_brief_id": "theme_brief_energy_2026-03-13_v1",
                "brief_version": "v1",
                "brief_json": {"themeKey": "energy"},
            }
        ],
        "budget_summary": {
            "quota": {"event_budget_share": 0.65},
            "event_budget": 500,
            "theme_budget": 150,
            "market_budget": 250,
            "event_tokens": 340,
            "theme_tokens": 80,
            "market_tokens": 90,
            "total_tokens": 510,
        },
        "coverage_summary": {
            "event_count": 2,
            "theme_count": 1,
            "regions": ["middle east", "europe"],
            "market_channels": ["energy", "shipping", "rates_fx"],
        },
        "truncation_summary": {
            "dropped_event_ids": ["evt_macro"],
            "dropped_theme_keys": [],
            "compressed_event_ids": ["evt_rates"],
            "hard_cap_hit": False,
        },
    }


@pytest.mark.asyncio
async def test_report_run_tracker_records_completed_run_and_event_links():
    repo = FakeReportRepository()
    tracker = ReportRunTracker(repo)

    trace = await tracker.record_completed_run(
        report=make_report(),
        context_package=make_context_package(),
        profile="risk_daily",
        version="v1",
        report_metrics={"context_event_count": 2, "report_generated": True},
        guard_stats={"pre_guard_tokens": 880, "post_guard_tokens": 760},
    )

    report_run = trace["report_run"]
    assert report_run["report_run_id"] == "report_risk_daily_2026-03-13"
    assert report_run["selected_event_count"] == 2
    assert report_run["input_event_count"] == 3
    assert report_run["metadata"]["context"]["top_event_ids"] == [
        "evt_energy",
        "evt_rates",
    ]
    assert report_run["metadata"]["coverage"]["regions"] == ["middle east", "europe"]
    assert report_run["metadata"]["budget"]["guard"]["post_guard_tokens"] == 760

    event_links = trace["event_links"]
    assert [item["event_id"] for item in event_links] == ["evt_energy", "evt_rates"]
    assert event_links[0]["rationale_json"]["state_change"] == "escalated"
    assert event_links[1]["rationale_json"]["selection_reason"] == "selected_compact"
    assert trace["summary"]["state_change_mix"] == {"escalated": 1, "updated": 1}


@pytest.mark.asyncio
async def test_report_run_tracker_updates_existing_run_for_same_profile_and_date():
    repo = FakeReportRepository()
    tracker = ReportRunTracker(repo)

    await tracker.record_completed_run(
        report=make_report(),
        context_package=make_context_package(),
        profile="risk_daily",
        version="v1",
    )
    second_context = make_context_package()
    second_context["selected_event_briefs"] = second_context["selected_event_briefs"][:1]
    second_context["input_summary"] = {"event_count": 2, "theme_count": 1}

    trace = await tracker.record_completed_run(
        report=make_report(),
        context_package=second_context,
        profile="risk_daily",
        version="v1",
    )

    assert len(repo.create_calls) == 1
    assert len(repo.update_calls) == 1
    assert trace["report_run"]["selected_event_count"] == 1
    assert [item["event_id"] for item in trace["event_links"]] == ["evt_energy"]


@pytest.mark.asyncio
async def test_report_run_tracker_returns_latest_trace():
    repo = FakeReportRepository()
    tracker = ReportRunTracker(repo)

    await tracker.record_completed_run(
        report=make_report(),
        context_package=make_context_package(),
        profile="risk_daily",
        version="v1",
    )

    latest = await tracker.get_latest_report_trace("risk_daily")

    assert latest is not None
    assert latest["summary"]["report_run_id"] == "report_risk_daily_2026-03-13"
    assert latest["summary"]["selected_event_ids"] == ["evt_energy", "evt_rates"]
