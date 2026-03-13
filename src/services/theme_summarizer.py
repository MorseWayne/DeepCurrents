from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from datetime import UTC, date, datetime
import re
from typing import Any, Protocol

from ..utils.logger import get_logger
from .metrics import log_stage_metrics, mean_float, safe_ratio

logger = get_logger("theme-summarizer")

THEME_LABELS = {
    "geopolitics": "Geopolitics",
    "central_banks": "Central Banks",
    "macro_data": "Macro Data",
    "energy": "Energy",
    "cyber": "Cyber",
    "commodities": "Commodities",
    "rates_fx": "Rates / FX",
}

THEME_PRIORITIES = {
    "geopolitics": 70,
    "central_banks": 65,
    "macro_data": 60,
    "energy": 55,
    "commodities": 50,
    "rates_fx": 45,
    "cyber": 40,
}

GEOPOLITICS_EVENT_TYPES = {"conflict", "policy", "supply_disruption"}
ENERGY_MARKERS = {
    "brent",
    "wti",
    "oil",
    "gas",
    "lng",
    "refinery",
    "pipeline",
    "diesel",
    "power",
}
COMMODITY_MARKERS = {
    "brent",
    "wti",
    "oil",
    "gas",
    "gold",
    "silver",
    "copper",
    "iron ore",
    "commodity",
}
CYBER_MARKERS = {
    "cyber",
    "ransomware",
    "malware",
    "hack",
    "hacker",
    "breach",
}
TOP_EVENT_LIMIT = 4


class BriefRepositoryLike(Protocol):
    async def upsert_theme_brief(self, brief: Mapping[str, Any]) -> dict[str, Any]: ...


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


class ThemeSummarizer:
    def __init__(
        self,
        brief_repository: BriefRepositoryLike,
        event_summarizer: EventSummarizerLike,
        *,
        version: str = "v1",
    ):
        self.brief_repository = brief_repository
        self.event_summarizer = event_summarizer
        self.version = version
        self.last_theme_metrics: dict[str, Any] = {}

    async def summarize_theme(
        self,
        theme_key: str,
        *,
        statuses: Sequence[str] | None = None,
        since: datetime | None = None,
        profile: str = "macro_daily",
        report_date: date | None = None,
        event_limit: int = 20,
        evidence_limit: int = 4,
        version: str | None = None,
    ) -> dict[str, Any]:
        normalized_key = self._normalize_theme_key(theme_key)
        event_briefs = await self._load_event_briefs(
            statuses=statuses,
            since=since,
            profile=profile,
            event_limit=event_limit,
            evidence_limit=evidence_limit,
            version=version,
        )
        groups = self._group_event_briefs(event_briefs)
        selected = groups.get(normalized_key, [])
        if not selected:
            raise ValueError(f"theme not found or empty: {normalized_key}")

        stored = await self._persist_theme_brief(
            theme_key=normalized_key,
            event_briefs=selected,
            report_date=report_date or self._today(),
            profile=profile,
            version=version or self.version,
        )
        self.last_theme_metrics = self._build_theme_metrics(
            [stored],
            events_considered=len(event_briefs),
            profile=profile,
        )
        log_stage_metrics(
            logger,
            "theme_brief",
            self.last_theme_metrics,
            service="ThemeSummarizer.summarize_theme",
        )
        return stored

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
        event_briefs = await self._load_event_briefs(
            statuses=statuses,
            since=since,
            profile=profile,
            event_limit=event_limit,
            evidence_limit=evidence_limit,
            version=version,
        )
        ordered_groups = self._ordered_theme_groups(self._group_event_briefs(event_briefs))
        stored_briefs: list[dict[str, Any]] = []

        for theme_key, grouped_briefs in ordered_groups[: max(max_themes, 0)]:
            stored_briefs.append(
                await self._persist_theme_brief(
                    theme_key=theme_key,
                    event_briefs=grouped_briefs,
                    report_date=report_date or self._today(),
                    profile=profile,
                    version=version or self.version,
                )
            )

        self.last_theme_metrics = self._build_theme_metrics(
            stored_briefs,
            events_considered=len(event_briefs),
            profile=profile,
        )
        log_stage_metrics(
            logger,
            "theme_brief",
            self.last_theme_metrics,
            service="ThemeSummarizer.summarize_ranked_themes",
        )
        return stored_briefs

    async def _load_event_briefs(
        self,
        *,
        statuses: Sequence[str] | None,
        since: datetime | None,
        profile: str,
        event_limit: int,
        evidence_limit: int,
        version: str | None,
    ) -> list[dict[str, Any]]:
        return await self.event_summarizer.summarize_ranked_events(
            statuses=statuses,
            since=since,
            profile=profile,
            limit=event_limit,
            evidence_limit=evidence_limit,
            version=version,
        )

    async def _persist_theme_brief(
        self,
        *,
        theme_key: str,
        event_briefs: Sequence[Mapping[str, Any]],
        report_date: date,
        profile: str,
        version: str,
    ) -> dict[str, Any]:
        brief_json = self._build_theme_brief_json(
            theme_key=theme_key,
            event_briefs=event_briefs,
            profile=profile,
            report_date=report_date,
        )
        return await self.brief_repository.upsert_theme_brief(
            {
                "theme_brief_id": self._build_theme_brief_id(
                    theme_key,
                    report_date,
                    version,
                ),
                "theme_key": theme_key,
                "report_date": report_date,
                "version": version,
                "brief_json": brief_json,
            }
        )

    def _group_event_briefs(
        self,
        event_briefs: Sequence[Mapping[str, Any]],
    ) -> dict[str, list[dict[str, Any]]]:
        prepared: list[dict[str, Any]] = []
        region_counts: Counter[str] = Counter()
        seen_events_by_region: dict[str, set[str]] = defaultdict(set)

        for row in event_briefs:
            brief = self._mapping(row)
            brief_json = self._mapping(brief.get("brief_json"))
            event_id = self._text(brief_json.get("eventId"))
            if not event_id or not brief_json:
                continue

            primary_region = self._primary_region(brief_json)
            if primary_region and event_id not in seen_events_by_region[primary_region]:
                seen_events_by_region[primary_region].add(event_id)
                region_counts[primary_region] += 1

            prepared.append(
                {
                    "row": brief,
                    "brief_json": brief_json,
                    "theme_keys": self._theme_keys_for_brief(brief_json),
                    "primary_region": primary_region,
                    "event_id": event_id,
                }
            )

        groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
        seen_event_ids: dict[str, set[str]] = defaultdict(set)
        for item in prepared:
            event_id = self._text(item.get("event_id"))
            for theme_key in item.get("theme_keys", []):
                if event_id in seen_event_ids[theme_key]:
                    continue
                seen_event_ids[theme_key].add(event_id)
                groups[theme_key].append(dict(item["row"]))

            primary_region = self._text(item.get("primary_region"))
            if primary_region and region_counts[primary_region] >= 2:
                region_key = f"region:{self._slug(primary_region)}"
                if event_id not in seen_event_ids[region_key]:
                    seen_event_ids[region_key].add(event_id)
                    groups[region_key].append(dict(item["row"]))

        return dict(groups)

    def _ordered_theme_groups(
        self,
        groups: Mapping[str, Sequence[Mapping[str, Any]]],
    ) -> list[tuple[str, list[dict[str, Any]]]]:
        ranked: list[tuple[str, list[dict[str, Any]], float]] = []
        for theme_key, items in groups.items():
            normalized_items = [dict(item) for item in items if isinstance(item, Mapping)]
            if not normalized_items:
                continue
            ranked.append(
                (theme_key, normalized_items, self._theme_score(normalized_items))
            )

        ranked.sort(
            key=lambda item: (
                -item[2],
                -len(item[1]),
                -self._theme_priority(item[0]),
                item[0],
            )
        )
        return [(theme_key, items) for theme_key, items, _ in ranked]

    def _build_theme_brief_json(
        self,
        *,
        theme_key: str,
        event_briefs: Sequence[Mapping[str, Any]],
        profile: str,
        report_date: date,
    ) -> dict[str, Any]:
        ranked_briefs = sorted(
            [self._mapping(item) for item in event_briefs if isinstance(item, Mapping)],
            key=lambda item: (
                -self._safe_float(self._mapping(item.get("brief_json")).get("totalScore")),
                self._text(self._mapping(item.get("brief_json")).get("eventId")),
            ),
        )
        brief_jsons = [self._mapping(item.get("brief_json")) for item in ranked_briefs]
        label = self._display_name(theme_key)
        bucket_type = "region" if theme_key.startswith("region:") else "taxonomy"
        top_events = [self._top_event(item) for item in brief_jsons[:TOP_EVENT_LIMIT]]
        event_refs = [self._text(item.get("eventId")) for item in brief_jsons if self._text(item.get("eventId"))]

        region_names = self._top_names(brief_jsons, "regions", limit=5)
        channel_names = self._top_names(brief_jsons, "marketChannels", limit=5)
        asset_names = self._top_names(brief_jsons, "assets", limit=5)

        state_counter = Counter(
            self._text(item.get("stateChange")) or "updated"
            for item in brief_jsons
        )
        contradiction_count = sum(
            1
            for item in brief_jsons
            if self._sequence_of_mappings(item.get("contradictions"))
        )
        theme_score = self._theme_score(ranked_briefs)
        avg_confidence = mean_float(
            [
                self._safe_float(item.get("confidence"))
                for item in brief_jsons
            ]
        )

        return {
            "themeKey": theme_key,
            "displayName": label,
            "bucketType": bucket_type,
            "reportDate": report_date.isoformat(),
            "profile": profile,
            "summary": self._build_summary(
                label=label,
                brief_jsons=brief_jsons,
                channels=channel_names,
                regions=region_names,
            ),
            "coreThreads": self._build_core_threads(
                label=label,
                brief_jsons=brief_jsons,
                channels=channel_names,
                regions=region_names,
                assets=asset_names,
                contradiction_count=contradiction_count,
                state_counter=state_counter,
            ),
            "whyItMatters": self._build_why_it_matters(
                label=label,
                channels=channel_names,
                regions=region_names,
                state_counter=state_counter,
                contradiction_count=contradiction_count,
                avg_confidence=avg_confidence,
            ),
            "eventRefs": event_refs,
            "topEvents": top_events,
            "regions": region_names,
            "marketChannels": channel_names,
            "assets": asset_names,
            "stateMix": {
                state: count
                for state, count in sorted(state_counter.items())
            },
            "eventCount": len(brief_jsons),
            "contradictionEventCount": contradiction_count,
            "avgConfidence": avg_confidence,
            "themeScore": theme_score,
            "generatedAt": datetime.now(UTC).isoformat(),
        }

    def _build_summary(
        self,
        *,
        label: str,
        brief_jsons: Sequence[Mapping[str, Any]],
        channels: Sequence[str],
        regions: Sequence[str],
    ) -> str:
        event_count = len(brief_jsons)
        titles = [
            self._text(item.get("canonicalTitle"))
            for item in brief_jsons[:2]
            if self._text(item.get("canonicalTitle"))
        ]
        channels_text = ", ".join(channels[:3]) if channels else "cross-asset sentiment"
        regions_text = ", ".join(regions[:3]) if regions else "multiple regions"
        lead_text = ", led by " + " and ".join(titles) if titles else ""
        return (
            f"{label} theme is driven by {event_count} events{lead_text}, "
            f"with pressure centered on {channels_text} across {regions_text}."
        )

    def _build_core_threads(
        self,
        *,
        label: str,
        brief_jsons: Sequence[Mapping[str, Any]],
        channels: Sequence[str],
        regions: Sequence[str],
        assets: Sequence[str],
        contradiction_count: int,
        state_counter: Counter[str],
    ) -> list[str]:
        threads: list[str] = []
        hot_count = state_counter.get("new", 0) + state_counter.get("escalated", 0)
        if hot_count > 0:
            threads.append(
                f"{hot_count} events are new or escalated inside the {label.lower()} theme."
            )

        titles = [
            self._text(item.get("canonicalTitle"))
            for item in brief_jsons[:2]
            if self._text(item.get("canonicalTitle"))
        ]
        if titles:
            threads.append("Lead developments: " + "; ".join(titles[:2]) + ".")
        if channels or regions:
            scope_parts: list[str] = []
            if channels:
                scope_parts.append("channels " + ", ".join(channels[:3]))
            if regions:
                scope_parts.append("regions " + ", ".join(regions[:3]))
            threads.append("Main transmission runs through " + " and ".join(scope_parts) + ".")
        if assets:
            threads.append("Key assets in focus: " + ", ".join(assets[:3]) + ".")
        if contradiction_count > 0:
            threads.append(
                f"Contradictory reporting remains active in {contradiction_count} related events."
            )

        deduped: list[str] = []
        seen = set()
        for thread in threads:
            normalized = thread.casefold()
            if not thread or normalized in seen:
                continue
            seen.add(normalized)
            deduped.append(thread)
        return deduped[:4]

    def _build_why_it_matters(
        self,
        *,
        label: str,
        channels: Sequence[str],
        regions: Sequence[str],
        state_counter: Counter[str],
        contradiction_count: int,
        avg_confidence: float,
    ) -> str:
        channels_text = ", ".join(channels[:3]) if channels else "cross-asset pricing"
        regions_text = ", ".join(regions[:2]) if regions else "global risk sentiment"
        active_count = (
            state_counter.get("new", 0)
            + state_counter.get("updated", 0)
            + state_counter.get("escalated", 0)
        )
        contradiction_text = (
            f" Contradictory coverage persists in {contradiction_count} events."
            if contradiction_count
            else ""
        )
        return (
            f"{label} matters for {channels_text} because {active_count} active developments "
            f"are still shaping expectations across {regions_text}, with average confidence "
            f"{avg_confidence:.2f}.{contradiction_text}"
        )

    def _theme_keys_for_brief(self, brief_json: Mapping[str, Any]) -> list[str]:
        event_type = self._text(brief_json.get("eventType")).casefold()
        channels = {
            item.casefold()
            for item in self._text_list(brief_json.get("marketChannels"))
        }
        assets = {
            item.casefold()
            for item in self._text_list(brief_json.get("assets"))
        }
        text = " ".join(
            [
                self._text(brief_json.get("canonicalTitle")),
                self._text(brief_json.get("whyItMatters")),
                *self._text_list(brief_json.get("coreFacts")),
                *channels,
                *assets,
            ]
        ).casefold()

        themes: list[str] = []
        if event_type in GEOPOLITICS_EVENT_TYPES or "shipping" in channels:
            themes.append("geopolitics")
        if event_type == "central_bank":
            themes.append("central_banks")
        if event_type == "macro_data":
            themes.append("macro_data")
        if "energy" in channels or self._contains_marker(text, assets, ENERGY_MARKERS):
            themes.append("energy")
        if "commodities" in channels or self._contains_marker(
            text,
            assets,
            COMMODITY_MARKERS,
        ):
            themes.append("commodities")
        if {"rates", "fx"} & channels or event_type == "central_bank":
            themes.append("rates_fx")
        if event_type == "cyber" or self._contains_marker(text, assets, CYBER_MARKERS):
            themes.append("cyber")
        return list(dict.fromkeys(themes))

    def _build_theme_metrics(
        self,
        briefs: Sequence[Mapping[str, Any]],
        *,
        events_considered: int,
        profile: str,
    ) -> dict[str, Any]:
        brief_jsons = [
            self._mapping(brief.get("brief_json"))
            for brief in briefs
            if isinstance(brief, Mapping)
        ]
        theme_scores = [
            self._safe_float(item.get("themeScore"))
            for item in brief_jsons
        ]
        event_counts = [
            self._safe_int(item.get("eventCount"))
            for item in brief_jsons
        ]
        region_theme_count = sum(
            1 for item in brief_jsons if self._text(item.get("bucketType")) == "region"
        )
        contradiction_theme_count = sum(
            1 for item in brief_jsons if self._safe_int(item.get("contradictionEventCount")) > 0
        )
        multi_event_theme_count = sum(
            1 for item in brief_jsons if self._safe_int(item.get("eventCount")) > 1
        )
        total = len(brief_jsons)
        return {
            "profile": profile,
            "events_considered": max(events_considered, 0),
            "themes_generated": total,
            "avg_theme_score": mean_float(theme_scores),
            "avg_events_per_theme": mean_float(event_counts),
            "region_theme_ratio": safe_ratio(region_theme_count, total),
            "contradiction_theme_ratio": safe_ratio(contradiction_theme_count, total),
            "multi_event_theme_ratio": safe_ratio(multi_event_theme_count, total),
        }

    def _top_event(self, brief_json: Mapping[str, Any]) -> dict[str, Any]:
        contradictions = self._sequence_of_mappings(brief_json.get("contradictions"))
        return {
            "eventId": self._text(brief_json.get("eventId")),
            "canonicalTitle": self._text(brief_json.get("canonicalTitle")),
            "stateChange": self._text(brief_json.get("stateChange")),
            "totalScore": round(self._safe_float(brief_json.get("totalScore")), 3),
            "confidence": round(self._safe_float(brief_json.get("confidence")), 3),
            "regions": self._text_list(brief_json.get("regions"))[:3],
            "marketChannels": self._text_list(brief_json.get("marketChannels"))[:3],
            "contradictionCount": len(contradictions),
        }

    def _top_names(
        self,
        brief_jsons: Sequence[Mapping[str, Any]],
        field: str,
        *,
        limit: int,
    ) -> list[str]:
        counter: Counter[str] = Counter()
        first_seen: dict[str, int] = {}
        next_position = 0
        for brief_json in brief_jsons:
            seen_for_brief: set[str] = set()
            for item in self._text_list(brief_json.get(field)):
                normalized = item.casefold()
                if normalized in seen_for_brief:
                    continue
                seen_for_brief.add(normalized)
                counter[item] += 1
                if item not in first_seen:
                    first_seen[item] = next_position
                    next_position += 1
        ordered = sorted(
            counter.items(),
            key=lambda item: (-item[1], first_seen.get(item[0], 0), item[0]),
        )
        return [name for name, _ in ordered[:limit]]

    def _theme_score(self, event_briefs: Sequence[Mapping[str, Any]]) -> float:
        weights = (1.0, 0.7, 0.5, 0.3)
        total = 0.0
        denominator = 0.0
        ranked = sorted(
            [
                self._safe_float(self._mapping(item.get("brief_json")).get("totalScore"))
                for item in event_briefs
                if isinstance(item, Mapping)
            ],
            reverse=True,
        )
        for index, score in enumerate(ranked[: len(weights)]):
            weight = weights[index]
            total += score * weight
            denominator += weight
        if denominator == 0:
            return 0.0
        return round(total / denominator, 4)

    def _primary_region(self, brief_json: Mapping[str, Any]) -> str:
        regions = self._text_list(brief_json.get("regions"))
        return regions[0] if regions else ""

    def _display_name(self, theme_key: str) -> str:
        normalized = self._normalize_theme_key(theme_key)
        if normalized.startswith("region:"):
            region_name = normalized.split(":", 1)[1].replace("_", " ").strip()
            return "Region: " + region_name.title()
        return THEME_LABELS.get(normalized, normalized.replace("_", " ").title())

    def _theme_priority(self, theme_key: str) -> int:
        normalized = self._normalize_theme_key(theme_key)
        if normalized.startswith("region:"):
            return 10
        return THEME_PRIORITIES.get(normalized, 1)

    def _normalize_theme_key(self, theme_key: str) -> str:
        normalized = self._text(theme_key).casefold().replace("-", "_")
        if normalized.startswith("region:"):
            region = normalized.split(":", 1)[1]
            return "region:" + self._slug(region)
        return normalized

    @staticmethod
    def _contains_marker(
        text: str,
        assets: set[str],
        markers: set[str],
    ) -> bool:
        combined = text + " " + " ".join(sorted(assets))
        return any(marker in combined for marker in markers)

    @staticmethod
    def _build_theme_brief_id(theme_key: str, report_date: date, version: str) -> str:
        return f"theme_brief_{theme_key}_{report_date.isoformat()}_{version}"

    @staticmethod
    def _slug(value: str) -> str:
        return re.sub(r"[^a-z0-9]+", "_", value.casefold()).strip("_")

    @staticmethod
    def _today() -> date:
        return datetime.now(UTC).date()

    def _mapping(self, value: Any) -> dict[str, Any]:
        return dict(value) if isinstance(value, Mapping) else {}

    def _sequence_of_mappings(self, value: Any) -> list[dict[str, Any]]:
        if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
            return []
        return [dict(item) for item in value if isinstance(item, Mapping)]

    @staticmethod
    def _text_list(value: Any) -> list[str]:
        if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
            return []
        return [str(item).strip() for item in value if str(item).strip()]

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


__all__ = ["ThemeSummarizer"]
