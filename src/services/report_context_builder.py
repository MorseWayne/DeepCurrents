from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from datetime import date, datetime
import json
from typing import Any, Protocol

from ..utils.logger import get_logger
from .metrics import log_stage_metrics, safe_ratio

logger = get_logger("report-context-builder")

DEFAULT_EVENT_BUDGET_SHARE = 0.65
DEFAULT_THEME_BUDGET_SHARE = 0.20
DEFAULT_MARKET_BUDGET_SHARE = 0.15
MAX_EVENTS_PER_THEME = 2
MAX_EVENTS_PER_REGION = 2
STATE_PRIORITIES = {
    "new": 4,
    "escalated": 3,
    "updated": 2,
    "resolved": 1,
}
PRIMARY_THEME_ORDER = (
    "geopolitics",
    "central_banks",
    "macro_data",
    "energy",
    "commodities",
    "rates_fx",
    "cyber",
)


class EventSummarizerLike(Protocol):
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
    ) -> list[dict[str, Any]]: ...


class ThemeSummarizerLike(Protocol):
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
    ) -> list[dict[str, Any]]: ...


class ReportContextBuilder:
    def __init__(
        self,
        event_summarizer: EventSummarizerLike | None = None,
        theme_summarizer: ThemeSummarizerLike | None = None,
        *,
        event_budget_share: float = DEFAULT_EVENT_BUDGET_SHARE,
        theme_budget_share: float = DEFAULT_THEME_BUDGET_SHARE,
        market_budget_share: float = DEFAULT_MARKET_BUDGET_SHARE,
    ):
        self.event_summarizer = event_summarizer
        self.theme_summarizer = theme_summarizer
        self.event_budget_share = max(event_budget_share, 0.0)
        self.theme_budget_share = max(theme_budget_share, 0.0)
        self.market_budget_share = max(market_budget_share, 0.0)
        self.last_context_metrics: dict[str, Any] = {}

    def build_context(
        self,
        *,
        event_briefs: Sequence[Mapping[str, Any]],
        theme_briefs: Sequence[Mapping[str, Any]],
        market_context: Any = "",
        token_budget: int,
        profile: str = "macro_daily",
    ) -> dict[str, Any]:
        normalized_budget = max(int(token_budget), 0)
        market_text = self._trim_market_context(market_context, normalized_budget)
        market_tokens = estimate_tokens(market_text)

        remaining_after_market = max(0, normalized_budget - market_tokens)
        theme_target = min(
            int(normalized_budget * self.theme_budget_share),
            remaining_after_market,
        )
        event_target = max(0, remaining_after_market - theme_target)

        event_candidates = self._prepare_event_candidates(event_briefs)
        theme_candidates = self._prepare_theme_candidates(theme_briefs)

        (
            selected_events,
            event_overflow,
            event_dropped_ids,
            event_theme_counts,
            event_region_counts,
            event_tokens,
        ) = self._select_event_candidates(event_candidates, budget=event_target)

        (
            selected_themes,
            theme_dropped_keys,
            theme_tokens,
        ) = self._select_theme_candidates(
            theme_candidates,
            budget=theme_target,
            selected_events=selected_events,
        )

        remaining_tokens = max(
            0,
            normalized_budget - market_tokens - event_tokens - theme_tokens,
        )
        if remaining_tokens > 0:
            (
                selected_events,
                event_dropped_ids,
                event_tokens,
            ) = self._expand_event_selection(
                selected_events=selected_events,
                overflow_candidates=event_overflow,
                dropped_event_ids=event_dropped_ids,
                theme_counts=event_theme_counts,
                region_counts=event_region_counts,
                extra_budget=remaining_tokens,
                current_event_tokens=event_tokens,
            )

        prompt_sections = self._build_prompt_sections(
            selected_events=selected_events,
            selected_themes=selected_themes,
            market_text=market_text,
            token_budget=normalized_budget,
        )
        combined_context_text = self._text(prompt_sections.get("combined_context_text"))
        total_tokens = estimate_tokens(combined_context_text)
        hard_cap_hit = False
        if total_tokens > normalized_budget > 0:
            combined_context_text = truncate_to_token_budget(
                combined_context_text,
                normalized_budget,
            )
            prompt_sections["combined_context_text"] = combined_context_text
            total_tokens = estimate_tokens(combined_context_text)
            hard_cap_hit = True

        compressed_event_ids = [
            self._text(item.get("event_id"))
            for item in selected_events
            if self._text(item.get("render_mode")) == "compact"
        ]
        context_package = {
            "profile": profile,
            "token_budget": normalized_budget,
            "selected_event_briefs": selected_events,
            "selected_theme_briefs": selected_themes,
            "market_context": {
                "text": market_text,
                "tokens": market_tokens,
            },
            "budget_summary": {
                "event_budget": event_target,
                "theme_budget": theme_target,
                "market_budget": max(0, normalized_budget - event_target - theme_target),
                "event_tokens": event_tokens,
                "theme_tokens": theme_tokens,
                "market_tokens": market_tokens,
                "total_tokens": total_tokens,
            },
            "coverage_summary": self._build_coverage_summary(
                selected_events,
                selected_themes,
            ),
            "truncation_summary": {
                "dropped_event_ids": sorted(event_dropped_ids),
                "dropped_theme_keys": sorted(theme_dropped_keys),
                "compressed_event_ids": compressed_event_ids,
                "hard_cap_hit": hard_cap_hit,
            },
            "prompt_sections": prompt_sections,
        }
        self.last_context_metrics = self._build_context_metrics(context_package)
        log_stage_metrics(
            logger,
            "context",
            self.last_context_metrics,
            service="ReportContextBuilder.build_context",
        )
        return context_package

    def build_prompt_sections(
        self,
        *,
        event_briefs: Sequence[Mapping[str, Any]],
        theme_briefs: Sequence[Mapping[str, Any]],
        market_context: Any = "",
        token_budget: int,
        profile: str = "macro_daily",
    ) -> dict[str, Any]:
        context = self.build_context(
            event_briefs=event_briefs,
            theme_briefs=theme_briefs,
            market_context=market_context,
            token_budget=token_budget,
            profile=profile,
        )
        return dict(context.get("prompt_sections") or {})

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
        if self.event_summarizer is None or self.theme_summarizer is None:
            raise RuntimeError("ReportContextBuilder requires event and theme summarizers")

        event_briefs = await self.event_summarizer.summarize_ranked_events(
            statuses=statuses,
            since=since,
            profile=profile,
            limit=event_limit,
            evidence_limit=evidence_limit,
            version=version,
        )
        theme_briefs = await self.theme_summarizer.summarize_ranked_themes(
            statuses=statuses,
            since=since,
            profile=profile,
            report_date=report_date,
            event_limit=event_limit,
            max_themes=theme_limit,
            evidence_limit=evidence_limit,
            version=version,
        )
        return self.build_context(
            event_briefs=event_briefs,
            theme_briefs=theme_briefs,
            market_context=market_context,
            token_budget=token_budget,
            profile=profile,
        )

    def _prepare_event_candidates(
        self,
        event_briefs: Sequence[Mapping[str, Any]],
    ) -> list[dict[str, Any]]:
        candidates: list[dict[str, Any]] = []
        for row in event_briefs:
            brief_json = self._brief_json(row)
            event_id = self._text(brief_json.get("eventId"))
            if not event_id:
                continue
            primary_theme = self._primary_event_theme(brief_json)
            primary_region = self._first_text(brief_json.get("regions"))
            full_text = self._render_event_brief(brief_json, mode="full")
            compact_text = self._render_event_brief(brief_json, mode="compact")
            contradictions = self._sequence_of_mappings(brief_json.get("contradictions"))
            candidates.append(
                {
                    "event_id": event_id,
                    "brief_json": brief_json,
                    "primary_theme": primary_theme,
                    "primary_region": primary_region,
                    "full_text": full_text,
                    "compact_text": compact_text,
                    "full_tokens": estimate_tokens(full_text),
                    "compact_tokens": estimate_tokens(compact_text),
                    "state_priority": STATE_PRIORITIES.get(
                        self._text(brief_json.get("stateChange")),
                        0,
                    ),
                    "total_score": self._safe_float(brief_json.get("totalScore")),
                    "confidence": self._safe_float(brief_json.get("confidence")),
                    "contradiction_count": len(contradictions),
                }
            )

        candidates.sort(
            key=lambda item: (
                -self._safe_int(item.get("state_priority")),
                -self._safe_float(item.get("total_score")),
                -self._safe_float(item.get("confidence")),
                -self._safe_int(item.get("contradiction_count")),
                self._text(item.get("event_id")),
            )
        )
        return candidates

    def _prepare_theme_candidates(
        self,
        theme_briefs: Sequence[Mapping[str, Any]],
    ) -> list[dict[str, Any]]:
        candidates: list[dict[str, Any]] = []
        for row in theme_briefs:
            brief_json = self._brief_json(row)
            theme_key = self._text(brief_json.get("themeKey"))
            if not theme_key:
                theme_key = self._text(self._mapping(row).get("theme_key"))
            if not theme_key:
                continue
            text = self._render_theme_brief(brief_json)
            bucket_type = self._text(brief_json.get("bucketType")) or (
                "region" if theme_key.startswith("region:") else "taxonomy"
            )
            candidates.append(
                {
                    "theme_key": theme_key,
                    "brief_json": brief_json,
                    "text": text,
                    "tokens": estimate_tokens(text),
                    "bucket_type": bucket_type,
                    "theme_score": self._safe_float(brief_json.get("themeScore")),
                    "event_count": self._safe_int(brief_json.get("eventCount")),
                }
            )

        candidates.sort(
            key=lambda item: (
                1 if self._text(item.get("bucket_type")) == "region" else 0,
                -self._safe_float(item.get("theme_score")),
                -self._safe_int(item.get("event_count")),
                self._text(item.get("theme_key")),
            )
        )
        return candidates

    def _select_event_candidates(
        self,
        candidates: Sequence[Mapping[str, Any]],
        *,
        budget: int,
    ) -> tuple[
        list[dict[str, Any]],
        list[dict[str, Any]],
        set[str],
        Counter[str],
        Counter[str],
        int,
    ]:
        selected: list[dict[str, Any]] = []
        overflow: list[dict[str, Any]] = []
        dropped_ids: set[str] = set()
        theme_counts: Counter[str] = Counter()
        region_counts: Counter[str] = Counter()
        used = 0

        for candidate in candidates:
            event_id = self._text(candidate.get("event_id"))
            primary_theme = self._text(candidate.get("primary_theme"))
            primary_region = self._text(candidate.get("primary_region"))

            if primary_theme and theme_counts[primary_theme] >= MAX_EVENTS_PER_THEME:
                dropped_ids.add(event_id)
                continue
            if primary_region and region_counts[primary_region] >= MAX_EVENTS_PER_REGION:
                dropped_ids.add(event_id)
                continue

            full_tokens = self._safe_int(candidate.get("full_tokens"))
            compact_tokens = self._safe_int(candidate.get("compact_tokens"))
            render_mode = ""
            token_count = 0
            text = ""

            if used + full_tokens <= budget:
                render_mode = "full"
                token_count = full_tokens
                text = self._text(candidate.get("full_text"))
            elif used + compact_tokens <= budget:
                render_mode = "compact"
                token_count = compact_tokens
                text = self._text(candidate.get("compact_text"))
            else:
                overflow.append(dict(candidate))
                dropped_ids.add(event_id)
                continue

            selected.append(
                {
                    "event_id": event_id,
                    "render_mode": render_mode,
                    "token_count": token_count,
                    "primary_theme": primary_theme,
                    "primary_region": primary_region,
                    "text": text,
                    "brief_json": self._mapping(candidate.get("brief_json")),
                }
            )
            used += token_count
            if primary_theme:
                theme_counts[primary_theme] += 1
            if primary_region:
                region_counts[primary_region] += 1

        return selected, overflow, dropped_ids, theme_counts, region_counts, used

    def _select_theme_candidates(
        self,
        candidates: Sequence[Mapping[str, Any]],
        *,
        budget: int,
        selected_events: Sequence[Mapping[str, Any]],
    ) -> tuple[list[dict[str, Any]], set[str], int]:
        selected: list[dict[str, Any]] = []
        dropped_keys: set[str] = set()
        used = 0
        covered_regions = set(self._collect_regions(selected_events))
        covered_channels = set(self._collect_channels(selected_events))

        for candidate in candidates:
            theme_key = self._text(candidate.get("theme_key"))
            bucket_type = self._text(candidate.get("bucket_type"))
            tokens = self._safe_int(candidate.get("tokens"))
            brief_json = self._mapping(candidate.get("brief_json"))
            regions = {
                region.casefold()
                for region in self._text_list(brief_json.get("regions"))
            }
            channels = {
                channel.casefold()
                for channel in self._text_list(brief_json.get("marketChannels"))
            }

            if bucket_type == "region" and not (
                regions - covered_regions or channels - covered_channels
            ):
                dropped_keys.add(theme_key)
                continue

            if used + tokens > budget:
                dropped_keys.add(theme_key)
                continue

            selected.append(
                {
                    "theme_key": theme_key,
                    "token_count": tokens,
                    "text": self._text(candidate.get("text")),
                    "brief_json": brief_json,
                }
            )
            used += tokens
            covered_regions |= regions
            covered_channels |= channels

        return selected, dropped_keys, used

    def _expand_event_selection(
        self,
        *,
        selected_events: list[dict[str, Any]],
        overflow_candidates: Sequence[Mapping[str, Any]],
        dropped_event_ids: set[str],
        theme_counts: Counter[str],
        region_counts: Counter[str],
        extra_budget: int,
        current_event_tokens: int,
    ) -> tuple[list[dict[str, Any]], set[str], int]:
        remaining = max(extra_budget, 0)
        used = current_event_tokens

        for item in selected_events:
            if self._text(item.get("render_mode")) != "compact":
                continue
            brief_json = self._mapping(item.get("brief_json"))
            full_text = self._render_event_brief(brief_json, mode="full")
            full_tokens = estimate_tokens(full_text)
            delta = max(0, full_tokens - self._safe_int(item.get("token_count")))
            if delta > remaining:
                continue
            item["render_mode"] = "full"
            item["text"] = full_text
            item["token_count"] = full_tokens
            remaining -= delta
            used += delta

        for candidate in overflow_candidates:
            if remaining <= 0:
                break
            event_id = self._text(candidate.get("event_id"))
            primary_theme = self._text(candidate.get("primary_theme"))
            primary_region = self._text(candidate.get("primary_region"))
            if primary_theme and theme_counts[primary_theme] >= MAX_EVENTS_PER_THEME:
                continue
            if primary_region and region_counts[primary_region] >= MAX_EVENTS_PER_REGION:
                continue

            full_tokens = self._safe_int(candidate.get("full_tokens"))
            compact_tokens = self._safe_int(candidate.get("compact_tokens"))
            render_mode = ""
            token_count = 0
            text = ""

            if full_tokens <= remaining:
                render_mode = "full"
                token_count = full_tokens
                text = self._text(candidate.get("full_text"))
            elif compact_tokens <= remaining:
                render_mode = "compact"
                token_count = compact_tokens
                text = self._text(candidate.get("compact_text"))
            else:
                continue

            selected_events.append(
                {
                    "event_id": event_id,
                    "render_mode": render_mode,
                    "token_count": token_count,
                    "primary_theme": primary_theme,
                    "primary_region": primary_region,
                    "text": text,
                    "brief_json": self._mapping(candidate.get("brief_json")),
                }
            )
            remaining -= token_count
            used += token_count
            dropped_event_ids.discard(event_id)
            if primary_theme:
                theme_counts[primary_theme] += 1
            if primary_region:
                region_counts[primary_region] += 1

        return selected_events, dropped_event_ids, used

    def _build_prompt_sections(
        self,
        *,
        selected_events: Sequence[Mapping[str, Any]],
        selected_themes: Sequence[Mapping[str, Any]],
        market_text: str,
        token_budget: int,
    ) -> dict[str, Any]:
        event_body = "\n".join(
            self._text(item.get("text"))
            for item in selected_events
            if self._text(item.get("text"))
        )
        theme_body = "\n".join(
            self._text(item.get("text"))
            for item in selected_themes
            if self._text(item.get("text"))
        )
        event_text = self._section_text("EVENT BRIEFS", event_body)
        theme_text = self._section_text("THEME BRIEFS", theme_body)
        market_block = self._section_text("MARKET CONTEXT", market_text)
        combined = "\n\n".join(
            section for section in (event_text, theme_text, market_block) if section
        )
        if estimate_tokens(combined) > token_budget > 0:
            combined = truncate_to_token_budget(combined, token_budget)
        return {
            "event_briefs_text": event_text,
            "theme_briefs_text": theme_text,
            "market_context_text": market_block,
            "combined_context_text": combined,
        }

    def _build_coverage_summary(
        self,
        selected_events: Sequence[Mapping[str, Any]],
        selected_themes: Sequence[Mapping[str, Any]],
    ) -> dict[str, Any]:
        theme_keys: list[str] = []
        seen_theme_keys: set[str] = set()
        for item in selected_themes:
            brief_json = self._mapping(item.get("brief_json"))
            theme_key = self._text(brief_json.get("themeKey")) or self._text(
                item.get("theme_key")
            )
            if theme_key and theme_key not in seen_theme_keys:
                theme_keys.append(theme_key)
                seen_theme_keys.add(theme_key)
        return {
            "event_count": len(selected_events),
            "theme_count": len(selected_themes),
            "theme_keys": theme_keys,
            "regions": sorted(self._collect_regions(selected_events, selected_themes)),
            "market_channels": sorted(
                self._collect_channels(selected_events, selected_themes)
            ),
        }

    def _build_context_metrics(
        self,
        context_package: Mapping[str, Any],
    ) -> dict[str, Any]:
        selected_events = self._sequence_of_mappings(
            context_package.get("selected_event_briefs")
        )
        selected_themes = self._sequence_of_mappings(
            context_package.get("selected_theme_briefs")
        )
        budget_summary = self._mapping(context_package.get("budget_summary"))
        truncation_summary = self._mapping(context_package.get("truncation_summary"))
        return {
            "profile": self._text(context_package.get("profile")),
            "token_budget": self._safe_int(context_package.get("token_budget")),
            "events_selected": len(selected_events),
            "themes_selected": len(selected_themes),
            "compressed_event_ratio": safe_ratio(
                len(self._text_list(truncation_summary.get("compressed_event_ids"))),
                len(selected_events),
            ),
            "budget_utilization": safe_ratio(
                self._safe_int(budget_summary.get("total_tokens")),
                self._safe_int(context_package.get("token_budget")),
            ),
            "hard_cap_hit": bool(truncation_summary.get("hard_cap_hit")),
        }

    def _trim_market_context(self, market_context: Any, token_budget: int) -> str:
        text = self._render_market_context(market_context)
        if not text or token_budget <= 0:
            return ""
        target_budget = min(
            max(int(token_budget * self.market_budget_share), 0),
            token_budget,
        )
        if target_budget <= 0:
            return ""
        return truncate_to_token_budget(text, target_budget)

    def _render_event_brief(self, brief_json: Mapping[str, Any], *, mode: str) -> str:
        title = self._text(brief_json.get("canonicalTitle"))
        event_id = self._text(brief_json.get("eventId"))
        state = self._text(brief_json.get("stateChange"))
        why = self._text(brief_json.get("whyItMatters"))
        score = round(self._safe_float(brief_json.get("totalScore")), 3)
        confidence = round(self._safe_float(brief_json.get("confidence")), 3)
        header = (
            f"- [{event_id}] {title} | state={state} | score={score:.3f} | confidence={confidence:.3f}"
        )
        if mode == "compact":
            return "\n".join(part for part in (header, f"  Why: {why}") if part.strip())

        facts = "; ".join(self._text_list(brief_json.get("coreFacts"))[:3])
        channels = ", ".join(self._text_list(brief_json.get("marketChannels"))[:3])
        regions = ", ".join(self._text_list(brief_json.get("regions"))[:3])
        assets = ", ".join(self._text_list(brief_json.get("assets"))[:3])
        contradictions = self._sequence_of_mappings(brief_json.get("contradictions"))
        scope_parts = [
            f"channels={channels}" if channels else "",
            f"regions={regions}" if regions else "",
            f"assets={assets}" if assets else "",
        ]
        lines = [
            header,
            f"  Why: {why}" if why else "",
            f"  Facts: {facts}" if facts else "",
            "  Scope: " + " | ".join(part for part in scope_parts if part)
            if any(scope_parts)
            else "",
            f"  Contradictions: {len(contradictions)}" if contradictions else "",
        ]
        return "\n".join(line for line in lines if line)

    def _render_theme_brief(self, brief_json: Mapping[str, Any]) -> str:
        display_name = self._text(brief_json.get("displayName"))
        theme_key = self._text(brief_json.get("themeKey"))
        summary = self._text(brief_json.get("summary"))
        threads = "; ".join(self._text_list(brief_json.get("coreThreads"))[:3])
        top_events = ", ".join(self._text_list(brief_json.get("eventRefs"))[:4])
        theme_score = round(self._safe_float(brief_json.get("themeScore")), 3)
        event_count = self._safe_int(brief_json.get("eventCount"))
        lines = [
            f"- [{theme_key}] {display_name} | score={theme_score:.3f} | events={event_count}",
            f"  Summary: {summary}" if summary else "",
            f"  Threads: {threads}" if threads else "",
            f"  Top events: {top_events}" if top_events else "",
        ]
        return "\n".join(line for line in lines if line)

    def _render_market_context(self, market_context: Any) -> str:
        if market_context is None:
            return ""
        if isinstance(market_context, str):
            return market_context.strip()
        if isinstance(market_context, Mapping):
            lines = []
            for key, value in market_context.items():
                if isinstance(value, Mapping):
                    value_text = json.dumps(dict(value), ensure_ascii=True, sort_keys=True)
                elif isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
                    value_text = ", ".join(self._text_list(value))
                else:
                    value_text = self._text(value)
                lines.append(f"- {self._text(key)}: {value_text}")
            return "\n".join(line for line in lines if line.strip())
        if isinstance(market_context, Sequence) and not isinstance(
            market_context,
            (str, bytes),
        ):
            return "\n".join(f"- {self._text(item)}" for item in market_context if self._text(item))
        return self._text(market_context)

    def _primary_event_theme(self, brief_json: Mapping[str, Any]) -> str:
        event_type = self._text(brief_json.get("eventType")).casefold()
        channels = {
            item.casefold()
            for item in self._text_list(brief_json.get("marketChannels"))
        }
        text = " ".join(
            [
                self._text(brief_json.get("canonicalTitle")),
                self._text(brief_json.get("whyItMatters")),
                *channels,
            ]
        ).casefold()
        theme_hits: list[str] = []
        if event_type in {"conflict", "policy", "supply_disruption"} or "shipping" in channels:
            theme_hits.append("geopolitics")
        if event_type == "central_bank":
            theme_hits.append("central_banks")
        if event_type == "macro_data":
            theme_hits.append("macro_data")
        if "energy" in channels or any(
            marker in text for marker in ("brent", "wti", "oil", "gas", "pipeline", "refinery")
        ):
            theme_hits.append("energy")
        if "commodities" in channels or any(
            marker in text for marker in ("gold", "copper", "commodity", "wti", "brent")
        ):
            theme_hits.append("commodities")
        if {"rates", "fx"} & channels or event_type == "central_bank":
            theme_hits.append("rates_fx")
        if event_type == "cyber" or any(
            marker in text for marker in ("cyber", "hack", "breach", "malware", "ransomware")
        ):
            theme_hits.append("cyber")
        for theme_key in PRIMARY_THEME_ORDER:
            if theme_key in theme_hits:
                return theme_key
        return ""

    def _brief_json(self, row: Mapping[str, Any]) -> dict[str, Any]:
        data = self._mapping(row)
        brief_json = self._mapping(data.get("brief_json"))
        return brief_json if brief_json else data

    def _section_text(self, label: str, body: str) -> str:
        normalized_body = body.strip()
        if not normalized_body:
            return ""
        return f"[{label}]\n{normalized_body}"

    def _collect_regions(self, *groups: Sequence[Mapping[str, Any]]) -> set[str]:
        regions: set[str] = set()
        for group in groups:
            for item in group:
                brief_json = self._brief_json(item)
                for region in self._text_list(brief_json.get("regions"))[:4]:
                    if region:
                        regions.add(region.casefold())
        return regions

    def _collect_channels(self, *groups: Sequence[Mapping[str, Any]]) -> set[str]:
        channels: set[str] = set()
        for group in groups:
            for item in group:
                brief_json = self._brief_json(item)
                for channel in self._text_list(brief_json.get("marketChannels"))[:4]:
                    if channel:
                        channels.add(channel.casefold())
        return channels

    def _mapping(self, value: Any) -> dict[str, Any]:
        return dict(value) if isinstance(value, Mapping) else {}

    def _sequence_of_mappings(self, value: Any) -> list[dict[str, Any]]:
        if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
            return []
        return [dict(item) for item in value if isinstance(item, Mapping)]

    def _text_list(self, value: Any) -> list[str]:
        if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
            return []
        return [self._text(item) for item in value if self._text(item)]

    def _first_text(self, value: Any) -> str:
        items = self._text_list(value)
        return items[0] if items else ""

    @staticmethod
    def _safe_int(value: Any) -> int:
        try:
            return int(value)
        except (TypeError, ValueError):
            return 0

    @staticmethod
    def _safe_float(value: Any) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return 0.0

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


__all__ = [
    "ReportContextBuilder",
    "estimate_tokens",
    "truncate_to_token_budget",
]
