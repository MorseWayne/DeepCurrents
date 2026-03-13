from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Mapping, Protocol, Sequence

from ..config.settings import CONFIG
from ..utils.tokenizer import tokenize
from .article_models import ArticleRecord
from .db_service import dice_coefficient, generate_trigrams, jaccard_similarity
from .event_state_machine import EventStateDecision, EventStateMachine

ENTITY_METADATA_KEYS = (
    "entities",
    "entity",
    "symbols",
    "tickers",
    "companies",
    "countries",
    "regions",
    "locations",
    "people",
    "organizations",
    "orgs",
    "assets",
    "topics",
    "tags",
)
REGION_METADATA_KEYS = ("regions", "countries", "locations", "markets")
LOCATION_ENTITY_TYPES = {"location", "region", "country"}
ACTION_GROUPS = {
    "rate_cut": {
        "cut",
        "cuts",
        "lower",
        "lowers",
        "lowered",
        "easing",
        "downshift",
        "downshifted",
        "降息",
        "下调",
    },
    "rate_hike": {
        "hike",
        "hikes",
        "raise",
        "raises",
        "raised",
        "tightening",
        "加息",
        "上调",
    },
    "approval": {
        "approve",
        "approves",
        "approved",
        "pass",
        "passes",
        "passed",
        "adopt",
        "adopts",
        "adopted",
        "批准",
        "通过",
    },
    "rejection": {
        "reject",
        "rejects",
        "rejected",
        "block",
        "blocks",
        "blocked",
        "veto",
        "vetoes",
        "vetoed",
        "deny",
        "denies",
        "denied",
        "否决",
        "否认",
        "驳回",
    },
    "surge": {"surge", "surges", "jump", "jumps", "spike", "spikes", "飙升", "跳涨"},
    "slump": {
        "slump",
        "slumps",
        "fall",
        "falls",
        "drop",
        "drops",
        "plunge",
        "plunges",
        "下跌",
        "暴跌",
    },
}
ACTION_CONFLICTS = {
    "rate_cut": {"rate_hike"},
    "rate_hike": {"rate_cut"},
    "approval": {"rejection"},
    "rejection": {"approval"},
    "surge": {"slump"},
    "slump": {"surge"},
}
RISK_MARKERS = {
    "attack",
    "attacks",
    "strike",
    "strikes",
    "missile",
    "missiles",
    "drone",
    "drones",
    "sanction",
    "sanctions",
    "outage",
    "halt",
    "halts",
    "shutdown",
    "shutdowns",
    "default",
    "defaults",
    "爆炸",
    "袭击",
    "停摆",
    "违约",
    "断供",
    "停火破裂",
}
RESOLUTION_MARKERS = {
    "ceasefire",
    "truce",
    "resolved",
    "restored",
    "restore",
    "reopen",
    "reopened",
    "resume",
    "resumes",
    "resumed",
    "agreement",
    "deal",
    "ended",
    "withdrawn",
    "clarified",
    "clarification",
    "停火",
    "恢复",
    "重启",
    "澄清",
    "证伪",
    "结束",
    "复航",
}


class EventRepositoryLike(Protocol):
    async def list_recent_events(
        self,
        *,
        statuses: Sequence[str] | None = None,
        since: datetime | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]: ...

    async def create_event(self, event: Mapping[str, Any]) -> dict[str, Any]: ...

    async def update_event(
        self, event_id: str, fields: Mapping[str, Any]
    ) -> dict[str, Any]: ...

    async def add_event_member(self, member: Mapping[str, Any]) -> dict[str, Any]: ...

    async def list_event_members(self, event_id: str) -> list[dict[str, Any]]: ...

    async def upsert_event_score(self, score: Mapping[str, Any]) -> dict[str, Any]: ...

    async def record_state_transition(
        self, transition: Mapping[str, Any]
    ) -> dict[str, Any]: ...


class ArticleRepositoryLike(Protocol):
    async def get_article(self, article_id: str) -> dict[str, Any] | None: ...

    async def get_article_features(self, article_id: str) -> dict[str, Any] | None: ...


class VectorStoreLike(Protocol):
    async def query_similar_points(
        self,
        collection_name: str,
        *,
        query_vector: Sequence[float],
        limit: int = 10,
        score_threshold: float | None = None,
        with_payload: bool | Sequence[str] = True,
    ) -> list[dict[str, Any]]: ...


@dataclass(frozen=True)
class EventCandidateMatch:
    event: Mapping[str, Any]
    current_members: list[dict[str, Any]]
    merge_signals: dict[str, Any]


class EventBuilder:
    def __init__(
        self,
        event_repository: EventRepositoryLike,
        article_repository: ArticleRepositoryLike,
        vector_store: VectorStoreLike | None = None,
        state_machine: EventStateMachine | None = None,
        *,
        candidate_window_hours: int = CONFIG.dedup_hours_back,
        candidate_limit: int = 100,
        title_similarity_threshold: float = CONFIG.dedup_similarity_threshold,
        candidate_statuses: Sequence[str] = (
            "new",
            "active",
            "updated",
            "escalating",
            "stabilizing",
        ),
        merge_score_threshold: float = 0.58,
        semantic_score_threshold: float = 0.75,
        semantic_limit: int = 12,
        vector_collection: str = "article_features",
    ):
        self.event_repository = event_repository
        self.article_repository = article_repository
        self.vector_store = vector_store
        self.state_machine = state_machine or EventStateMachine()
        self.candidate_window_hours = candidate_window_hours
        self.candidate_limit = candidate_limit
        self.title_similarity_threshold = title_similarity_threshold
        self.candidate_statuses = tuple(candidate_statuses)
        self.merge_score_threshold = merge_score_threshold
        self.semantic_score_threshold = semantic_score_threshold
        self.semantic_limit = semantic_limit
        self.vector_collection = vector_collection

    async def assign_article_to_event(
        self,
        article: ArticleRecord | Mapping[str, Any],
        *,
        extracted_features: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        seed = self._coerce_article(article)
        article_id = self._text(seed.get("article_id"))
        if not article_id:
            raise ValueError("article_id is required")

        anchor_time = self._article_time(seed)
        candidates = await self.event_repository.list_recent_events(
            statuses=self.candidate_statuses,
            since=anchor_time - timedelta(hours=self.candidate_window_hours),
            limit=self.candidate_limit,
        )

        target_event = await self._pick_best_candidate(
            seed,
            candidates,
            anchor_time=anchor_time,
            extracted_features=extracted_features,
        )
        if target_event is None:
            return await self._create_new_event(seed, anchor_time)
        return await self._attach_to_existing_event(
            seed,
            target_event,
            anchor_time,
        )

    async def extract_and_persist(
        self,
        article: ArticleRecord | Mapping[str, Any],
        *,
        extracted_features: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        assigned = await self.assign_article_to_event(
            article,
            extracted_features=extracted_features,
        )
        score = await self._upsert_event_score(
            assigned,
            extracted_features=extracted_features,
        )
        return {**assigned, "score": score}

    async def _upsert_event_score(
        self,
        assigned: Mapping[str, Any],
        *,
        extracted_features: Mapping[str, Any] | None,
    ) -> dict[str, Any] | None:
        if not extracted_features or "quality_score" not in extracted_features:
            return None

        event = assigned.get("event")
        if not isinstance(event, Mapping):
            return None
        event_id = self._text(event.get("event_id"))
        if not event_id:
            return None

        quality_score = float(extracted_features.get("quality_score") or 0)
        return await self.event_repository.upsert_event_score(
            {
                "event_id": event_id,
                "profile": "ingestion_v1",
                "source_quality_score": quality_score,
                "total_score": quality_score,
                "payload": {
                    "quality_score": quality_score,
                    "keywords": list(extracted_features.get("keywords", [])),
                    "entities": list(extracted_features.get("entities", [])),
                },
                "scored_at": datetime.now(UTC),
            }
        )

    async def _create_new_event(
        self,
        article: Mapping[str, Any],
        anchor_time: datetime,
    ) -> dict[str, Any]:
        article_id = self._text(article.get("article_id"))
        event_id = self._build_event_id(article_id, anchor_time)
        event = await self.event_repository.create_event(
            {
                "event_id": event_id,
                "status": "new",
                "canonical_title": self._article_title(article),
                "started_at": anchor_time,
                "last_updated_at": anchor_time,
                "latest_article_at": anchor_time,
                "article_count": 1,
                "source_count": 1,
                "metadata": self._normalize_metadata(
                    {
                        "seed_article_id": article_id,
                        "created_by": "event_builder",
                    }
                ),
            }
        )
        member = await self.event_repository.add_event_member(
            {
                "event_id": event_id,
                "article_id": article_id,
                "role": "primary",
                "is_primary": True,
                "added_at": anchor_time,
            }
        )
        transition = await self._record_state_transition(
            event_id=event_id,
            from_state="",
            to_state="new",
            trigger_article_id=article_id,
            reason="event_created",
            metadata={
                "article_count": 1,
                "source_count": 1,
                "seed_article_id": article_id,
            },
            anchor_time=anchor_time,
        )
        return {
            "event": event,
            "member": member,
            "created": True,
            "transition": transition,
            "merge_signals": {
                "confidence": 1.0,
                "support_score": 1.0,
                "new_entity_count": 0,
                "new_region_count": 0,
                "risk_signal_delta": 0.0,
                "resolution_signal": False,
            },
        }

    async def _attach_to_existing_event(
        self,
        article: Mapping[str, Any],
        candidate_match: EventCandidateMatch,
        anchor_time: datetime,
    ) -> dict[str, Any]:
        event = candidate_match.event
        current_members = candidate_match.current_members
        merge_signals = candidate_match.merge_signals

        event_id = self._text(event.get("event_id"))
        article_id = self._text(article.get("article_id"))
        if not event_id:
            raise ValueError("event_id is required for candidate event")

        existing_member = next(
            (
                dict(member)
                for member in current_members
                if self._text(member.get("article_id")) == article_id
            ),
            None,
        )
        has_primary = any(bool(member.get("is_primary")) for member in current_members)
        member = existing_member or await self.event_repository.add_event_member(
            {
                "event_id": event_id,
                "article_id": article_id,
                "role": "supporting" if has_primary else "primary",
                "is_primary": False if has_primary else True,
                "added_at": anchor_time,
            }
        )

        article_count = max(
            self._safe_int(event.get("article_count")),
            len(current_members) + (0 if existing_member else 1),
        )
        source_count = await self._estimate_source_count(
            event_id,
            current_members,
            article,
        )

        decision = self.state_machine.evaluate(
            event,
            article=article,
            article_count=article_count,
            source_count=source_count,
            merge_signals=merge_signals,
            anchor_time=anchor_time,
        )
        status = (
            decision.to_state
            if decision is not None
            else self._text(event.get("status")) or "active"
        )

        started_at = self._min_datetime(
            self._optional_datetime(event.get("started_at")),
            anchor_time,
        )
        latest_article_at = self._max_datetime(
            self._optional_datetime(event.get("latest_article_at")),
            anchor_time,
        )

        updated_event = await self.event_repository.update_event(
            event_id,
            {
                "status": status,
                "started_at": started_at,
                "last_updated_at": anchor_time,
                "latest_article_at": latest_article_at,
                "article_count": article_count,
                "source_count": source_count,
                "metadata": self._build_event_metadata(
                    event,
                    article_id=article_id,
                    merge_signals=merge_signals,
                    decision=decision,
                ),
            },
        )

        transition = None
        if decision is not None:
            transition = await self._record_state_transition(
                event_id=event_id,
                from_state=decision.from_state,
                to_state=decision.to_state,
                trigger_article_id=article_id,
                reason=decision.reason,
                metadata={
                    **decision.metadata,
                    "merge_signals": self._compact_merge_signals(merge_signals),
                },
                anchor_time=anchor_time,
            )
        return {
            "event": updated_event,
            "member": member,
            "created": False,
            "transition": transition,
            "merge_signals": merge_signals,
        }

    async def _pick_best_candidate(
        self,
        article: Mapping[str, Any],
        candidates: Sequence[Mapping[str, Any]],
        *,
        anchor_time: datetime,
        extracted_features: Mapping[str, Any] | None,
    ) -> EventCandidateMatch | None:
        best: EventCandidateMatch | None = None
        best_score = 0.0
        article_cache: dict[str, dict[str, Any] | None] = {}
        feature_cache: dict[str, dict[str, Any] | None] = {}
        semantic_scores = await self._query_semantic_scores(extracted_features)

        for candidate in candidates:
            event_id = self._text(candidate.get("event_id"))
            if not event_id:
                continue

            current_members = await self.event_repository.list_event_members(event_id)
            merge_signals = await self._build_merge_signals(
                article,
                candidate,
                current_members,
                anchor_time=anchor_time,
                extracted_features=extracted_features,
                semantic_scores=semantic_scores,
                article_cache=article_cache,
                feature_cache=feature_cache,
            )

            score = self._safe_float(merge_signals.get("confidence"))
            if merge_signals.get("conflict"):
                continue
            if score < self.merge_score_threshold:
                continue
            if score > best_score:
                best_score = score
                best = EventCandidateMatch(
                    event=candidate,
                    current_members=current_members,
                    merge_signals=merge_signals,
                )
        return best

    async def _query_semantic_scores(
        self,
        extracted_features: Mapping[str, Any] | None,
    ) -> dict[str, float]:
        if self.vector_store is None or not extracted_features:
            return {}
        embedding = extracted_features.get("embedding")
        if (
            not isinstance(embedding, Sequence)
            or isinstance(embedding, (str, bytes))
            or not embedding
        ):
            return {}

        points = await self.vector_store.query_similar_points(
            self.vector_collection,
            query_vector=[float(item) for item in embedding],
            limit=self.semantic_limit,
            score_threshold=self.semantic_score_threshold,
            with_payload=True,
        )
        scores: dict[str, float] = {}
        for point in points:
            payload = point.get("payload") or {}
            article_id = self._text(payload.get("article_id") or point.get("id"))
            if not article_id:
                continue
            scores[article_id] = max(
                self._safe_float(point.get("score")),
                scores.get(article_id, 0.0),
            )
        return scores

    async def _build_merge_signals(
        self,
        article: Mapping[str, Any],
        candidate: Mapping[str, Any],
        current_members: Sequence[Mapping[str, Any]],
        *,
        anchor_time: datetime,
        extracted_features: Mapping[str, Any] | None,
        semantic_scores: Mapping[str, float],
        article_cache: dict[str, dict[str, Any] | None],
        feature_cache: dict[str, dict[str, Any] | None],
    ) -> dict[str, Any]:
        article_title = self._article_title(article)
        candidate_title = self._text(candidate.get("canonical_title"))
        title_similarity = self._title_similarity(article_title, candidate_title)
        latest_candidate_time = (
            self._optional_datetime(candidate.get("latest_article_at"))
            or self._optional_datetime(candidate.get("last_updated_at"))
            or self._optional_datetime(candidate.get("started_at"))
        )
        time_proximity = self._time_proximity(anchor_time, latest_candidate_time)

        article_entities = self._extract_entities(article, extracted_features)
        article_regions = self._extract_regions(article, extracted_features)
        article_actions = self._extract_action_groups(article)
        article_risk_markers = self._extract_risk_markers(article)
        resolution_signal = bool(self._extract_resolution_markers(article))

        candidate_entities: set[str] = set()
        candidate_regions: set[str] = set()
        candidate_actions: set[str] = self._action_groups_from_text(candidate_title)
        candidate_risk_markers: set[str] = self._risk_markers_from_text(candidate_title)

        member_ids: list[str] = []
        for member in current_members:
            member_article_id = self._text(member.get("article_id"))
            if not member_article_id:
                continue
            member_ids.append(member_article_id)
            article_row, feature_row = await self._load_article_context(
                member_article_id,
                article_cache=article_cache,
                feature_cache=feature_cache,
            )
            candidate_entities.update(self._extract_entities(article_row, feature_row))
            candidate_regions.update(self._extract_regions(article_row, feature_row))
            candidate_actions.update(self._extract_action_groups(article_row))
            candidate_risk_markers.update(self._extract_risk_markers(article_row))

        entity_overlap = self._overlap_ratio(article_entities, candidate_entities)
        region_overlap = self._overlap_ratio(article_regions, candidate_regions)
        new_entity_count = len(article_entities - candidate_entities)
        new_region_count = len(article_regions - candidate_regions)
        risk_signal_delta = float(
            len(article_risk_markers - candidate_risk_markers)
        )
        semantic_support = max(
            (semantic_scores.get(article_id, 0.0) for article_id in member_ids),
            default=0.0,
        )
        support_score = round(
            (
                title_similarity * 0.4
                + max(entity_overlap, region_overlap) * 0.25
                + semantic_support * 0.35
            ),
            3,
        )
        confidence = round(
            (
                title_similarity * 0.35
                + semantic_support * 0.3
                + entity_overlap * 0.2
                + region_overlap * 0.05
                + time_proximity * 0.1
            ),
            3,
        )
        conflict_reason = self._detect_action_conflict(article_actions, candidate_actions)
        if title_similarity >= self.title_similarity_threshold and time_proximity >= 0.5:
            confidence = max(confidence, round(title_similarity * 0.7 + time_proximity * 0.3, 3))
        if conflict_reason:
            confidence = round(max(0.0, confidence - 0.4), 3)

        return {
            "title_similarity": round(title_similarity, 3),
            "semantic_support": round(semantic_support, 3),
            "entity_overlap": round(entity_overlap, 3),
            "region_overlap": round(region_overlap, 3),
            "time_proximity": round(time_proximity, 3),
            "support_score": support_score,
            "confidence": confidence,
            "new_entity_count": new_entity_count,
            "new_region_count": new_region_count,
            "risk_signal_delta": round(risk_signal_delta, 3),
            "resolution_signal": resolution_signal,
            "semantic_hit_count": sum(
                1 for article_id in member_ids if semantic_scores.get(article_id, 0.0) > 0
            ),
            "conflict": bool(conflict_reason),
            "conflict_reason": conflict_reason,
        }

    async def _load_article_context(
        self,
        article_id: str,
        *,
        article_cache: dict[str, dict[str, Any] | None],
        feature_cache: dict[str, dict[str, Any] | None],
    ) -> tuple[dict[str, Any], dict[str, Any] | None]:
        if article_id not in article_cache:
            article_cache[article_id] = await self.article_repository.get_article(article_id)
        if article_id not in feature_cache:
            feature_cache[article_id] = await self.article_repository.get_article_features(
                article_id
            )
        return dict(article_cache[article_id] or {}), feature_cache[article_id]

    async def _estimate_source_count(
        self,
        event_id: str,
        current_members: Sequence[Mapping[str, Any]],
        article: Mapping[str, Any],
    ) -> int:
        source_ids: set[str] = set()
        new_source = self._text(article.get("source_id"))
        if new_source:
            source_ids.add(new_source)

        if not current_members:
            current_members = await self.event_repository.list_event_members(event_id)

        for member in current_members:
            member_article_id = self._text(member.get("article_id"))
            if not member_article_id:
                continue
            row = await self.article_repository.get_article(member_article_id)
            if not row:
                continue
            source_id = self._text(row.get("source_id"))
            if source_id:
                source_ids.add(source_id)

        return max(1, len(source_ids))

    async def _record_state_transition(
        self,
        *,
        event_id: str,
        from_state: str,
        to_state: str,
        trigger_article_id: str,
        reason: str,
        metadata: Mapping[str, Any],
        anchor_time: datetime,
    ) -> dict[str, Any]:
        transition_id = self._build_transition_id(
            event_id,
            trigger_article_id,
            from_state,
            to_state,
            anchor_time,
        )
        return await self.event_repository.record_state_transition(
            {
                "transition_id": transition_id,
                "event_id": event_id,
                "from_state": from_state,
                "to_state": to_state,
                "trigger_article_id": trigger_article_id,
                "reason": reason,
                "metadata": self._normalize_metadata(metadata),
            }
        )

    def _build_event_metadata(
        self,
        event: Mapping[str, Any],
        *,
        article_id: str,
        merge_signals: Mapping[str, Any],
        decision: EventStateDecision | None,
    ) -> dict[str, Any]:
        base_metadata = event.get("metadata") if isinstance(event.get("metadata"), Mapping) else {}
        metadata = dict(base_metadata)
        metadata.update(
            {
                "last_article_id": article_id,
                "last_merge_confidence": round(
                    self._safe_float(merge_signals.get("confidence")), 3
                ),
                "last_merge_signals": self._compact_merge_signals(merge_signals),
            }
        )
        if decision is not None:
            metadata["last_transition"] = {
                "from_state": decision.from_state,
                "to_state": decision.to_state,
                "reason": decision.reason,
            }
        return self._normalize_metadata(metadata)

    def _compact_merge_signals(self, merge_signals: Mapping[str, Any]) -> dict[str, Any]:
        return {
            "confidence": round(self._safe_float(merge_signals.get("confidence")), 3),
            "title_similarity": round(
                self._safe_float(merge_signals.get("title_similarity")),
                3,
            ),
            "semantic_support": round(
                self._safe_float(merge_signals.get("semantic_support")),
                3,
            ),
            "entity_overlap": round(
                self._safe_float(merge_signals.get("entity_overlap")),
                3,
            ),
            "region_overlap": round(
                self._safe_float(merge_signals.get("region_overlap")),
                3,
            ),
            "time_proximity": round(
                self._safe_float(merge_signals.get("time_proximity")),
                3,
            ),
            "new_entity_count": self._safe_int(
                merge_signals.get("new_entity_count")
            ),
            "new_region_count": self._safe_int(
                merge_signals.get("new_region_count")
            ),
            "risk_signal_delta": round(
                self._safe_float(merge_signals.get("risk_signal_delta")),
                3,
            ),
            "resolution_signal": bool(merge_signals.get("resolution_signal")),
            "conflict": bool(merge_signals.get("conflict")),
            "conflict_reason": self._text(merge_signals.get("conflict_reason")),
        }

    def _extract_entities(
        self,
        article: Mapping[str, Any] | None,
        features: Mapping[str, Any] | None,
    ) -> set[str]:
        entities: set[str] = set()
        for payload in (features, article):
            if not isinstance(payload, Mapping):
                continue
            raw_entities = payload.get("entities")
            entities.update(self._iter_entity_names(raw_entities))
            metadata = payload.get("metadata")
            if isinstance(metadata, Mapping):
                for key in ENTITY_METADATA_KEYS:
                    entities.update(self._iter_entity_names(metadata.get(key)))
        return entities

    def _extract_regions(
        self,
        article: Mapping[str, Any] | None,
        features: Mapping[str, Any] | None,
    ) -> set[str]:
        regions: set[str] = set()
        for payload in (features, article):
            if not isinstance(payload, Mapping):
                continue
            raw_entities = payload.get("entities")
            if isinstance(raw_entities, Sequence) and not isinstance(
                raw_entities, (str, bytes)
            ):
                for item in raw_entities:
                    if not isinstance(item, Mapping):
                        continue
                    entity_type = self._text(item.get("type")).lower()
                    if entity_type in LOCATION_ENTITY_TYPES:
                        normalized = self._normalize_term(item.get("name"))
                        if normalized:
                            regions.add(normalized)
            metadata = payload.get("metadata")
            if isinstance(metadata, Mapping):
                for key in REGION_METADATA_KEYS:
                    regions.update(self._iter_entity_names(metadata.get(key)))
        return regions

    def _extract_action_groups(self, article: Mapping[str, Any] | None) -> set[str]:
        text = self._article_text(article)
        return self._action_groups_from_text(text)

    def _extract_risk_markers(self, article: Mapping[str, Any] | None) -> set[str]:
        text = self._article_text(article)
        return self._risk_markers_from_text(text)

    def _extract_resolution_markers(
        self,
        article: Mapping[str, Any] | None,
    ) -> set[str]:
        return self._resolution_markers_from_text(self._article_text(article))

    def _article_text(self, article: Mapping[str, Any] | None) -> str:
        if not isinstance(article, Mapping):
            return ""
        return " ".join(
            part
            for part in (
                self._text(article.get("title")),
                self._text(article.get("normalized_title")),
                self._text(article.get("clean_content") or article.get("content"))[:500],
            )
            if part
        )

    def _action_groups_from_text(self, text: str) -> set[str]:
        lowered = text.casefold()
        return {
            group
            for group, markers in ACTION_GROUPS.items()
            if any(marker in lowered for marker in markers)
        }

    def _risk_markers_from_text(self, text: str) -> set[str]:
        lowered = text.casefold()
        return {marker for marker in RISK_MARKERS if marker in lowered}

    def _resolution_markers_from_text(self, text: str) -> set[str]:
        lowered = text.casefold()
        return {marker for marker in RESOLUTION_MARKERS if marker in lowered}

    def _detect_action_conflict(
        self,
        article_actions: set[str],
        candidate_actions: set[str],
    ) -> str:
        for action in article_actions:
            for opposite in ACTION_CONFLICTS.get(action, set()):
                if opposite in candidate_actions:
                    return f"{action}_vs_{opposite}"
        return ""

    def _overlap_ratio(self, left: set[str], right: set[str]) -> float:
        if not left or not right:
            return 0.0
        return round(len(left & right) / max(1, min(len(left), len(right))), 3)

    def _iter_entity_names(self, payload: Any) -> set[str]:
        values: set[str] = set()
        if payload is None:
            return values
        if isinstance(payload, Mapping):
            normalized = self._normalize_term(
                payload.get("name") or payload.get("value") or payload.get("id")
            )
            if normalized:
                values.add(normalized)
            return values
        if isinstance(payload, (str, bytes)):
            normalized = self._normalize_term(payload)
            if normalized:
                values.add(normalized)
            return values
        if isinstance(payload, Sequence):
            for item in payload:
                values.update(self._iter_entity_names(item))
        return values

    def _coerce_article(
        self,
        article: ArticleRecord | Mapping[str, Any],
    ) -> dict[str, Any]:
        if isinstance(article, ArticleRecord):
            return article.to_feature_seed()
        if not isinstance(article, Mapping):
            raise TypeError("article must be an ArticleRecord or mapping")
        return dict(article)

    def _article_time(self, article: Mapping[str, Any]) -> datetime:
        for key in ("published_at", "ingested_at"):
            value = article.get(key)
            parsed = self._optional_datetime(value)
            if parsed is not None:
                return parsed
        return datetime.now(UTC)

    def _article_title(self, article: Mapping[str, Any]) -> str:
        title = self._text(article.get("normalized_title") or article.get("title"))
        if not title:
            return "untitled event"
        return title

    def _title_similarity(self, left_title: str, right_title: str) -> float:
        left = self._text(left_title)
        right = self._text(right_title)
        if not left or not right:
            return 0.0
        if left == right:
            return 1.0
        token_score = jaccard_similarity(tokenize(left), tokenize(right))
        trigram_score = dice_coefficient(
            generate_trigrams(left),
            generate_trigrams(right),
        )
        return max(token_score, trigram_score)

    def _time_proximity(
        self,
        anchor_time: datetime,
        candidate_time: datetime | None,
    ) -> float:
        if candidate_time is None:
            return 0.0
        delta_hours = abs((anchor_time - candidate_time).total_seconds()) / 3600
        ratio = 1.0 - min(delta_hours / max(self.candidate_window_hours, 1), 1.0)
        return round(max(ratio, 0.0), 3)

    def _build_event_id(self, article_id: str, anchor_time: datetime) -> str:
        digest = hashlib.sha1(
            f"{article_id}:{anchor_time.isoformat()}".encode("utf-8")
        ).hexdigest()[:16]
        return f"evt_{digest}"

    def _build_transition_id(
        self,
        event_id: str,
        article_id: str,
        from_state: str,
        to_state: str,
        anchor_time: datetime,
    ) -> str:
        digest = hashlib.sha1(
            f"{event_id}:{article_id}:{from_state}:{to_state}:{anchor_time.isoformat()}".encode(
                "utf-8"
            )
        ).hexdigest()[:16]
        return f"etr_{digest}"

    @staticmethod
    def _normalize_metadata(metadata: Mapping[str, Any]) -> dict[str, Any]:
        return json.loads(json.dumps(dict(metadata), default=str))

    @staticmethod
    def _optional_datetime(value: Any) -> datetime | None:
        if not isinstance(value, datetime):
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value

    @staticmethod
    def _safe_float(value: Any) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return 0.0

    @staticmethod
    def _safe_int(value: Any) -> int:
        try:
            return int(value)
        except (TypeError, ValueError):
            return 0

    @staticmethod
    def _min_datetime(left: datetime | None, right: datetime) -> datetime:
        if left is None:
            return right
        return min(left, right)

    @staticmethod
    def _max_datetime(left: datetime | None, right: datetime) -> datetime:
        if left is None:
            return right
        return max(left, right)

    @staticmethod
    def _normalize_term(value: Any) -> str:
        if value is None:
            return ""
        if isinstance(value, str):
            normalized = " ".join(value.split()).strip().casefold()
            return normalized
        return str(value).strip().casefold()

    @staticmethod
    def _text(value: Any) -> str:
        if value is None:
            return ""
        if isinstance(value, str):
            return value.strip()
        return str(value).strip()


__all__ = ["EventBuilder"]
