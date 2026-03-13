from __future__ import annotations

import asyncio
from collections.abc import Mapping, Sequence
from datetime import date, datetime
from typing import Any, Protocol

from ..utils.logger import get_logger
from .metrics import build_report_metrics, log_stage_metrics
from .prompts import (
    MACRO_ANALYST_PROMPT_V2,
    MARKET_STRATEGIST_PROMPT_V2,
    SENTIMENT_ANALYST_PROMPT_V2,
    build_macro_analyst_input,
    build_market_strategist_input,
    build_sentiment_analyst_input,
)
from .report_models import DailyReport

logger = get_logger("report-orchestrator")


class AIServiceLike(Protocol):
    last_report_guard_stats: dict[str, Any]
    last_report_metrics: dict[str, Any]

    async def _resolve_shared_context_window(self) -> tuple[int, dict[str, int]]: ...

    def _compute_input_budget(self, context_window: int) -> dict[str, int]: ...

    async def build_market_price_context(self) -> str: ...

    async def call_agent(
        self,
        name: str,
        system_prompt: str,
        user_content: str,
        use_json: bool = True,
    ) -> str: ...

    async def parse_daily_report_json(self, raw_text: str) -> dict[str, Any]: ...

    async def _persist_predictions(self, report: DailyReport) -> None: ...


class ReportContextBuilderLike(Protocol):
    def build_context(
        self,
        *,
        event_briefs: Sequence[Mapping[str, Any]],
        theme_briefs: Sequence[Mapping[str, Any]],
        market_context: Any = "",
        token_budget: int,
        profile: str = "macro_daily",
    ) -> dict[str, Any]: ...

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
    ) -> dict[str, Any]: ...


class ReportRunTrackerLike(Protocol):
    async def record_completed_run(
        self,
        *,
        report: DailyReport,
        context_package: Mapping[str, Any],
        profile: str,
        report_date: date | None = None,
        version: str | None = None,
        report_metrics: Mapping[str, Any] | None = None,
        guard_stats: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]: ...


class ReportOrchestrator:
    def __init__(
        self,
        ai_service: AIServiceLike,
        report_context_builder: ReportContextBuilderLike,
        report_run_tracker: ReportRunTrackerLike | None = None,
    ):
        self.ai_service = ai_service
        self.report_context_builder = report_context_builder
        self.report_run_tracker = report_run_tracker
        self.last_context_package: dict[str, Any] = {}
        self.last_report_guard_stats: dict[str, Any] = {}
        self.last_report_metrics: dict[str, Any] = {}
        self.last_agent_outputs: dict[str, str] = {}
        self.last_report_trace: dict[str, Any] = {}

    async def generate_event_centric_report(
        self,
        *,
        event_briefs: Sequence[Mapping[str, Any]] | None = None,
        theme_briefs: Sequence[Mapping[str, Any]] | None = None,
        statuses: Sequence[str] | None = None,
        since: datetime | None = None,
        profile: str = "macro_daily",
        token_budget: int | None = None,
        market_context: Any = None,
        event_limit: int = 12,
        theme_limit: int = 6,
        evidence_limit: int = 4,
        report_date: date | None = None,
        version: str | None = None,
    ) -> DailyReport:
        self.last_context_package = {}
        self.last_report_guard_stats = {}
        self.last_report_metrics = {}
        self.last_agent_outputs = {}
        self.last_report_trace = {}

        shared_window, provider_windows = await self.ai_service._resolve_shared_context_window()
        budget = self.ai_service._compute_input_budget(shared_window)
        usable_input = max(int(token_budget or 0), 0) or budget["usable_input"]
        resolved_market_context = await self._resolve_market_context(market_context)

        if event_briefs is not None or theme_briefs is not None:
            context_package = self.report_context_builder.build_context(
                event_briefs=list(event_briefs or []),
                theme_briefs=list(theme_briefs or []),
                market_context=resolved_market_context,
                token_budget=usable_input,
                profile=profile,
            )
        else:
            context_package = await self.report_context_builder.build_context_from_services(
                statuses=statuses,
                since=since,
                profile=profile,
                token_budget=usable_input,
                market_context=resolved_market_context,
                event_limit=event_limit,
                theme_limit=theme_limit,
                evidence_limit=evidence_limit,
                report_date=report_date,
                version=version,
            )

        prompt_sections = self._mapping(context_package.get("prompt_sections"))
        combined_context_text = self._text(prompt_sections.get("combined_context_text"))
        market_context_text = self._text(prompt_sections.get("market_context_text"))

        macro_input = build_macro_analyst_input(combined_context_text)
        sentiment_input = build_sentiment_analyst_input(
            combined_context_text,
            market_context_text,
        )

        logger.info(
            f"Event-centric report context ready: window={shared_window}, usable={usable_input}, "
            f"providers={provider_windows}, events={len(self._sequence_of_mappings(context_package.get('selected_event_briefs')))}, "
            f"themes={len(self._sequence_of_mappings(context_package.get('selected_theme_briefs')))}"
        )

        macro_out, sentiment_out = await self._run_parallel_analysts(
            macro_input=macro_input,
            sentiment_input=sentiment_input,
        )

        strategist_input, guard_stats = self._guard_strategist_input(
            context_text=combined_context_text,
            macro_out=macro_out,
            sentiment_out=sentiment_out,
            market_context_text=market_context_text,
            usable_budget=usable_input,
        )
        final_raw = await self.ai_service.call_agent(
            "MarketStrategist",
            MARKET_STRATEGIST_PROMPT_V2,
            strategist_input,
            use_json=True,
        )
        parsed_json = await self.ai_service.parse_daily_report_json(final_raw)
        report = DailyReport(**parsed_json)

        self.last_context_package = dict(context_package)
        self.last_report_guard_stats = dict(guard_stats)
        self.last_agent_outputs = {
            "macro": macro_out,
            "sentiment": sentiment_out,
            "strategist": final_raw,
        }
        self.last_report_metrics = self._build_report_metrics(
            report=report,
            context_package=context_package,
            profile=profile,
            guard_stats=guard_stats,
        )
        self.ai_service.last_report_guard_stats = dict(self.last_report_guard_stats)
        self.ai_service.last_report_metrics = dict(self.last_report_metrics)
        log_stage_metrics(
            logger,
            "report",
            self.last_report_metrics,
            service="ReportOrchestrator.generate_event_centric_report",
        )

        await self.ai_service._persist_predictions(report)
        if self.report_run_tracker is not None:
            self.last_report_trace = await self.report_run_tracker.record_completed_run(
                report=report,
                context_package=context_package,
                profile=profile,
                report_date=report_date,
                version=version,
                report_metrics=self.last_report_metrics,
                guard_stats=guard_stats,
            )
        return report

    async def _resolve_market_context(self, market_context: Any) -> Any:
        if market_context is None:
            return await self.ai_service.build_market_price_context()
        return market_context

    async def _run_parallel_analysts(
        self,
        *,
        macro_input: str,
        sentiment_input: str,
    ) -> tuple[str, str]:
        return await asyncio.gather(
            self.ai_service.call_agent(
                "MacroAnalyst",
                MACRO_ANALYST_PROMPT_V2,
                macro_input,
            ),
            self.ai_service.call_agent(
                "SentimentAnalyst",
                SENTIMENT_ANALYST_PROMPT_V2,
                sentiment_input,
            ),
        )

    def _guard_strategist_input(
        self,
        *,
        context_text: str,
        macro_out: str,
        sentiment_out: str,
        market_context_text: str,
        usable_budget: int,
    ) -> tuple[str, dict[str, Any]]:
        initial_input = build_market_strategist_input(
            context_text,
            macro_out,
            sentiment_out,
            market_context_text,
        )
        pre_tokens = estimate_tokens(initial_input)
        fixed_tokens = estimate_tokens(
            build_market_strategist_input(
                "",
                macro_out,
                sentiment_out,
                market_context_text,
            )
        )
        max_context_tokens = max(0, usable_budget - fixed_tokens)
        trimmed_sections: list[str] = []
        guarded_context_text = context_text

        if estimate_tokens(context_text) > max_context_tokens and max_context_tokens >= 0:
            guarded_context_text = truncate_to_token_budget(
                context_text,
                max_context_tokens,
            )
            trimmed_sections.append("context")

        final_input = build_market_strategist_input(
            guarded_context_text,
            macro_out,
            sentiment_out,
            market_context_text,
        )
        post_tokens = estimate_tokens(final_input)

        if post_tokens > usable_budget:
            final_input = truncate_to_token_budget(final_input, usable_budget)
            trimmed_sections.append("final-hard-cap")
            post_tokens = estimate_tokens(final_input)

        return final_input, {
            "pre_guard_tokens": pre_tokens,
            "post_guard_tokens": post_tokens,
            "trimmed_sections": trimmed_sections,
        }

    def _build_report_metrics(
        self,
        *,
        report: DailyReport,
        context_package: Mapping[str, Any],
        profile: str,
        guard_stats: Mapping[str, Any],
    ) -> dict[str, Any]:
        selected_events = self._sequence_of_mappings(
            context_package.get("selected_event_briefs")
        )
        selected_themes = self._sequence_of_mappings(
            context_package.get("selected_theme_briefs")
        )
        metrics = build_report_metrics(
            raw_news_input_count=0,
            cluster_count=len(selected_themes),
            report_generated=True,
            investment_trend_count=len(report.investmentTrends),
            guard_stats=guard_stats,
        )
        metrics.update(
            {
                "profile": profile,
                "context_event_count": len(selected_events),
                "context_theme_count": len(selected_themes),
            }
        )
        return metrics

    def _mapping(self, value: Any) -> dict[str, Any]:
        return dict(value) if isinstance(value, Mapping) else {}

    def _sequence_of_mappings(self, value: Any) -> list[dict[str, Any]]:
        if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
            return []
        return [dict(item) for item in value if isinstance(item, Mapping)]

    @staticmethod
    def _text(value: Any) -> str:
        if value is None:
            return ""
        if isinstance(value, str):
            return value.strip()
        return str(value).strip()


def estimate_tokens(text: str) -> int:
    return int(len(text) / 3.5)


def truncate_to_token_budget(text: str, max_tokens: int) -> str:
    normalized_budget = max(int(max_tokens), 0)
    if normalized_budget <= 0:
        return ""
    max_chars = int(normalized_budget * 3.5)
    if len(text) <= max_chars:
        return text
    truncated = text[:max_chars]
    last_newline = truncated.rfind("\n")
    if last_newline > max_chars * 0.8:
        return truncated[:last_newline]
    return truncated


__all__ = ["ReportOrchestrator"]
