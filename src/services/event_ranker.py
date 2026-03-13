from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any, Mapping, Protocol, Sequence


THREAT_EVENT_TYPES = {"conflict", "supply_disruption"}
HIGH_IMPACT_EVENT_TYPES = {"central_bank", "conflict", "supply_disruption", "macro_data"}
HIGH_IMPACT_CHANNELS = {"rates", "fx", "commodities", "energy", "credit", "shipping"}
MACRO_DAILY_WEIGHTS = {
    "threat_score": 0.14,
    "market_impact_score": 0.24,
    "novelty_score": 0.18,
    "corroboration_score": 0.18,
    "source_quality_score": 0.14,
    "velocity_score": 0.08,
    "uncertainty_penalty": 0.12,
}


class EventRepositoryLike(Protocol):
    async def get_event(self, event_id: str) -> dict[str, Any] | None: ...

    async def list_recent_events(
        self,
        *,
        statuses: Sequence[str] | None = None,
        since: datetime | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]: ...

    async def upsert_event_score(self, score: Mapping[str, Any]) -> dict[str, Any]: ...


class ArticleRepositoryLike(Protocol):
    async def get_article(self, article_id: str) -> dict[str, Any] | None: ...


class EventQueryLike(Protocol):
    async def get_event_timeline(self, event_id: str) -> dict[str, Any]: ...

    async def list_events(
        self,
        *,
        event_id: str | None = None,
        statuses: Sequence[str] | None = None,
        since: datetime | None = None,
        theme: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]: ...


class EventRanker:
    def __init__(
        self,
        event_repository: EventRepositoryLike,
        article_repository: ArticleRepositoryLike,
        event_query_service: EventQueryLike,
        *,
        reference_now: datetime | None = None,
    ):
        self.event_repository = event_repository
        self.article_repository = article_repository
        self.event_query_service = event_query_service
        self.reference_now = reference_now

    async def score_event(
        self,
        event_id: str,
        *,
        profile: str = "macro_daily",
    ) -> dict[str, Any]:
        timeline = await self.event_query_service.get_event_timeline(event_id)
        score_payload = await self._build_score_payload(
            timeline,
            profile=profile,
        )
        return await self.event_repository.upsert_event_score(score_payload)

    async def score_events(
        self,
        event_ids: Sequence[str],
        *,
        profile: str = "macro_daily",
    ) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        for event_id in event_ids:
            normalized = self._text(event_id)
            if not normalized:
                continue
            results.append(await self.score_event(normalized, profile=profile))
        return results

    async def rank_events(
        self,
        *,
        statuses: Sequence[str] | None = None,
        since: datetime | None = None,
        theme: str | None = None,
        limit: int = 100,
        profile: str = "macro_daily",
    ) -> list[dict[str, Any]]:
        event_items = await self.event_query_service.list_events(
            statuses=statuses,
            since=since,
            theme=theme,
            limit=limit,
        )
        ranked: list[dict[str, Any]] = []
        for item in event_items:
            event_id = self._text(item.get("event_id"))
            if not event_id:
                continue
            scored = await self.score_event(event_id, profile=profile)
            ranked.append(
                {
                    "event_id": event_id,
                    "total_score": self._safe_float(scored.get("total_score")),
                    "score": dict(scored),
                    "event": dict(item),
                }
            )
        ranked.sort(key=lambda item: item["total_score"], reverse=True)
        return ranked[:limit]

    async def _build_score_payload(
        self,
        timeline: Mapping[str, Any],
        *,
        profile: str,
    ) -> dict[str, Any]:
        event = self._mapping(timeline.get("event"))
        enrichment = self._mapping(timeline.get("enrichment"))
        members = self._sequence_of_mappings(timeline.get("members"))
        transitions = self._sequence_of_mappings(timeline.get("transitions"))

        threat_score = self._threat_score(event, enrichment)
        market_impact_score = self._market_impact_score(event, enrichment)
        novelty_score = self._novelty_score(event, enrichment)
        corroboration_score = self._corroboration_score(event, enrichment)
        source_quality_score = await self._source_quality_score(members)
        velocity_score = self._velocity_score(event, members, transitions)
        uncertainty_score = self._uncertainty_score(event, enrichment)

        total_score = self._total_score(
            threat_score=threat_score,
            market_impact_score=market_impact_score,
            novelty_score=novelty_score,
            corroboration_score=corroboration_score,
            source_quality_score=source_quality_score,
            velocity_score=velocity_score,
            uncertainty_score=uncertainty_score,
        )
        event_id = self._text(event.get("event_id"))
        scored_at = self._now()

        payload = {
            "event_id": event_id,
            "profile": profile,
            "threat_score": threat_score,
            "market_impact_score": market_impact_score,
            "novelty_score": novelty_score,
            "corroboration_score": corroboration_score,
            "source_quality_score": source_quality_score,
            "velocity_score": velocity_score,
            "uncertainty_score": uncertainty_score,
            "total_score": total_score,
            "payload": {
                "weights": dict(MACRO_DAILY_WEIGHTS),
                "explanation": {
                    "event_type": self._text(event.get("event_type"))
                    or self._text(enrichment.get("event_type")),
                    "market_channels": self._extract_names(
                        enrichment.get("market_channels")
                    ),
                    "supporting_sources": len(
                        enrichment.get("supporting_sources", [])
                    ),
                    "contradicting_sources": len(
                        enrichment.get("contradicting_sources", [])
                    ),
                    "last_transition": self._mapping(
                        enrichment.get("last_transition")
                    ),
                },
                "member_count": len(members),
            },
            "scored_at": scored_at,
        }
        return payload

    def _threat_score(
        self,
        event: Mapping[str, Any],
        enrichment: Mapping[str, Any],
    ) -> float:
        event_type = self._text(event.get("event_type")) or self._text(
            enrichment.get("event_type")
        )
        status = self._text(event.get("status")).casefold()
        channels = {
            name.casefold() for name in self._extract_names(enrichment.get("market_channels"))
        }

        score = 0.2
        if event_type in THREAT_EVENT_TYPES:
            score += 0.4
        if status == "escalating":
            score += 0.2
        if {"shipping", "energy", "credit"} & channels:
            score += 0.1
        if self._text(event.get("canonical_title")).casefold().find("attack") >= 0:
            score += 0.1
        return round(min(score, 1.0), 3)

    def _market_impact_score(
        self,
        event: Mapping[str, Any],
        enrichment: Mapping[str, Any],
    ) -> float:
        event_type = self._text(event.get("event_type")) or self._text(
            enrichment.get("event_type")
        )
        channels = {
            name.casefold() for name in self._extract_names(enrichment.get("market_channels"))
        }
        assets = self._extract_names(enrichment.get("assets"))

        score = 0.1
        if event_type in HIGH_IMPACT_EVENT_TYPES:
            score += 0.25
        score += min(len(channels & HIGH_IMPACT_CHANNELS) * 0.15, 0.45)
        score += min(len(assets) * 0.05, 0.2)
        return round(min(score, 1.0), 3)

    def _novelty_score(
        self,
        event: Mapping[str, Any],
        enrichment: Mapping[str, Any],
    ) -> float:
        last_transition = self._mapping(enrichment.get("last_transition"))
        status = self._text(event.get("status")).casefold()
        score = 0.2
        if self._text(last_transition.get("to_state")).casefold() in {
            "new",
            "updated",
            "escalating",
        }:
            score += 0.35
        if status in {"new", "updated", "escalating"}:
            score += 0.15

        latest_article_at = self._optional_datetime(
            event.get("latest_article_at") or event.get("last_updated_at")
        )
        if latest_article_at is not None:
            age_hours = max(
                0.0,
                (self._now() - latest_article_at).total_seconds() / 3600,
            )
            freshness = max(0.0, 1.0 - min(age_hours / 24.0, 1.0))
            score += freshness * 0.3
        return round(min(score, 1.0), 3)

    def _corroboration_score(
        self,
        event: Mapping[str, Any],
        enrichment: Mapping[str, Any],
    ) -> float:
        supporting_sources = len(self._source_ids(enrichment.get("supporting_sources")))
        contradicting_sources = len(
            self._source_ids(enrichment.get("contradicting_sources"))
        )
        unique_source_count = len(
            self._source_ids(enrichment.get("supporting_sources"))
            | self._source_ids(enrichment.get("contradicting_sources"))
        )
        source_count = max(
            self._safe_int(event.get("source_count")),
            self._safe_int(enrichment.get("source_count")),
            unique_source_count,
        )
        article_count = max(
            self._safe_int(event.get("article_count")),
            self._safe_int(enrichment.get("member_count")),
        )

        score = min(supporting_sources * 0.25 + source_count * 0.1 + article_count * 0.04, 1.0)
        if contradicting_sources > 0:
            score = max(0.0, score - min(0.15 * contradicting_sources, 0.45))
        return round(score, 3)

    async def _source_quality_score(
        self,
        members: Sequence[Mapping[str, Any]],
    ) -> float:
        if not members:
            return 0.0

        scores: list[float] = []
        for member in members:
            article_id = self._text(member.get("article_id"))
            if not article_id:
                continue
            article = await self.article_repository.get_article(article_id) or {}
            tier = self._safe_int(article.get("tier"))
            source_type = self._text(article.get("source_type")).casefold()
            tier_score = {1: 1.0, 2: 0.82, 3: 0.64, 4: 0.45}.get(tier, 0.45)
            source_type_bonus = {
                "wire": 0.08,
                "official": 0.08,
                "news": 0.04,
                "analysis": 0.02,
            }.get(source_type, 0.0)
            scores.append(min(tier_score + source_type_bonus, 1.0))
        if not scores:
            return 0.0
        return round(sum(scores) / len(scores), 3)

    def _velocity_score(
        self,
        event: Mapping[str, Any],
        members: Sequence[Mapping[str, Any]],
        transitions: Sequence[Mapping[str, Any]],
    ) -> float:
        article_count = self._safe_int(event.get("article_count")) or len(members)
        latest_article_at = self._optional_datetime(
            event.get("latest_article_at") or event.get("last_updated_at")
        )
        started_at = self._optional_datetime(event.get("started_at"))

        score = min(article_count * 0.08, 0.45)
        if started_at is not None and latest_article_at is not None:
            duration_hours = max(
                1.0, (latest_article_at - started_at).total_seconds() / 3600
            )
            cadence = min(article_count / duration_hours, 1.0)
            score += cadence * 0.35

        recent_transitions = 0
        recent_threshold = self._now() - timedelta(hours=24)
        for transition in transitions:
            created_at = self._optional_datetime(transition.get("created_at"))
            if created_at is not None and created_at >= recent_threshold:
                recent_transitions += 1
        score += min(recent_transitions * 0.08, 0.2)
        return round(min(score, 1.0), 3)

    def _uncertainty_score(
        self,
        event: Mapping[str, Any],
        enrichment: Mapping[str, Any],
    ) -> float:
        supporting_source_ids = self._source_ids(enrichment.get("supporting_sources"))
        contradicting_source_ids = self._source_ids(
            enrichment.get("contradicting_sources")
        )
        contradicting_sources = len(contradicting_source_ids)
        supporting_sources = len(supporting_source_ids)
        unique_source_count = len(supporting_source_ids | contradicting_source_ids)
        source_count = max(
            self._safe_int(event.get("source_count")),
            unique_source_count,
        )

        score = 0.0
        if source_count <= 1:
            score += 0.45
        score += min(contradicting_sources * 0.3, 0.6)
        if supporting_sources == 0:
            score += 0.1
        return round(min(score, 1.0), 3)

    def _source_ids(self, items: Any) -> set[str]:
        if not isinstance(items, Sequence) or isinstance(items, (str, bytes)):
            return set()
        return {
            self._text(item.get("source_id")).casefold()
            for item in items
            if isinstance(item, Mapping) and self._text(item.get("source_id"))
        }

    def _total_score(
        self,
        *,
        threat_score: float,
        market_impact_score: float,
        novelty_score: float,
        corroboration_score: float,
        source_quality_score: float,
        velocity_score: float,
        uncertainty_score: float,
    ) -> float:
        total = (
            threat_score * MACRO_DAILY_WEIGHTS["threat_score"]
            + market_impact_score * MACRO_DAILY_WEIGHTS["market_impact_score"]
            + novelty_score * MACRO_DAILY_WEIGHTS["novelty_score"]
            + corroboration_score * MACRO_DAILY_WEIGHTS["corroboration_score"]
            + source_quality_score * MACRO_DAILY_WEIGHTS["source_quality_score"]
            + velocity_score * MACRO_DAILY_WEIGHTS["velocity_score"]
            - uncertainty_score * MACRO_DAILY_WEIGHTS["uncertainty_penalty"]
        )
        return round(max(total, 0.0), 3)

    def _extract_names(self, items: Any) -> list[str]:
        if not isinstance(items, Sequence) or isinstance(items, (str, bytes)):
            return []
        names: list[str] = []
        for item in items:
            if isinstance(item, Mapping):
                name = self._text(item.get("name"))
                if name:
                    names.append(name)
            else:
                name = self._text(item)
                if name:
                    names.append(name)
        return names

    def _mapping(self, value: Any) -> dict[str, Any]:
        return dict(value) if isinstance(value, Mapping) else {}

    def _sequence_of_mappings(self, value: Any) -> list[dict[str, Any]]:
        if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
            return []
        return [dict(item) for item in value if isinstance(item, Mapping)]

    def _now(self) -> datetime:
        if self.reference_now is not None:
            return self.reference_now
        return datetime.now(UTC)

    @staticmethod
    def _optional_datetime(value: Any) -> datetime | None:
        if not isinstance(value, datetime):
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value

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


__all__ = ["EventRanker"]
