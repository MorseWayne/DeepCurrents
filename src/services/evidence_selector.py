from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
import re
from typing import Any, Protocol


QUANT_SIGNAL_RE = re.compile(
    r"\b\d+(?:\.\d+)?(?:%|bp|bps|m|mn|bn|million|billion|trillion|mbpd)?\b",
    re.IGNORECASE,
)
POLICY_SIGNAL_TERMS = {
    "benchmark rate",
    "interest rate",
    "central bank",
    "rate decision",
    "rate cut",
    "rate hike",
    "tariff",
    "sanction",
    "approved",
    "approval",
    "package",
    "guidance",
    "treasury",
    "ministry",
    "parliament",
    "opec",
    "quota",
    "policy",
    "央行",
    "利率",
    "关税",
    "制裁",
    "批准",
    "政策",
}
SCORE_FIELDS = (
    "threat_score",
    "market_impact_score",
    "novelty_score",
    "corroboration_score",
    "source_quality_score",
    "velocity_score",
    "uncertainty_score",
    "total_score",
)


@dataclass(frozen=True)
class EvidenceCandidate:
    article_id: str
    source_id: str
    title: str
    canonical_url: str
    published_at: datetime | None
    role: str
    is_primary: bool
    tier: int
    source_type: str
    dedup_relations_count: int
    snippet: str
    keywords: tuple[str, ...]
    entities: tuple[str, ...]
    side: str
    base_score: float
    coverage_tokens: frozenset[str]
    quantitative_signal: bool
    policy_signal: bool
    base_reasons: tuple[str, ...]


@dataclass(frozen=True)
class SelectedEvidence:
    candidate: EvidenceCandidate
    evidence_score: float
    selection_reasons: tuple[str, ...]


class ArticleRepositoryLike(Protocol):
    async def get_article(self, article_id: str) -> dict[str, Any] | None: ...

    async def get_article_features(self, article_id: str) -> dict[str, Any] | None: ...


class EventQueryLike(Protocol):
    async def get_event_timeline(self, event_id: str) -> dict[str, Any]: ...


class EventRankerLike(Protocol):
    async def score_event(
        self,
        event_id: str,
        *,
        profile: str = "macro_daily",
    ) -> dict[str, Any]: ...

    async def rank_events(
        self,
        *,
        statuses: Sequence[str] | None = None,
        since: datetime | None = None,
        theme: str | None = None,
        limit: int = 100,
        profile: str = "macro_daily",
    ) -> list[dict[str, Any]]: ...


class EvidenceSelector:
    def __init__(
        self,
        article_repository: ArticleRepositoryLike,
        event_query_service: EventQueryLike,
        event_ranker: EventRankerLike,
        *,
        default_limit: int = 4,
        selection_version: str = "v1",
        max_keywords: int = 5,
        max_entities: int = 6,
    ):
        self.article_repository = article_repository
        self.event_query_service = event_query_service
        self.event_ranker = event_ranker
        self.default_limit = max(default_limit, 1)
        self.selection_version = selection_version
        self.max_keywords = max(max_keywords, 1)
        self.max_entities = max(max_entities, 1)

    async def select_event_evidence(
        self,
        event_id: str,
        *,
        profile: str = "macro_daily",
        limit: int | None = None,
    ) -> dict[str, Any]:
        scored = await self.event_ranker.score_event(event_id, profile=profile)
        timeline = await self.event_query_service.get_event_timeline(event_id)
        return await self._build_evidence_package(
            timeline=timeline,
            scored_event=scored,
            limit=self.default_limit if limit is None else max(limit, 0),
        )

    async def select_ranked_event_evidence(
        self,
        *,
        statuses: Sequence[str] | None = None,
        since: datetime | None = None,
        theme: str | None = None,
        profile: str = "macro_daily",
        per_event_limit: int = 4,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        ranked_events = await self.event_ranker.rank_events(
            statuses=statuses,
            since=since,
            theme=theme,
            limit=limit,
            profile=profile,
        )
        packages: list[dict[str, Any]] = []
        for ranked in ranked_events:
            event_id = self._text(ranked.get("event_id"))
            if not event_id:
                continue
            timeline = await self.event_query_service.get_event_timeline(event_id)
            packages.append(
                await self._build_evidence_package(
                    timeline=timeline,
                    scored_event=self._mapping(ranked.get("score")),
                    limit=max(per_event_limit, 0),
                )
            )
        return packages

    async def _build_evidence_package(
        self,
        *,
        timeline: Mapping[str, Any],
        scored_event: Mapping[str, Any],
        limit: int,
    ) -> dict[str, Any]:
        event = self._mapping(timeline.get("event"))
        enrichment = self._mapping(timeline.get("enrichment"))
        members = self._sequence_of_mappings(timeline.get("members"))
        transitions = self._sequence_of_mappings(timeline.get("transitions"))
        event_id = self._text(event.get("event_id"))

        contradicting_article_ids = self._contradicting_article_ids(transitions)
        contradicting_source_ids = self._source_ids(
            enrichment.get("contradicting_sources")
        )
        latest_event_time = self._optional_datetime(
            event.get("latest_article_at") or event.get("last_updated_at")
        )

        candidates: list[EvidenceCandidate] = []
        for member in members:
            candidate = await self._build_candidate(
                member=member,
                latest_event_time=latest_event_time,
                contradicting_article_ids=contradicting_article_ids,
                contradicting_source_ids=contradicting_source_ids,
            )
            if candidate is not None:
                candidates.append(candidate)

        supporting_candidates = [
            candidate for candidate in candidates if candidate.side == "supporting"
        ]
        contradicting_candidates = [
            candidate for candidate in candidates if candidate.side == "contradicting"
        ]
        supporting_limit, contradicting_limit = self._slot_allocation(
            total_limit=limit,
            supporting_count=len(supporting_candidates),
            contradicting_count=len(contradicting_candidates),
        )
        selected_supporting = self._select_diverse_candidates(
            supporting_candidates,
            limit=supporting_limit,
        )
        selected_contradicting = self._select_diverse_candidates(
            contradicting_candidates,
            limit=contradicting_limit,
        )

        return {
            "event_id": event_id,
            "profile": self._text(scored_event.get("profile")),
            "event_score": self._serialize_event_score(scored_event),
            "supporting_evidence": [
                self._serialize_selected_evidence(item)
                for item in selected_supporting
            ],
            "contradicting_evidence": [
                self._serialize_selected_evidence(item)
                for item in selected_contradicting
            ],
            "coverage_notes": self._build_coverage_notes(
                selected_supporting=selected_supporting,
                selected_contradicting=selected_contradicting,
                supporting_candidates=supporting_candidates,
                contradicting_candidates=contradicting_candidates,
            ),
            "selection_metadata": {
                "selection_version": self.selection_version,
                "requested_limit": limit,
                "selected_count": len(selected_supporting) + len(selected_contradicting),
                "supporting_candidate_count": len(supporting_candidates),
                "contradicting_candidate_count": len(contradicting_candidates),
                "supporting_selected_count": len(selected_supporting),
                "contradicting_selected_count": len(selected_contradicting),
                "event_type": self._text(event.get("event_type"))
                or self._text(enrichment.get("event_type")),
                "status": self._text(event.get("status")),
                "reserved_contradicting_slot": bool(
                    contradicting_candidates and limit >= 2
                ),
            },
        }

    async def _build_candidate(
        self,
        *,
        member: Mapping[str, Any],
        latest_event_time: datetime | None,
        contradicting_article_ids: set[str],
        contradicting_source_ids: set[str],
    ) -> EvidenceCandidate | None:
        article_id = self._text(member.get("article_id"))
        if not article_id:
            return None

        article = await self.article_repository.get_article(article_id) or {}
        features = await self.article_repository.get_article_features(article_id) or {}
        source_id = self._text(member.get("source_id")) or self._text(
            article.get("source_id")
        )
        title = self._text(member.get("title")) or self._text(article.get("title"))
        published_at = self._optional_datetime(
            member.get("published_at") or article.get("published_at")
        )
        role = self._text(member.get("role"))
        is_primary = bool(member.get("is_primary"))
        dedup_relations_count = self._safe_int(member.get("dedup_relations_count"))
        tier = self._safe_int(article.get("tier")) or 4
        source_type = self._text(article.get("source_type")).casefold() or "other"
        snippet = self._snippet(
            article.get("clean_content") or article.get("content") or ""
        )
        keywords = tuple(self._normalize_keywords(features.get("keywords")))
        entities = tuple(self._normalize_entities(features.get("entities")))
        text_blob = " ".join(
            part for part in (title, snippet, " ".join(keywords), " ".join(entities)) if part
        )
        quantitative_signal = bool(QUANT_SIGNAL_RE.search(text_blob))
        policy_signal = self._contains_policy_signal(text_blob)
        side = (
            "contradicting"
            if article_id in contradicting_article_ids
            or source_id.casefold() in contradicting_source_ids
            else "supporting"
        )

        base_score = self._candidate_base_score(
            is_primary=is_primary,
            role=role,
            tier=tier,
            source_type=source_type,
            quantitative_signal=quantitative_signal,
            policy_signal=policy_signal,
            dedup_relations_count=dedup_relations_count,
            latest_event_time=latest_event_time,
            published_at=published_at,
            side=side,
        )
        base_reasons = list(self._candidate_base_reasons(
            is_primary=is_primary,
            role=role,
            tier=tier,
            quantitative_signal=quantitative_signal,
            policy_signal=policy_signal,
            side=side,
        ))
        coverage_tokens = frozenset(
            self._coverage_tokens(
                title=title,
                keywords=keywords,
                entities=entities,
            )
        )

        return EvidenceCandidate(
            article_id=article_id,
            source_id=source_id,
            title=title,
            canonical_url=self._text(article.get("canonical_url")),
            published_at=published_at,
            role=role,
            is_primary=is_primary,
            tier=tier,
            source_type=source_type,
            dedup_relations_count=dedup_relations_count,
            snippet=snippet,
            keywords=keywords[: self.max_keywords],
            entities=entities[: self.max_entities],
            side=side,
            base_score=base_score,
            coverage_tokens=coverage_tokens,
            quantitative_signal=quantitative_signal,
            policy_signal=policy_signal,
            base_reasons=tuple(base_reasons),
        )

    def _slot_allocation(
        self,
        *,
        total_limit: int,
        supporting_count: int,
        contradicting_count: int,
    ) -> tuple[int, int]:
        if total_limit <= 0:
            return 0, 0
        if contradicting_count <= 0:
            return min(total_limit, supporting_count), 0
        if supporting_count <= 0:
            return 0, min(total_limit, contradicting_count)
        if total_limit == 1:
            return 1, 0

        contradicting_limit = min(
            contradicting_count,
            max(1, total_limit // 3),
        )
        supporting_limit = min(supporting_count, max(total_limit - contradicting_limit, 1))
        remaining = total_limit - supporting_limit - contradicting_limit

        while remaining > 0:
            remaining_supporting = max(supporting_count - supporting_limit, 0)
            remaining_contradicting = max(
                contradicting_count - contradicting_limit,
                0,
            )
            if remaining_supporting <= 0 and remaining_contradicting <= 0:
                break
            if remaining_supporting >= remaining_contradicting and remaining_supporting > 0:
                supporting_limit += 1
            elif remaining_contradicting > 0:
                contradicting_limit += 1
            else:
                supporting_limit += 1
            remaining -= 1
        return supporting_limit, contradicting_limit

    def _select_diverse_candidates(
        self,
        candidates: Sequence[EvidenceCandidate],
        *,
        limit: int,
    ) -> list[SelectedEvidence]:
        if limit <= 0:
            return []

        remaining = list(candidates)
        selected: list[SelectedEvidence] = []
        used_sources: set[str] = set()
        covered_tokens: set[str] = set()

        while remaining and len(selected) < limit:
            best_candidate: EvidenceCandidate | None = None
            best_score = -1.0
            best_reasons: tuple[str, ...] = ()
            for candidate in remaining:
                score, reasons = self._candidate_selection_score(
                    candidate,
                    used_sources=used_sources,
                    covered_tokens=covered_tokens,
                )
                if (
                    best_candidate is None
                    or score > best_score
                    or (
                        score == best_score
                        and self._candidate_sort_key(candidate)
                        > self._candidate_sort_key(best_candidate)
                    )
                ):
                    best_candidate = candidate
                    best_score = score
                    best_reasons = reasons

            if best_candidate is None:
                break

            remaining = [
                candidate
                for candidate in remaining
                if candidate.article_id != best_candidate.article_id
            ]
            used_sources.add(best_candidate.source_id.casefold())
            covered_tokens.update(best_candidate.coverage_tokens)
            selected.append(
                SelectedEvidence(
                    candidate=best_candidate,
                    evidence_score=round(best_score, 3),
                    selection_reasons=best_reasons,
                )
            )
        return selected

    def _candidate_selection_score(
        self,
        candidate: EvidenceCandidate,
        *,
        used_sources: set[str],
        covered_tokens: set[str],
    ) -> tuple[float, tuple[str, ...]]:
        score = candidate.base_score
        reasons = list(candidate.base_reasons)
        source_id = candidate.source_id.casefold()

        if candidate.source_id and source_id not in used_sources:
            score += 0.14
            reasons.append("independent_source")
        elif source_id in used_sources:
            score -= 0.08

        new_tokens = candidate.coverage_tokens - covered_tokens
        if new_tokens:
            score += min(len(new_tokens) * 0.02, 0.12)
            reasons.append("expands_coverage")

        overlap_ratio = self._overlap_ratio(candidate.coverage_tokens, covered_tokens)
        if overlap_ratio >= 0.6:
            score -= 0.12

        return round(max(score, 0.0), 3), tuple(dict.fromkeys(reasons))

    def _candidate_base_score(
        self,
        *,
        is_primary: bool,
        role: str,
        tier: int,
        source_type: str,
        quantitative_signal: bool,
        policy_signal: bool,
        dedup_relations_count: int,
        latest_event_time: datetime | None,
        published_at: datetime | None,
        side: str,
    ) -> float:
        role_score = 0.22 if is_primary else 0.12 if role == "primary" else 0.06
        tier_score = {1: 1.0, 2: 0.82, 3: 0.64, 4: 0.45}.get(tier, 0.45)
        source_type_bonus = {
            "wire": 0.08,
            "official": 0.08,
            "news": 0.04,
            "analysis": 0.02,
        }.get(source_type, 0.0)
        source_quality = min(tier_score + source_type_bonus, 1.0)
        freshness_score = self._freshness_score(
            latest_event_time=latest_event_time,
            published_at=published_at,
        )
        score = role_score + source_quality * 0.32 + freshness_score
        if quantitative_signal:
            score += 0.12
        if policy_signal:
            score += 0.10
        if side == "contradicting":
            score += 0.03
        score -= min(dedup_relations_count * 0.05, 0.18)
        return round(max(score, 0.0), 3)

    def _candidate_base_reasons(
        self,
        *,
        is_primary: bool,
        role: str,
        tier: int,
        quantitative_signal: bool,
        policy_signal: bool,
        side: str,
    ) -> tuple[str, ...]:
        reasons: list[str] = []
        if is_primary or role == "primary":
            reasons.append("primary_event_report")
        if tier <= 2:
            reasons.append("top_tier_source")
        if quantitative_signal:
            reasons.append("quantified_market_detail")
        if policy_signal:
            reasons.append("policy_decision_signal")
        if side == "contradicting":
            reasons.append("contradicting_narrative")
        return tuple(reasons)

    def _build_coverage_notes(
        self,
        *,
        selected_supporting: Sequence[SelectedEvidence],
        selected_contradicting: Sequence[SelectedEvidence],
        supporting_candidates: Sequence[EvidenceCandidate],
        contradicting_candidates: Sequence[EvidenceCandidate],
    ) -> list[str]:
        notes: list[str] = []
        if selected_supporting:
            notes.append(
                "selected "
                f"{len(selected_supporting)} supporting articles across "
                f"{len({item.candidate.source_id for item in selected_supporting if item.candidate.source_id})} sources"
            )
        if selected_contradicting:
            notes.append(
                "retained "
                f"{len(selected_contradicting)} contradicting articles across "
                f"{len({item.candidate.source_id for item in selected_contradicting if item.candidate.source_id})} sources"
            )
        selected_items = [*selected_supporting, *selected_contradicting]
        signal_count = sum(
            1
            for item in selected_items
            if item.candidate.quantitative_signal or item.candidate.policy_signal
        )
        if signal_count:
            notes.append(
                f"{signal_count} selected articles carry quantified or policy-relevant details"
            )
        redundant_count = max(
            len(supporting_candidates)
            + len(contradicting_candidates)
            - len(selected_supporting)
            - len(selected_contradicting),
            0,
        )
        if redundant_count:
            notes.append(
                f"de-prioritized {redundant_count} redundant articles with overlapping coverage"
            )
        return notes

    def _serialize_event_score(self, score: Mapping[str, Any]) -> dict[str, Any]:
        payload = self._mapping(score.get("payload"))
        explanation = self._mapping(payload.get("explanation"))
        return {
            "profile": self._text(score.get("profile")),
            **{
                field: self._safe_float(score.get(field))
                for field in SCORE_FIELDS
            },
            "risk_flags": self._text_list(explanation.get("risk_flags")),
            "top_drivers": [
                dict(item)
                for item in explanation.get("top_drivers", [])
                if isinstance(item, Mapping)
            ],
        }

    def _serialize_selected_evidence(
        self,
        item: SelectedEvidence,
    ) -> dict[str, Any]:
        candidate = item.candidate
        return {
            "article_id": candidate.article_id,
            "source_id": candidate.source_id,
            "title": candidate.title,
            "canonical_url": candidate.canonical_url,
            "published_at": candidate.published_at,
            "role": candidate.role,
            "is_primary": candidate.is_primary,
            "tier": candidate.tier,
            "source_type": candidate.source_type,
            "side": candidate.side,
            "evidence_score": item.evidence_score,
            "selection_reasons": list(item.selection_reasons),
            "quantitative_signal": candidate.quantitative_signal,
            "policy_signal": candidate.policy_signal,
            "dedup_relations_count": candidate.dedup_relations_count,
            "keywords": list(candidate.keywords),
            "entities": list(candidate.entities),
            "snippet": candidate.snippet,
        }

    def _contradicting_article_ids(
        self,
        transitions: Sequence[Mapping[str, Any]],
    ) -> set[str]:
        article_ids: set[str] = set()
        for transition in transitions:
            metadata = transition.get("metadata")
            if not isinstance(metadata, Mapping):
                continue
            merge_signals = metadata.get("merge_signals")
            if not isinstance(merge_signals, Mapping):
                continue
            if bool(merge_signals.get("conflict")):
                article_id = self._text(transition.get("trigger_article_id"))
                if article_id:
                    article_ids.add(article_id)
        return article_ids

    def _source_ids(self, items: Any) -> set[str]:
        if not isinstance(items, Sequence) or isinstance(items, (str, bytes)):
            return set()
        return {
            self._text(item.get("source_id")).casefold()
            for item in items
            if isinstance(item, Mapping) and self._text(item.get("source_id"))
        }

    def _coverage_tokens(
        self,
        *,
        title: str,
        keywords: Sequence[str],
        entities: Sequence[str],
    ) -> list[str]:
        tokens = [
            self._normalize_token(token)
            for token in [*keywords, *entities, *self._text_tokens(title)]
        ]
        unique: list[str] = []
        seen = set()
        for token in tokens:
            if not token or token in seen:
                continue
            seen.add(token)
            unique.append(token)
        return unique

    def _freshness_score(
        self,
        *,
        latest_event_time: datetime | None,
        published_at: datetime | None,
    ) -> float:
        if latest_event_time is None or published_at is None:
            return 0.05
        age_hours = max(
            0.0,
            (latest_event_time - published_at).total_seconds() / 3600,
        )
        freshness = max(0.0, 1.0 - min(age_hours / 48.0, 1.0))
        return round(freshness * 0.14, 3)

    def _contains_policy_signal(self, text: str) -> bool:
        normalized = text.casefold()
        return any(term in normalized for term in POLICY_SIGNAL_TERMS)

    def _overlap_ratio(
        self,
        candidate_tokens: frozenset[str],
        covered_tokens: set[str],
    ) -> float:
        if not candidate_tokens or not covered_tokens:
            return 0.0
        overlap = candidate_tokens & covered_tokens
        return len(overlap) / max(len(candidate_tokens), 1)

    def _candidate_sort_key(self, candidate: EvidenceCandidate) -> tuple[Any, ...]:
        published = candidate.published_at
        timestamp = published.timestamp() if isinstance(published, datetime) else 0.0
        return (
            1 if candidate.is_primary else 0,
            -candidate.tier,
            timestamp,
            -candidate.dedup_relations_count,
            candidate.article_id,
        )

    def _normalize_keywords(self, value: Any) -> list[str]:
        if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
            return []
        items: list[str] = []
        for item in value:
            token = self._normalize_token(item)
            if token:
                items.append(token)
        return items[: self.max_keywords]

    def _normalize_entities(self, value: Any) -> list[str]:
        if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
            return []
        names: list[str] = []
        for item in value:
            if not isinstance(item, Mapping):
                token = self._normalize_token(item)
                if token:
                    names.append(token)
                continue
            token = self._normalize_token(item.get("name"))
            if token:
                names.append(token)
        return names[: self.max_entities]

    def _snippet(self, value: Any) -> str:
        text = self._text(value)
        if not text:
            return ""
        normalized = " ".join(text.split())
        return normalized[:220]

    def _text_tokens(self, text: str) -> list[str]:
        return [
            token
            for token in re.findall(r"[A-Za-z0-9_%-]+", text.casefold())
            if len(token) >= 3
        ][: self.max_keywords]

    @staticmethod
    def _normalize_token(value: Any) -> str:
        if value is None:
            return ""
        return str(value).strip().casefold()

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


__all__ = ["EvidenceSelector"]
