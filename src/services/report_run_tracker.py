from __future__ import annotations

import json
import re
from collections import Counter
from collections.abc import Mapping, Sequence
from datetime import UTC, date, datetime
from typing import Any, Protocol

from .report_models import DailyReport


class ReportRepositoryLike(Protocol):
    async def create_report_run(self, report_run: Mapping[str, Any]) -> dict[str, Any]: ...

    async def get_report_run(self, report_run_id: str) -> dict[str, Any] | None: ...

    async def get_report_run_by_date(
        self, profile: str, report_date: date | None
    ) -> dict[str, Any] | None: ...

    async def get_latest_report_run(
        self, profile: str, *, status: str = "completed"
    ) -> dict[str, Any] | None: ...

    async def update_report_run(
        self, report_run_id: str, fields: Mapping[str, Any]
    ) -> dict[str, Any]: ...

    async def replace_report_event_links(
        self, report_run_id: str, links: Sequence[Mapping[str, Any]]
    ) -> list[dict[str, Any]]: ...

    async def list_report_event_links(self, report_run_id: str) -> list[dict[str, Any]]: ...


class ReportRunTracker:
    def __init__(self, report_repository: ReportRepositoryLike):
        self.report_repository = report_repository

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
    ) -> dict[str, Any]:
        resolved_date = self._resolve_report_date(report, report_date)
        selected_events = self._sequence_of_mappings(
            context_package.get("selected_event_briefs")
        )
        input_summary = self._mapping(context_package.get("input_summary"))
        budget_summary = self._mapping(context_package.get("budget_summary"))
        metadata = self._build_metadata(
            report=report,
            context_package=context_package,
            profile=profile,
            version=version,
            report_metrics=report_metrics,
            guard_stats=guard_stats,
        )
        existing_run = await self.report_repository.get_report_run_by_date(
            profile,
            resolved_date,
        )
        report_run_id = self._report_run_id(profile, resolved_date)
        run_payload = {
            "profile": profile,
            "report_date": resolved_date,
            "status": "completed",
            "budget_tokens": self._safe_int(
                budget_summary.get("total_tokens"),
                fallback=self._safe_int(context_package.get("token_budget")),
            ),
            "input_event_count": self._safe_int(
                input_summary.get("event_count"),
                fallback=len(selected_events),
            ),
            "selected_event_count": len(selected_events),
            "metadata": metadata,
        }

        if existing_run:
            report_run_id = self._text(existing_run.get("report_run_id")) or report_run_id
            await self.report_repository.update_report_run(report_run_id, run_payload)
        else:
            await self.report_repository.create_report_run(
                {
                    "report_run_id": report_run_id,
                    **run_payload,
                }
            )

        links = self._build_event_links(
            report_run_id=report_run_id,
            selected_events=selected_events,
            fallback_version=version,
        )
        await self.report_repository.replace_report_event_links(report_run_id, links)
        trace = await self.get_report_trace(report_run_id)
        return trace or {}

    async def get_report_trace(self, report_run_id: str) -> dict[str, Any] | None:
        report_run = await self.report_repository.get_report_run(report_run_id)
        if not report_run:
            return None
        links = await self.report_repository.list_report_event_links(report_run_id)
        normalized_links = [self._normalize_link(item) for item in links]
        return {
            "report_run": report_run,
            "event_links": normalized_links,
            "summary": self._build_trace_summary(report_run, normalized_links),
        }

    async def get_latest_report_trace(
        self,
        profile: str,
        *,
        status: str = "completed",
    ) -> dict[str, Any] | None:
        report_run = await self.report_repository.get_latest_report_run(
            profile,
            status=status,
        )
        if not report_run:
            return None
        report_run_id = self._text(report_run.get("report_run_id"))
        if not report_run_id:
            return None
        return await self.get_report_trace(report_run_id)

    def _build_metadata(
        self,
        *,
        report: DailyReport,
        context_package: Mapping[str, Any],
        profile: str,
        version: str | None,
        report_metrics: Mapping[str, Any] | None,
        guard_stats: Mapping[str, Any] | None,
    ) -> dict[str, Any]:
        selected_events = self._sequence_of_mappings(
            context_package.get("selected_event_briefs")
        )
        selected_themes = self._sequence_of_mappings(
            context_package.get("selected_theme_briefs")
        )
        budget_summary = self._mapping(context_package.get("budget_summary"))
        coverage_summary = self._mapping(context_package.get("coverage_summary"))
        truncation_summary = self._mapping(context_package.get("truncation_summary"))
        fallback_version = self._text(version) or "v1"
        event_version = self._resolve_source_version(
            selected_events,
            "brief_version",
            fallback=fallback_version,
        )
        theme_version = self._resolve_source_version(
            selected_themes,
            "brief_version",
            fallback=fallback_version,
        )

        return {
            "version": fallback_version,
            "report_summary": {
                "executive_summary": report.executiveSummary,
                "economic_analysis": report.economicAnalysis,
                "risk_assessment": report.riskAssessment or "",
                "investment_trend_count": len(report.investmentTrends),
            },
            "context": {
                "profile": profile,
                "event_count": len(selected_events),
                "theme_count": len(selected_themes),
                "theme_keys": [
                    self._text(item.get("theme_key"))
                    for item in selected_themes
                    if self._text(item.get("theme_key"))
                ],
                "top_event_ids": [
                    self._text(item.get("event_id"))
                    for item in selected_events[:5]
                    if self._text(item.get("event_id"))
                ],
                "top_theme_keys": [
                    self._text(item.get("theme_key"))
                    for item in selected_themes[:5]
                    if self._text(item.get("theme_key"))
                ],
            },
            "budget": {
                "token_budget": self._safe_int(context_package.get("token_budget")),
                "quota": self._mapping(budget_summary.get("quota")),
                "event_budget": self._safe_int(budget_summary.get("event_budget")),
                "theme_budget": self._safe_int(budget_summary.get("theme_budget")),
                "market_budget": self._safe_int(budget_summary.get("market_budget")),
                "event_tokens": self._safe_int(budget_summary.get("event_tokens")),
                "theme_tokens": self._safe_int(budget_summary.get("theme_tokens")),
                "market_tokens": self._safe_int(budget_summary.get("market_tokens")),
                "total_tokens": self._safe_int(budget_summary.get("total_tokens")),
                "guard": dict(guard_stats or {}),
            },
            "source_versions": {
                "event_brief_version": event_version,
                "theme_brief_version": theme_version,
                "prompt_profile": profile,
            },
            "coverage": {
                "regions": self._text_list(coverage_summary.get("regions")),
                "market_channels": self._text_list(
                    coverage_summary.get("market_channels")
                ),
                "truncation_summary": truncation_summary,
            },
            "report_metrics": dict(report_metrics or {}),
        }

    def _build_event_links(
        self,
        *,
        report_run_id: str,
        selected_events: Sequence[Mapping[str, Any]],
        fallback_version: str | None,
    ) -> list[dict[str, Any]]:
        links: list[dict[str, Any]] = []
        normalized_version = self._text(fallback_version) or "v1"
        for rank, item in enumerate(selected_events, start=1):
            brief_json = self._mapping(item.get("brief_json"))
            event_id = self._text(item.get("event_id")) or self._text(brief_json.get("eventId"))
            if not event_id:
                continue
            render_mode = self._text(item.get("render_mode")) or "full"
            rationale_payload = {
                "event_id": event_id,
                "rank": rank,
                "included": True,
                "state_change": self._text(brief_json.get("stateChange")) or "updated",
                "canonical_title": self._text(brief_json.get("canonicalTitle")),
                "why_it_matters": self._text(brief_json.get("whyItMatters")),
                "total_score": round(self._safe_float(brief_json.get("totalScore")), 3),
                "confidence": round(self._safe_float(brief_json.get("confidence")), 3),
                "regions": self._text_list(brief_json.get("regions")),
                "market_channels": self._text_list(brief_json.get("marketChannels")),
                "assets": self._text_list(brief_json.get("assets")),
                "brief_id": self._text(item.get("brief_id")),
                "brief_version": self._text(item.get("brief_version")) or normalized_version,
                "render_mode": render_mode,
                "selection_reason": (
                    "selected_compact" if render_mode == "compact" else "selected_full"
                ),
                "last_transition": self._mapping(brief_json.get("lastTransition")),
                "evidence_refs": self._text_list(brief_json.get("evidenceRefs")),
                "contradiction_count": len(
                    self._sequence_of_mappings(brief_json.get("contradictions"))
                ),
            }
            links.append(
                {
                    "report_run_id": report_run_id,
                    "event_id": event_id,
                    "rank": rank,
                    "included": True,
                    "rationale": json.dumps(
                        rationale_payload,
                        ensure_ascii=False,
                        sort_keys=True,
                    ),
                }
            )
        return links

    def _build_trace_summary(
        self,
        report_run: Mapping[str, Any],
        event_links: Sequence[Mapping[str, Any]],
    ) -> dict[str, Any]:
        state_counter: Counter[str] = Counter()
        selected_event_ids: list[str] = []

        for link in event_links:
            rationale_json = self._mapping(link.get("rationale_json"))
            event_id = self._text(link.get("event_id"))
            if event_id:
                selected_event_ids.append(event_id)
            state_change = self._text(rationale_json.get("state_change"))
            if state_change:
                state_counter[state_change] += 1

        return {
            "report_run_id": self._text(report_run.get("report_run_id")),
            "profile": self._text(report_run.get("profile")),
            "report_date": self._text(report_run.get("report_date")),
            "selected_event_ids": selected_event_ids,
            "state_change_mix": dict(state_counter),
        }

    def _normalize_link(self, link: Mapping[str, Any]) -> dict[str, Any]:
        normalized = dict(link)
        rationale_json = self._parse_json(self._text(link.get("rationale")))
        if rationale_json:
            normalized["rationale_json"] = rationale_json
        return normalized

    def _resolve_report_date(
        self,
        report: DailyReport,
        report_date: date | None,
    ) -> date:
        if isinstance(report_date, date):
            return report_date
        report_value = self._text(getattr(report, "date", ""))
        try:
            return date.fromisoformat(report_value)
        except ValueError:
            return datetime.now(UTC).date()

    def _report_run_id(self, profile: str, report_date: date) -> str:
        normalized_profile = re.sub(r"[^a-z0-9]+", "_", profile.casefold()).strip("_")
        return f"report_{normalized_profile}_{report_date.isoformat()}"

    def _resolve_source_version(
        self,
        items: Sequence[Mapping[str, Any]],
        field: str,
        *,
        fallback: str,
    ) -> str:
        versions = {
            self._text(item.get(field))
            for item in items
            if self._text(item.get(field))
        }
        if not versions:
            return fallback
        if len(versions) == 1:
            return next(iter(versions))
        return "mixed"

    def _parse_json(self, value: str) -> dict[str, Any]:
        if not value:
            return {}
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return {}
        return dict(parsed) if isinstance(parsed, Mapping) else {}

    def _mapping(self, value: Any) -> dict[str, Any]:
        return dict(value) if isinstance(value, Mapping) else {}

    def _sequence_of_mappings(self, value: Any) -> list[dict[str, Any]]:
        if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
            return []
        return [dict(item) for item in value if isinstance(item, Mapping)]

    def _text(self, value: Any) -> str:
        if value is None:
            return ""
        if isinstance(value, str):
            return value.strip()
        if isinstance(value, date):
            return value.isoformat()
        return str(value).strip()

    def _text_list(self, value: Any) -> list[str]:
        if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
            return []
        items: list[str] = []
        for item in value:
            text = self._text(item)
            if text:
                items.append(text)
        return items

    def _safe_int(self, value: Any, *, fallback: int = 0) -> int:
        try:
            return int(value)
        except (TypeError, ValueError):
            return fallback

    def _safe_float(self, value: Any) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return 0.0


__all__ = ["ReportRunTracker"]
