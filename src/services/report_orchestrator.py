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
        self.last_sparse_fallback_fields: list[str] = []

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
        self.last_sparse_fallback_fields = []
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

        # ── LangGraph 路径 (可通过 USE_LANGGRAPH=true 开启) ──
        from ..config.settings import CONFIG
        if getattr(CONFIG, "use_langgraph", False):
            return await self._generate_via_langgraph(
                context_package=context_package,
                combined_context_text=combined_context_text,
                market_context_text=market_context_text,
                resolved_report_date=resolved_report_date,
                profile=profile,
                version=version,
            )

        macro_out, sentiment_out = await self._run_parallel_analysts(
            macro_input=macro_input,
            sentiment_input=sentiment_input,
        )

        # 注入增强的宏观因子 (Phase 3 另类数据增强)
        enhanced_market_factors = ""
        try:
            from ..utils.market_data import get_volatility_context, get_yield_curve_context
            vix_data = await get_volatility_context()
            yield_data = await get_yield_curve_context()
            enhanced_market_factors = (
                f"\n[MACRO REGIME INDICATORS]\n"
                f"- VIX (Volatility): {vix_data['price']} | Regime: {vix_data['regime']}\n"
                f"- 10Y Rate: {yield_data['tnx']}%\n"
                f"- Yield Curve (Proxy): {'INVERTED' if yield_data.get('inverted') else 'Normal'} (Spread: {yield_data.get('spread')})\n"
            )
            market_context_text += enhanced_market_factors
        except Exception as e:
            logger.warning(f"Failed to fetch enhanced macro factors: {e}")

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
        # Log the full raw output to ensure we can diagnose parsing or sparse issues
        logger.info(
            f"MarketStrategist raw output (first 1000 chars):\n{final_raw[:1000] if final_raw else 'EMPTY'}"
        )
        if not final_raw or len(final_raw.strip()) < 20:
            logger.warning(
                "MarketStrategist returned empty/minimal output ({} chars)",
                len(final_raw or ""),
            )
        parsed_json = await self.ai_service.parse_daily_report_json(final_raw)

        # 引入 CRO 审核循环 (Phase 3 辩论机制)
        final_report_json = parsed_json
        from .prompts import RISK_MANAGER_PROMPT, build_risk_manager_input
        try:
            cro_input = build_risk_manager_input(parsed_json, market_context_text)
            cro_raw = await self.ai_service.call_agent(
                "RiskManager",
                RISK_MANAGER_PROMPT,
                cro_input,
                use_json=True,
            )
            final_report_json = await self.ai_service.parse_daily_report_json(cro_raw)
            logger.info("RiskManager (CRO) review completed and refined the report.")
        except Exception as e:
            logger.warning(f"RiskManager review failed, using original CIO draft: {e}")

        report = DailyReport(**final_report_json)
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

        if self._is_sparse_macro_chain(report.macroTransmissionChain):
            payload["macroTransmissionChain"] = self._fallback_macro_transmission_chain(
                selected_events=selected_events,
                selected_themes=selected_themes,
            )
            fallback_fields.append("macroTransmissionChain")

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

        if self._is_sparse_asset_breakdowns(report.assetTransmissionBreakdowns):
            payload["assetTransmissionBreakdowns"] = (
                self._fallback_asset_transmission_breakdowns(
                    selected_events=selected_events,
                    selected_themes=selected_themes,
                    investment_trends=payload.get("investmentTrends"),
                )
            )
            fallback_fields.append("assetTransmissionBreakdowns")

        self.last_sparse_fallback_fields = list(fallback_fields)
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

    def _fallback_macro_transmission_chain(
        self,
        *,
        selected_events: Sequence[Mapping[str, Any]],
        selected_themes: Sequence[Mapping[str, Any]],
    ) -> dict[str, Any]:
        event_brief = self._first_event_brief(selected_events)
        theme_brief = self._first_theme_brief(selected_themes)
        shock_source = (
            self._text(event_brief.get("canonicalTitle"))
            or self._text(event_brief.get("title"))
            or self._text(theme_brief.get("displayName"))
            or self._text(theme_brief.get("themeKey"))
            or "当前事件主线"
        )
        theme_key = self._text(theme_brief.get("themeKey")).lower()
        theme_name = (
            self._text(theme_brief.get("displayName"))
            or self._text(theme_brief.get("themeKey"))
            or "当前主题"
        )
        why = self._text(event_brief.get("whyItMatters"))
        channels = self._text_list(event_brief.get("marketChannels"))
        macro_variables = self._infer_macro_variables(theme_key=theme_key, channels=channels)
        market_pricing = self._fallback_market_pricing(
            why=why,
            channels=channels,
            theme_name=theme_name,
        )
        allocation_implication = self._fallback_allocation_implication(
            theme_key=theme_key,
            channels=channels,
        )
        headline_var = macro_variables[0] if macro_variables else "风险溢价"
        steps = [
            {"stage": "冲击源", "driver": shock_source},
            {
                "stage": "宏观变量",
                "driver": f"{'、'.join(macro_variables[:3])}开始被重新定价。"
                if macro_variables
                else "风险溢价与增长预期开始重新定价。",
            },
            {"stage": "市场定价", "driver": market_pricing},
            {"stage": "配置含义", "driver": allocation_implication},
        ]

        return {
            "headline": f"{shock_source}正在通过{headline_var}重定价跨资产表现。",
            "shockSource": shock_source,
            "macroVariables": macro_variables,
            "marketPricing": market_pricing,
            "allocationImplication": allocation_implication,
            "steps": steps,
            "timeframe": "short-term",
            "confidence": self._fallback_confidence(event_brief),
        }

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
                },
                {
                    "assetClass": "Gold",
                    "trend": "Bullish",
                    "rationale": "能源与地缘风险同时抬升时，黄金通常承接部分风险溢价与通胀对冲需求。",
                },
            ]
        return [
            {
                "assetClass": "Macro Basket",
                "trend": "Neutral",
                "rationale": why,
            },
            {
                "assetClass": "Risk Assets",
                "trend": "Neutral",
                "rationale": "主线仍在演化，风险资产更容易受预期反复影响。",
            }
        ]

    def _fallback_asset_transmission_breakdowns(
        self,
        *,
        selected_events: Sequence[Mapping[str, Any]],
        selected_themes: Sequence[Mapping[str, Any]],
        investment_trends: Any,
    ) -> list[dict[str, Any]]:
        event_brief = self._first_event_brief(selected_events)
        theme_brief = self._first_theme_brief(selected_themes)
        theme_key = self._text(theme_brief.get("themeKey")).lower()
        theme_name = (
            self._text(theme_brief.get("displayName"))
            or self._text(theme_brief.get("themeKey"))
            or "当前主题"
        )
        shock_source = (
            self._text(event_brief.get("canonicalTitle"))
            or self._text(event_brief.get("title"))
            or theme_name
        )
        why = self._text(event_brief.get("whyItMatters")) or "当前事件链正在影响跨资产定价。"
        channels = self._text_list(event_brief.get("marketChannels"))
        macro_variables = self._infer_macro_variables(theme_key=theme_key, channels=channels)
        watch_signals = self._build_watch_signals(
            event_brief=event_brief,
            theme_name=theme_name,
            channels=channels,
        )

        breakdowns: list[dict[str, Any]] = []
        seen_asset_classes: set[str] = set()
        trend_candidates = self._sequence_of_mappings(investment_trends)

        for trend_item in trend_candidates[:4]:
            asset_class = self._text(trend_item.get("assetClass")) or "Macro Basket"
            if asset_class in seen_asset_classes:
                continue
            trend = self._text(trend_item.get("trend")) or "Neutral"
            rationale = self._text(trend_item.get("rationale")) or why
            breakdowns.append(
                {
                    "assetClass": asset_class,
                    "trend": trend,
                    "coreView": rationale,
                    "transmissionPath": self._build_asset_transmission_path(
                        shock_source=shock_source,
                        macro_variables=macro_variables,
                        asset_class=asset_class,
                        trend=trend,
                    ),
                    "keyDrivers": self._build_asset_key_drivers(
                        macro_variables=macro_variables,
                        theme_name=theme_name,
                        why=why,
                    ),
                    "watchSignals": watch_signals,
                    "timeframe": self._text(trend_item.get("timeframe")) or "short-term",
                    "confidence": self._normalize_confidence_like(trend_item.get("confidence")) or self._fallback_confidence(event_brief),
                }
            )
            seen_asset_classes.add(asset_class)

        for template in self._suggest_asset_breakdown_templates(
            theme_key=theme_key,
            channels=channels,
            shock_source=shock_source,
            macro_variables=macro_variables,
            theme_name=theme_name,
            why=why,
            watch_signals=watch_signals,
            confidence=self._fallback_confidence(event_brief),
        ):
            asset_class = self._text(template.get("assetClass"))
            if not asset_class or asset_class in seen_asset_classes:
                continue
            breakdowns.append(template)
            seen_asset_classes.add(asset_class)
            if len(breakdowns) >= 4:
                break

        return breakdowns[:4]

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
                "macro_chain_present": False,
                "asset_breakdown_count": 0,
                "fallback_fields": list(self.last_sparse_fallback_fields),
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
                "macro_chain_present": report.macroTransmissionChain is not None,
                "asset_breakdown_count": len(report.assetTransmissionBreakdowns or []),
                "fallback_fields": list(self.last_sparse_fallback_fields),
            }
        )
        return metrics

    def _mapping(self, value: Any) -> dict[str, Any]:
        if isinstance(value, Mapping):
            return dict(value)
        if hasattr(value, "model_dump"):
            dumped = value.model_dump()
            return dict(dumped) if isinstance(dumped, Mapping) else {}
        return {}

    def _sequence_of_mappings(self, value: Any) -> list[dict[str, Any]]:
        if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
            return []
        result: list[dict[str, Any]] = []
        for item in value:
            if isinstance(item, Mapping):
                result.append(dict(item))
            elif hasattr(item, "model_dump"):
                dumped = item.model_dump()
                if isinstance(dumped, Mapping):
                    result.append(dict(dumped))
        return result

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

    def _is_sparse_macro_chain(self, value: Any) -> bool:
        chain = self._mapping(value)
        if not chain:
            return True

        headline = self._text(chain.get("headline"))
        market_pricing = self._text(chain.get("marketPricing"))
        allocation = self._text(chain.get("allocationImplication"))
        steps = self._sequence_of_mappings(chain.get("steps"))

        if len(steps) < 2 and not market_pricing and not allocation:
            return True

        generic_fragments = (
            "地缘政治影响市场",
            "事件影响市场",
            "建议关注后续",
            "暂无明确主线",
        )
        text_blob = " ".join(
            part for part in [headline, market_pricing, allocation] if part
        )
        return bool(text_blob) and any(fragment in text_blob for fragment in generic_fragments)

    def _is_sparse_asset_breakdowns(self, value: Any) -> bool:
        items = self._sequence_of_mappings(value)
        if not items:
            return True

        informative_count = 0
        for item in items:
            core_view = self._text(item.get("coreView"))
            path = self._text(item.get("transmissionPath"))
            pair_trade = self._text(item.get("pairTrade"))
            scenario = self._mapping(item.get("scenarioAnalysis"))
            
            # 如果提供了配对交易或场景推演，即视为极具价值的信息
            if pair_trade or scenario.get("bullCase") or scenario.get("bearCase"):
                informative_count += 2 # 加倍权重
            elif core_view and path:
                informative_count += 1
                
        return informative_count < 2

    def _fallback_market_pricing(
        self,
        *,
        why: str,
        channels: Sequence[str],
        theme_name: str,
    ) -> str:
        lowered = {channel.lower() for channel in channels}
        parts: list[str] = []
        if why:
            parts.append(why)
        if {"energy", "commodities", "shipping"} & lowered:
            parts.append("能源与航运相关资产更容易先表现强势，风险资产承压。")
        elif {"rates", "fx"} & lowered:
            parts.append("利率与汇率资产会更早反映预期差，权益资产随后跟进。")
        else:
            parts.append(f"市场会先围绕“{theme_name}”主线重新定价跨资产风险溢价。")
        return " ".join(parts)

    def _fallback_allocation_implication(
        self,
        *,
        theme_key: str,
        channels: Sequence[str],
    ) -> str:
        lowered = {channel.lower() for channel in channels}
        if "energy" in theme_key or {"energy", "commodities", "shipping"} & lowered:
            return "配置上更偏向能源链和防御性资产，对高贝塔风险资产保持克制。"
        if "rates" in theme_key or "fx" in theme_key:
            return "配置上优先关注利率与汇率敏感资产，再决定风险资产暴露。"
        return "配置上优先顺着主线做强表达，避免在证据不足时过度扩张风险暴露。"

    def _infer_macro_variables(
        self,
        *,
        theme_key: str,
        channels: Sequence[str],
    ) -> list[str]:
        lowered = {channel.lower() for channel in channels}
        if "energy" in theme_key or {"energy", "commodities", "shipping"} & lowered:
            return ["能源供给预期", "通胀预期", "风险溢价"]
        if "central" in theme_key or {"rates", "fx"} & lowered:
            return ["利率路径预期", "美元流动性", "估值折现率"]
        if "geopolit" in theme_key or "risk" in theme_key:
            return ["风险溢价", "避险需求", "跨资产波动率"]
        return ["风险溢价", "增长预期", "跨资产波动率"]

    def _build_watch_signals(
        self,
        *,
        event_brief: Mapping[str, Any],
        theme_name: str,
        channels: Sequence[str],
    ) -> list[str]:
        signals = self._dedupe_texts(
            [
                self._text(event_brief.get("stateChange")) and f"事件状态是否继续{self._text(event_brief.get('stateChange'))}",
                self._text(event_brief.get("lastTransition")) and "事件状态迁移是否继续恶化或缓和",
                theme_name and f"{theme_name}主题是否继续扩散",
                {"energy", "commodities", "shipping"} & {channel.lower() for channel in channels} and "油价与航运价格是否继续上行",
            ]
        )
        return signals[:3]

    def _build_asset_key_drivers(
        self,
        *,
        macro_variables: Sequence[str],
        theme_name: str,
        why: str,
    ) -> list[str]:
        drivers = self._dedupe_texts(
            list(macro_variables[:3]) + [theme_name, why[:48] if why else ""]
        )
        return drivers[:4]

    def _build_asset_transmission_path(
        self,
        *,
        shock_source: str,
        macro_variables: Sequence[str],
        asset_class: str,
        trend: str,
    ) -> str:
        macro_leg = "、".join(macro_variables[:2]) if macro_variables else "风险溢价"
        direction = {
            "Bullish": "价格偏强",
            "Bearish": "价格承压",
            "Neutral": "价格震荡",
        }.get(trend, "价格受主线牵引")
        return f"{shock_source} -> {macro_leg}重定价 -> {asset_class}更直接表达该主线 -> {direction}"

    def _suggest_asset_breakdown_templates(
        self,
        *,
        theme_key: str,
        channels: Sequence[str],
        shock_source: str,
        macro_variables: Sequence[str],
        theme_name: str,
        why: str,
        watch_signals: Sequence[str],
        confidence: float,
    ) -> list[dict[str, Any]]:
        lowered = {channel.lower() for channel in channels}
        templates: list[dict[str, Any]] = []
        if "energy" in theme_key or {"energy", "commodities", "shipping"} & lowered:
            templates.extend(
                [
                    {
                        "assetClass": "Crude Oil",
                        "trend": "Bullish",
                        "coreView": why or "能源供给扰动会先抬升原油风险溢价。",
                        "transmissionPath": self._build_asset_transmission_path(
                            shock_source=shock_source,
                            macro_variables=macro_variables,
                            asset_class="Crude Oil",
                            trend="Bullish",
                        ),
                        "keyDrivers": self._build_asset_key_drivers(
                            macro_variables=macro_variables,
                            theme_name=theme_name,
                            why=why,
                        ),
                        "watchSignals": list(watch_signals),
                        "timeframe": "short-term",
                        "confidence": confidence,
                    },
                    {
                        "assetClass": "Gold",
                        "trend": "Bullish",
                        "coreView": "若能源冲击继续抬升风险溢价与通胀担忧，黄金更容易承接防御性需求。",
                        "transmissionPath": self._build_asset_transmission_path(
                            shock_source=shock_source,
                            macro_variables=macro_variables,
                            asset_class="Gold",
                            trend="Bullish",
                        ),
                        "keyDrivers": self._dedupe_texts(
                            list(macro_variables[:2]) + ["避险需求", theme_name]
                        )[:4],
                        "watchSignals": list(watch_signals),
                        "timeframe": "short-term",
                        "confidence": max(55.0, confidence - 8.0),
                    },
                ]
            )
        else:
            templates.extend(
                [
                    {
                        "assetClass": "Risk Assets",
                        "trend": "Neutral",
                        "coreView": "风险资产更容易在主线摇摆时表现为高波动而非单边趋势。",
                        "transmissionPath": self._build_asset_transmission_path(
                            shock_source=shock_source,
                            macro_variables=macro_variables,
                            asset_class="Risk Assets",
                            trend="Neutral",
                        ),
                        "keyDrivers": self._build_asset_key_drivers(
                            macro_variables=macro_variables,
                            theme_name=theme_name,
                            why=why,
                        ),
                        "watchSignals": list(watch_signals),
                        "timeframe": "short-term",
                        "confidence": max(50.0, confidence - 10.0),
                    },
                    {
                        "assetClass": "USD",
                        "trend": "Neutral",
                        "coreView": "若主线先通过风险溢价和流动性传导，美元通常是最先被重新定价的缓冲资产之一。",
                        "transmissionPath": self._build_asset_transmission_path(
                            shock_source=shock_source,
                            macro_variables=macro_variables,
                            asset_class="USD",
                            trend="Neutral",
                        ),
                        "keyDrivers": self._dedupe_texts(
                            list(macro_variables[:2]) + ["美元流动性", theme_name]
                        )[:4],
                        "watchSignals": list(watch_signals),
                        "timeframe": "short-term",
                        "confidence": max(50.0, confidence - 10.0),
                    },
                ]
            )
        return templates

    def _fallback_confidence(self, event_brief: Mapping[str, Any]) -> float:
        for key in ("confidence", "supportConfidence", "totalScore"):
            confidence = self._normalize_confidence_like(event_brief.get(key))
            if confidence is not None:
                return confidence
        return 72.0

    def _normalize_confidence_like(self, value: Any) -> float | None:
        try:
            confidence = float(value)
        except Exception:
            return None
        if confidence <= 1:
            confidence *= 100
        return max(0.0, min(100.0, confidence))

    def _dedupe_texts(self, values: Sequence[Any]) -> list[str]:
        seen: set[str] = set()
        result: list[str] = []
        for value in values:
            text = self._text(value)
            if not text or text in seen:
                continue
            seen.add(text)
            result.append(text)
        return result

    @staticmethod
    def _text(value: Any) -> str:
        if value is None:
            return ""
        if isinstance(value, str):
            return value.strip()
        return str(value).strip()

    async def _generate_via_langgraph(
        self,
        *,
        context_package: dict,
        combined_context_text: str,
        market_context_text: str,
        resolved_report_date,
        profile: str,
        version: str | None,
    ) -> DailyReport | None:
        from .langgraph_orchestrator import build_report_workflow
        from .agent_state import AgentState

        workflow = build_report_workflow(self.ai_service)

        initial_state: AgentState = {
            "events": list(self._sequence_of_mappings(context_package.get("selected_event_briefs"))),
            "themes": list(self._sequence_of_mappings(context_package.get("selected_theme_briefs"))),
            "combined_context_text": combined_context_text,
            "market_context_text": market_context_text,
            "macro_output": None,
            "sentiment_output": None,
            "strategist_output": None,
            "risk_manager_output": None,
            "final_report_json": None,
            "errors": [],
            "retry_count": 0,
        }

        result = await workflow.ainvoke(initial_state)

        if result.get("errors"):
            for err in result["errors"]:
                logger.warning(f"LangGraph agent error: {err}")

        report_json = result.get("final_report_json")
        if not report_json:
            logger.error("LangGraph workflow produced no report")
            return None

        report = DailyReport(**report_json)
        report.date = resolved_report_date.isoformat()
        self.last_context_package = dict(context_package)
        return report


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
