from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from typing import Any, Protocol

from ..utils.logger import get_logger
from .metrics import log_stage_metrics, mean_float, safe_ratio

logger = get_logger("event-summarizer")

STATE_CHANGE_MAP = {
    "new": "new",
    "active": "new",
    "updated": "updated",
    "stabilizing": "updated",
    "escalating": "escalated",
    "resolved": "resolved",
    "dormant": "resolved",
}

NOVELTY_LABELS = (
    (0.75, "high"),
    (0.45, "medium"),
    (0.0, "low"),
)

CORROBORATION_LABELS = (
    (0.75, "strong"),
    (0.45, "moderate"),
    (0.0, "weak"),
)


class BriefRepositoryLike(Protocol):
    async def upsert_event_brief(self, brief: Mapping[str, Any]) -> dict[str, Any]: ...


class EventQueryLike(Protocol):
    async def get_event_timeline(self, event_id: str) -> dict[str, Any]: ...


class EvidenceSelectorLike(Protocol):
    async def select_event_evidence(
        self,
        event_id: str,
        *,
        profile: str = "macro_daily",
        limit: int | None = None,
    ) -> dict[str, Any]: ...

    async def select_ranked_event_evidence(
        self,
        *,
        statuses: Sequence[str] | None = None,
        since: datetime | None = None,
        theme: str | None = None,
        profile: str = "macro_daily",
        per_event_limit: int = 4,
        limit: int = 20,
    ) -> list[dict[str, Any]]: ...


class EventSummarizer:
    def __init__(
        self,
        brief_repository: BriefRepositoryLike,
        event_query_service: EventQueryLike,
        evidence_selector: EvidenceSelectorLike,
        *,
        version: str = "v1",
        model: str = "rule_template_v1",
    ):
        self.brief_repository = brief_repository
        self.event_query_service = event_query_service
        self.evidence_selector = evidence_selector
        self.version = version
        self.model = model
        self.last_brief_metrics: dict[str, Any] = {}

    async def summarize_event(
        self,
        event_id: str,
        *,
        profile: str = "macro_daily",
        evidence_limit: int = 4,
        version: str | None = None,
    ) -> dict[str, Any]:
        evidence_package = await self.evidence_selector.select_event_evidence(
            event_id,
            profile=profile,
            limit=evidence_limit,
        )
        timeline = await self.event_query_service.get_event_timeline(event_id)
        stored = await self._persist_brief(
            timeline=timeline,
            evidence_package=evidence_package,
            profile=profile,
            version=version or self.version,
        )
        self.last_brief_metrics = self._build_brief_metrics(
            [stored],
            events_considered=1,
            profile=profile,
        )
        log_stage_metrics(
            logger,
            "brief",
            self.last_brief_metrics,
            service="EventSummarizer.summarize_event",
        )
        return stored

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
        evidence_packages = await self.evidence_selector.select_ranked_event_evidence(
            statuses=statuses,
            since=since,
            theme=theme,
            profile=profile,
            per_event_limit=evidence_limit,
            limit=limit,
        )
        stored_briefs: list[dict[str, Any]] = []
        for package in evidence_packages:
            event_id = self._text(package.get("event_id"))
            if not event_id:
                continue
            timeline = await self.event_query_service.get_event_timeline(event_id)
            stored_briefs.append(
                await self._persist_brief(
                    timeline=timeline,
                    evidence_package=package,
                    profile=profile,
                    version=version or self.version,
                )
            )

        self.last_brief_metrics = self._build_brief_metrics(
            stored_briefs,
            events_considered=len(evidence_packages),
            profile=profile,
        )
        log_stage_metrics(
            logger,
            "brief",
            self.last_brief_metrics,
            service="EventSummarizer.summarize_ranked_events",
        )
        return stored_briefs

    async def _persist_brief(
        self,
        *,
        timeline: Mapping[str, Any],
        evidence_package: Mapping[str, Any],
        profile: str,
        version: str,
    ) -> dict[str, Any]:
        brief_json = self._build_brief_json(
            timeline=timeline,
            evidence_package=evidence_package,
            profile=profile,
        )
        event_id = self._text(brief_json.get("eventId"))
        summary = self._build_summary(brief_json)
        return await self.brief_repository.upsert_event_brief(
            {
                "brief_id": self._build_brief_id(event_id, version),
                "event_id": event_id,
                "version": version,
                "summary": summary,
                "brief_json": brief_json,
                "model": self.model,
            }
        )

    def _build_brief_json(
        self,
        *,
        timeline: Mapping[str, Any],
        evidence_package: Mapping[str, Any],
        profile: str,
    ) -> dict[str, Any]:
        event = self._mapping(timeline.get("event"))
        enrichment = self._mapping(timeline.get("enrichment"))
        transitions = self._sequence_of_mappings(timeline.get("transitions"))
        event_score = self._mapping(evidence_package.get("event_score"))
        supporting_evidence = self._sequence_of_mappings(
            evidence_package.get("supporting_evidence")
        )
        contradicting_evidence = self._sequence_of_mappings(
            evidence_package.get("contradicting_evidence")
        )

        event_id = self._text(event.get("event_id"))
        regions = self._names(enrichment.get("regions"), limit=4)
        channels = self._names(enrichment.get("market_channels"), limit=4)
        assets = self._names(enrichment.get("assets"), limit=4)
        status = self._text(event.get("status"))
        event_type = self._text(event.get("event_type")) or self._text(
            enrichment.get("event_type")
        )
        source_count = max(
            self._safe_int(event.get("source_count")),
            self._safe_int(enrichment.get("source_count")),
        )
        article_count = max(
            self._safe_int(event.get("article_count")),
            self._safe_int(enrichment.get("member_count")),
        )

        state_change = self._state_change(event, transitions)
        confidence = self._confidence_score(event_score)
        novelty = self._label(
            self._safe_float(event_score.get("novelty_score")),
            NOVELTY_LABELS,
        )
        corroboration = self._label(
            self._safe_float(event_score.get("corroboration_score")),
            CORROBORATION_LABELS,
        )
        contradictions = [
            {
                "articleId": self._text(item.get("article_id")),
                "sourceId": self._text(item.get("source_id")),
                "title": self._text(item.get("title")),
            }
            for item in contradicting_evidence
            if self._text(item.get("article_id"))
        ]
        evidence_refs = [
            self._text(item.get("article_id"))
            for item in [*supporting_evidence, *contradicting_evidence]
            if self._text(item.get("article_id"))
        ]
        last_transition = self._last_transition(event, transitions)
        top_drivers = self._top_driver_names(event_score)

        brief = {
            "eventId": event_id,
            "canonicalTitle": self._text(event.get("canonical_title")),
            "stateChange": state_change,
            "coreFacts": self._core_facts(
                event=event,
                event_type=event_type,
                state_change=state_change,
                source_count=source_count,
                article_count=article_count,
                regions=regions,
                channels=channels,
                supporting_evidence=supporting_evidence,
                contradicting_evidence=contradicting_evidence,
            ),
            "whyItMatters": self._why_it_matters(
                event_type=event_type,
                state_change=state_change,
                channels=channels,
                top_drivers=top_drivers,
                confidence=confidence,
                contradictions=contradictions,
            ),
            "marketChannels": channels,
            "regions": regions,
            "assets": assets,
            "confidence": confidence,
            "novelty": novelty,
            "corroboration": corroboration,
            "evidenceRefs": evidence_refs,
            "contradictions": contradictions,
            "profile": profile,
            "eventType": event_type,
            "status": status,
            "totalScore": round(self._safe_float(event_score.get("total_score")), 3),
            "lastTransition": {
                "toState": self._text(last_transition.get("to_state")),
                "reason": self._text(last_transition.get("reason")),
            },
            "generatedAt": datetime.now(UTC).isoformat(),
        }
        return brief

    def _core_facts(
        self,
        *,
        event: Mapping[str, Any],
        event_type: str,
        state_change: str,
        source_count: int,
        article_count: int,
        regions: Sequence[str],
        channels: Sequence[str],
        supporting_evidence: Sequence[Mapping[str, Any]],
        contradicting_evidence: Sequence[Mapping[str, Any]],
    ) -> list[str]:
        facts: list[str] = []
        facts.append(
            f"{self._event_type_label(event_type)} event is {state_change} with {source_count} sources and {article_count} articles."
        )
        if regions or channels:
            scope_parts: list[str] = []
            if regions:
                scope_parts.append(f"regions: {', '.join(regions)}")
            if channels:
                scope_parts.append(f"market channels: {', '.join(channels)}")
            facts.append(f"Primary impact scope covers {'; '.join(scope_parts)}.")

        for item in supporting_evidence[:2]:
            title = self._text(item.get("title"))
            if title:
                facts.append(title)

        if contradicting_evidence:
            counter_title = self._text(contradicting_evidence[0].get("title"))
            if counter_title:
                facts.append(f"Counterpoint: {counter_title}")

        deduped: list[str] = []
        seen = set()
        for fact in facts:
            normalized = fact.casefold()
            if not fact or normalized in seen:
                continue
            seen.add(normalized)
            deduped.append(fact)
        return deduped[:4]

    def _why_it_matters(
        self,
        *,
        event_type: str,
        state_change: str,
        channels: Sequence[str],
        top_drivers: Sequence[str],
        confidence: float,
        contradictions: Sequence[Mapping[str, Any]],
    ) -> str:
        channels_text = ", ".join(channels[:3]) if channels else "cross-asset sentiment"
        driver_text = ", ".join(top_drivers[:2]) if top_drivers else "market impact"
        contradiction_text = (
            " while contradictory reporting remains active"
            if contradictions
            else ""
        )
        return (
            f"This {self._event_type_label(event_type).lower()} matters for {channels_text} "
            f"because it is {state_change} and currently ranks on {driver_text}, "
            f"with confidence {confidence:.2f}{contradiction_text}."
        )

    def _build_summary(self, brief_json: Mapping[str, Any]) -> str:
        title = self._text(brief_json.get("canonicalTitle"))
        why = self._text(brief_json.get("whyItMatters"))
        if not why:
            return title
        if not title:
            return why
        summary = f"{title}: {why}"
        return summary[:400]

    def _build_brief_metrics(
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
        confidences = [
            self._safe_float(item.get("confidence"))
            for item in brief_jsons
            if item
        ]
        total_scores = [
            self._safe_float(item.get("totalScore"))
            for item in brief_jsons
            if item
        ]
        contradiction_briefs = sum(
            1 for item in brief_jsons if self._sequence_of_mappings(item.get("contradictions"))
        )
        evidence_counts = [
            len(self._text_list(item.get("evidenceRefs")))
            for item in brief_jsons
        ]
        return {
            "profile": profile,
            "events_considered": max(events_considered, 0),
            "briefs_generated": len(brief_jsons),
            "avg_confidence": mean_float(confidences),
            "avg_total_score": mean_float(total_scores),
            "contradiction_brief_ratio": safe_ratio(
                contradiction_briefs,
                len(brief_jsons),
            ),
            "avg_evidence_ref_count": mean_float(evidence_counts),
        }

    def _state_change(
        self,
        event: Mapping[str, Any],
        transitions: Sequence[Mapping[str, Any]],
    ) -> str:
        transition = self._last_transition(event, transitions)
        raw_state = self._text(transition.get("to_state")) or self._text(
            event.get("status")
        )
        return STATE_CHANGE_MAP.get(raw_state.casefold(), "updated")

    def _last_transition(
        self,
        event: Mapping[str, Any],
        transitions: Sequence[Mapping[str, Any]],
    ) -> dict[str, Any]:
        if transitions:
            return dict(transitions[-1])
        return {
            "to_state": self._text(event.get("status")),
            "reason": "",
        }

    def _confidence_score(self, event_score: Mapping[str, Any]) -> float:
        corroboration = self._safe_float(event_score.get("corroboration_score"))
        source_quality = self._safe_float(event_score.get("source_quality_score"))
        uncertainty = self._safe_float(event_score.get("uncertainty_score"))
        confidence = corroboration * 0.45 + source_quality * 0.35 + (1.0 - uncertainty) * 0.2
        return round(min(max(confidence, 0.0), 1.0), 3)

    def _top_driver_names(self, event_score: Mapping[str, Any]) -> list[str]:
        payload = self._mapping(event_score.get("payload"))
        explanation = self._mapping(payload.get("explanation"))
        top_drivers = self._sequence_of_mappings(explanation.get("top_drivers"))
        labels: list[str] = []
        for driver in top_drivers:
            dimension = self._text(driver.get("dimension"))
            if not dimension:
                continue
            labels.append(dimension.replace("_score", "").replace("_", " "))
        return labels

    def _names(self, items: Any, *, limit: int) -> list[str]:
        names: list[str] = []
        if not isinstance(items, Sequence) or isinstance(items, (str, bytes)):
            return names
        for item in items:
            if isinstance(item, Mapping):
                name = self._text(item.get("name"))
            else:
                name = self._text(item)
            if name:
                names.append(name)
            if len(names) >= limit:
                break
        return names

    def _label(
        self,
        score: float,
        ranges: Sequence[tuple[float, str]],
    ) -> str:
        for threshold, label in ranges:
            if score >= threshold:
                return label
        return ranges[-1][1]

    @staticmethod
    def _event_type_label(value: str) -> str:
        if not value:
            return "Event"
        return value.replace("_", " ").title()

    @staticmethod
    def _build_brief_id(event_id: str, version: str) -> str:
        return f"brief_{event_id}_{version}"

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
    def _optional_datetime(value: Any) -> datetime | None:
        if not isinstance(value, datetime):
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value

    @staticmethod
    def _text(value: Any) -> str:
        if value is None:
            return ""
        if isinstance(value, str):
            return value.strip()
        return str(value).strip()


__all__ = ["EventSummarizer"]
