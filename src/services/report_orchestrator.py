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
    ) -> DailyReport | None:
        self.last_context_package = {}
        self.last_report_guard_stats = {}
        self.last_report_metrics = {}
        self.last_agent_outputs = {}
        self.last_report_trace = {}
        resolved_report_date = report_date or date.today()

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
                report_date=resolved_report_date,
                version=version,
            )

        selected_events = self._sequence_of_mappings(
            context_package.get("selected_event_briefs")
        )
        selected_themes = self._sequence_of_mappings(
            context_package.get("selected_theme_briefs")
        )
        if not selected_events and not selected_themes:
            self.last_context_package = dict(context_package)
            self.last_report_metrics = self._build_empty_report_metrics(
                context_package=context_package,
                profile=profile,
            )
            self.ai_service.last_report_guard_stats = {}
            self.ai_service.last_report_metrics = dict(self.last_report_metrics)
            return None

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
        report.date = resolved_report_date.isoformat()
        report = self._apply_sparse_report_fallback(
            report=report,
            context_package=context_package,
        )

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
                report_date=resolved_report_date,
                version=version,
                report_metrics=self.last_report_metrics,
                guard_stats=guard_stats,
            )
        return report

    def _apply_sparse_report_fallback(
        self,
        *,
        report: DailyReport,
        context_package: Mapping[str, Any],
    ) -> DailyReport:
        selected_events = self._sequence_of_mappings(
            context_package.get("selected_event_briefs")
        )
        selected_themes = self._sequence_of_mappings(
            context_package.get("selected_theme_briefs")
        )
        if not selected_events and not selected_themes:
            return report

        default_summary = "暂无明确主线，建议关注后续数据更新。"
        fallback_fields: list[str] = []
        payload = report.model_dump()

        if self._is_sparse_text(report.executiveSummary, default_summary):
            payload["executiveSummary"] = self._fallback_executive_summary(
                selected_events
            )
            fallback_fields.append("executiveSummary")

        if self._is_sparse_text(report.economicAnalysis, default_summary):
            payload["economicAnalysis"] = self._fallback_economic_analysis(
                selected_events=selected_events,
                selected_themes=selected_themes,
            )
            fallback_fields.append("economicAnalysis")

        if not report.investmentTrends:
            payload["investmentTrends"] = self._fallback_investment_trends(
                selected_events=selected_events,
                selected_themes=selected_themes,
            )
            fallback_fields.append("investmentTrends")

        if fallback_fields:
            logger.warning(
                "MarketStrategist output sparse; applied fallback fields: "
                + ", ".join(fallback_fields)
            )
            return DailyReport(**payload)
        return report

    def _fallback_executive_summary(
        self, selected_events: Sequence[Mapping[str, Any]]
    ) -> str:
        brief_json = self._first_event_brief(selected_events)
        title = self._text(brief_json.get("canonicalTitle"))
        why = self._text(brief_json.get("whyItMatters"))
        state = self._text(brief_json.get("stateChange"))
        if title and why:
            if state:
                return f"{title}（{state}）正在主导市场叙事，核心影响为：{why}"
            return f"{title}正在主导市场叙事，核心影响为：{why}"
        if why:
            return why
        if title:
            return f"{title}是当前最需要关注的事件主线。"
        return "当前事件链正在重定价市场预期，建议关注后续变化。"

    def _fallback_economic_analysis(
        self,
        *,
        selected_events: Sequence[Mapping[str, Any]],
        selected_themes: Sequence[Mapping[str, Any]],
    ) -> str:
        event_brief = self._first_event_brief(selected_events)
        theme_brief = self._first_theme_brief(selected_themes)
        why = self._text(event_brief.get("whyItMatters"))
        regions = self._text_list(event_brief.get("regions"))
        channels = self._text_list(event_brief.get("marketChannels"))
        theme_summary = self._text(theme_brief.get("summary"))
        theme_name = (
            self._text(theme_brief.get("displayName"))
            or self._text(theme_brief.get("themeKey"))
        )

        parts: list[str] = []
        if why:
            parts.append(why)
        if theme_name:
            if theme_summary:
                parts.append(f"主题“{theme_name}”显示：{theme_summary}")
            else:
                parts.append(f"当前市场主线集中在“{theme_name}”相关链条。")
        if regions:
            parts.append(f"重点区域包括：{', '.join(regions[:3])}。")
        if channels:
            parts.append(f"主要影响通道为：{', '.join(channels[:3])}。")
        if not parts:
            return "当前事件链仍在演化，建议结合后续数据跟踪跨资产传导。"
        return " ".join(parts)

    def _fallback_investment_trends(
        self,
        *,
        selected_events: Sequence[Mapping[str, Any]],
        selected_themes: Sequence[Mapping[str, Any]],
    ) -> list[dict[str, str]]:
        trends: list[dict[str, str]] = []
        seen_asset_classes: set[str] = set()

        for theme in selected_themes[:3]:
            brief_json = self._mapping(theme.get("brief_json"))
            theme_key = self._text(brief_json.get("themeKey")).lower()
            display_name = (
                self._text(brief_json.get("displayName"))
                or self._text(brief_json.get("themeKey"))
                or "Macro Basket"
            )
            summary = (
                self._text(brief_json.get("summary"))
                or "主题事件仍在演化，建议保持跟踪。"
            )
            asset_class = display_name
            trend = "Neutral"
            if "energy" in theme_key or "commodit" in theme_key:
                asset_class = "Energy"
                trend = "Bullish"
            elif "risk" in theme_key or "geopolit" in theme_key:
                asset_class = "Risk Assets"
                trend = "Neutral"
            if asset_class in seen_asset_classes:
                continue
            trends.append(
                {
                    "assetClass": asset_class,
                    "trend": trend,
                    "rationale": summary,
                }
            )
            seen_asset_classes.add(asset_class)

        if trends:
            return trends

        event_brief = self._first_event_brief(selected_events)
        why = self._text(event_brief.get("whyItMatters")) or "事件影响路径仍在形成。"
        channels = {channel.lower() for channel in self._text_list(event_brief.get("marketChannels"))}
        if {"energy", "commodities", "shipping"} & channels:
            return [
                {
                    "assetClass": "Energy",
                    "trend": "Bullish",
                    "rationale": why,
                }
            ]
        return [
            {
                "assetClass": "Macro Basket",
                "trend": "Neutral",
                "rationale": why,
            }
        ]

    def _build_empty_report_metrics(
        self,
        *,
        context_package: Mapping[str, Any],
        profile: str,
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
            report_generated=False,
            investment_trend_count=0,
            guard_stats={},
        )
        metrics.update(
            {
                "profile": profile,
                "context_event_count": len(selected_events),
                "context_theme_count": len(selected_themes),
            }
        )
        return metrics

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

    def _text_list(self, value: Any) -> list[str]:
        if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
            return []
        result: list[str] = []
        for item in value:
            text = self._text(item)
            if text:
                result.append(text)
        return result

    def _first_event_brief(
        self,
        selected_events: Sequence[Mapping[str, Any]],
    ) -> dict[str, Any]:
        if not selected_events:
            return {}
        first = self._mapping(selected_events[0])
        return self._mapping(first.get("brief_json"))

    def _first_theme_brief(
        self,
        selected_themes: Sequence[Mapping[str, Any]],
    ) -> dict[str, Any]:
        if not selected_themes:
            return {}
        first = self._mapping(selected_themes[0])
        return self._mapping(first.get("brief_json"))

    def _is_sparse_text(self, value: Any, default_text: str) -> bool:
        text = self._text(value)
        if not text:
            return True
        return text == default_text

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
