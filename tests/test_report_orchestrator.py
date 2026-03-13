from __future__ import annotations

from datetime import date, datetime
import json
from typing import Any, Sequence
from unittest.mock import patch

import pytest

from src.services.report_models import DailyReport
from src.services.report_orchestrator import ReportOrchestrator


class FakeAIService:
    def __init__(self):
        self.last_report_guard_stats: dict[str, Any] = {}
        self.last_report_metrics: dict[str, Any] = {}
        self.agent_calls: list[dict[str, Any]] = []
        self.persisted_reports: list[DailyReport] = []
        self.market_context_calls = 0

    async def _resolve_shared_context_window(self) -> tuple[int, dict[str, int]]:
        return 16000, {"Primary:gpt-4o": 16000}

    def _compute_input_budget(self, context_window: int) -> dict[str, int]:
        assert context_window == 16000
        return {
            "context_window": context_window,
            "output_reserve": 2048,
            "safety_margin": 4000,
            "prompt_overhead": 2000,
            "usable_input": 1200,
        }

    async def build_market_price_context(self) -> str:
        self.market_context_calls += 1
        return "[MARKET CONTEXT]\nTop movers up: CL=F (+1.40%)"

    async def call_agent(
        self,
        name: str,
        system_prompt: str,
        user_content: str,
        use_json: bool = True,
    ) -> str:
        self.agent_calls.append(
            {
                "name": name,
                "system_prompt": system_prompt,
                "user_content": user_content,
                "use_json": use_json,
            }
        )
        if name == "MacroAnalyst":
            return json.dumps(
                {
                    "coreThesis": "能源冲击推升通胀尾部风险",
                    "keyDrivers": ["航运扰动"],
                    "riskScenarios": ["冲突升级"],
                    "watchpoints": ["运价"],
                    "confidence": 77,
                },
                ensure_ascii=False,
            )
        if name == "SentimentAnalyst":
            return json.dumps(
                {
                    "marketRegime": "Risk-off",
                    "sentimentDrivers": ["避险买盘"],
                    "crossAssetSignals": ["原油走强"],
                    "positioningRisks": ["油价拥挤"],
                    "confidence": 70,
                },
                ensure_ascii=False,
            )
        return """{
            "date": "2026-03-13",
            "intelligenceDigest": [],
            "executiveSummary": "主线是事件卡驱动的能源与风险情绪再定价。",
            "globalEvents": [],
            "economicAnalysis": "航运与能源冲击抬升通胀尾部风险。",
            "investmentTrends": [
                {"assetClass": "Brent", "trend": "Bullish", "rationale": "能源风险溢价抬升"}
            ]
        }"""

    async def parse_daily_report_json(self, raw_text: str) -> dict[str, Any]:
        return json.loads(raw_text)

    async def _persist_predictions(self, report: DailyReport) -> None:
        self.persisted_reports.append(report)


class FakeReportContextBuilder:
    def __init__(self):
        self.build_context_calls: list[dict[str, Any]] = []
        self.build_context_from_services_calls: list[dict[str, Any]] = []
        self.context_package = {
            "selected_event_briefs": [
                {
                    "event_id": "evt_energy",
                    "render_mode": "full",
                    "brief_json": {"eventId": "evt_energy"},
                }
            ],
            "selected_theme_briefs": [
                {
                    "theme_key": "energy",
                    "brief_json": {"themeKey": "energy"},
                }
            ],
            "prompt_sections": {
                "event_briefs_text": "[EVENT BRIEFS]\n- evt_energy",
                "theme_briefs_text": "[THEME BRIEFS]\n- energy",
                "market_context_text": "[MARKET CONTEXT]\nTop movers up: CL=F (+1.40%)",
                "combined_context_text": "[EVENT BRIEFS]\n- evt_energy\n\n[THEME BRIEFS]\n- energy\n\n[MARKET CONTEXT]\nTop movers up: CL=F (+1.40%)",
            },
            "budget_summary": {"total_tokens": 320},
            "coverage_summary": {"event_count": 1, "theme_count": 1},
            "truncation_summary": {
                "dropped_event_ids": [],
                "dropped_theme_keys": [],
                "compressed_event_ids": [],
                "hard_cap_hit": False,
            },
        }

    def build_context(
        self,
        *,
        event_briefs: Sequence[dict[str, Any]],
        theme_briefs: Sequence[dict[str, Any]],
        market_context: Any = "",
        token_budget: int,
        profile: str = "macro_daily",
    ) -> dict[str, Any]:
        self.build_context_calls.append(
            {
                "event_briefs": list(event_briefs),
                "theme_briefs": list(theme_briefs),
                "market_context": market_context,
                "token_budget": token_budget,
                "profile": profile,
            }
        )
        return dict(self.context_package)

    async def build_context_from_services(
        self,
        *,
        statuses: Sequence[str] | None = None,
        since: datetime | None = None,
        profile: str = "macro_daily",
        token_budget: int,
        market_context: Any = "",
        event_limit: int = 12,
        theme_limit: int = 6,
        evidence_limit: int = 4,
        report_date: date | None = None,
        version: str | None = None,
    ) -> dict[str, Any]:
        self.build_context_from_services_calls.append(
            {
                "statuses": list(statuses or []),
                "since": since,
                "profile": profile,
                "token_budget": token_budget,
                "market_context": market_context,
                "event_limit": event_limit,
                "theme_limit": theme_limit,
                "evidence_limit": evidence_limit,
                "report_date": report_date,
                "version": version,
            }
        )
        return dict(self.context_package)


@pytest.mark.asyncio
async def test_report_orchestrator_generates_event_centric_report_from_services():
    ai_service = FakeAIService()
    builder = FakeReportContextBuilder()
    orchestrator = ReportOrchestrator(ai_service, builder)

    with patch("src.services.report_orchestrator.log_stage_metrics") as mock_log_metrics:
        report = await orchestrator.generate_event_centric_report(
            statuses=["new", "updated"],
            profile="risk_daily",
            event_limit=5,
            theme_limit=3,
            evidence_limit=2,
            report_date=date(2026, 3, 13),
        )

    assert isinstance(report, DailyReport)
    assert report.executiveSummary == "主线是事件卡驱动的能源与风险情绪再定价。"
    assert builder.build_context_from_services_calls[0]["profile"] == "risk_daily"
    assert builder.build_context_from_services_calls[0]["event_limit"] == 5
    assert ai_service.market_context_calls == 1
    assert [call["name"] for call in ai_service.agent_calls] == [
        "MacroAnalyst",
        "SentimentAnalyst",
        "MarketStrategist",
    ]
    strategist_call = ai_service.agent_calls[2]
    assert "[EVENT BRIEFS]" in strategist_call["user_content"]
    assert "[THEME BRIEFS]" in strategist_call["user_content"]
    assert "[MARKET CONTEXT]" in strategist_call["user_content"]
    assert "raw news" not in strategist_call["user_content"].lower()
    assert orchestrator.last_context_package["coverage_summary"]["event_count"] == 1
    assert orchestrator.last_report_metrics["context_event_count"] == 1
    assert orchestrator.last_report_metrics["report_generated"] is True
    assert len(ai_service.persisted_reports) == 1
    mock_log_metrics.assert_called_once()
    assert mock_log_metrics.call_args.args[1] == "report"


@pytest.mark.asyncio
async def test_report_orchestrator_uses_explicit_briefs_without_service_build():
    ai_service = FakeAIService()
    builder = FakeReportContextBuilder()
    orchestrator = ReportOrchestrator(ai_service, builder)

    report = await orchestrator.generate_event_centric_report(
        event_briefs=[{"brief_json": {"eventId": "evt_1"}}],
        theme_briefs=[{"brief_json": {"themeKey": "energy"}}],
        market_context="Top movers up: CL=F (+1.40%)",
        profile="strategy_am",
        token_budget=900,
    )

    assert isinstance(report, DailyReport)
    assert len(builder.build_context_calls) == 1
    assert builder.build_context_from_services_calls == []
    assert builder.build_context_calls[0]["token_budget"] == 900
    assert builder.build_context_calls[0]["profile"] == "strategy_am"
    assert ai_service.market_context_calls == 0


@pytest.mark.asyncio
async def test_report_orchestrator_builds_market_context_when_missing():
    ai_service = FakeAIService()
    builder = FakeReportContextBuilder()
    orchestrator = ReportOrchestrator(ai_service, builder)

    await orchestrator.generate_event_centric_report(
        event_briefs=[{"brief_json": {"eventId": "evt_1"}}],
        theme_briefs=[],
    )

    assert ai_service.market_context_calls == 1
