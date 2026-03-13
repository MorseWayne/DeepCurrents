from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta
from typing import Any, Mapping, Protocol, Sequence

from ..config.settings import CONFIG
from ..utils.tokenizer import tokenize
from .article_models import ArticleRecord
from .db_service import dice_coefficient, generate_trigrams, jaccard_similarity


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


class ArticleRepositoryLike(Protocol):
    async def get_article(self, article_id: str) -> dict[str, Any] | None: ...


class EventBuilder:
    def __init__(
        self,
        event_repository: EventRepositoryLike,
        article_repository: ArticleRepositoryLike,
        *,
        candidate_window_hours: int = CONFIG.dedup_hours_back,
        candidate_limit: int = 100,
        title_similarity_threshold: float = CONFIG.dedup_similarity_threshold,
        candidate_statuses: Sequence[str] = ("new", "active", "updated", "escalating", "stabilizing"),
    ):
        self.event_repository = event_repository
        self.article_repository = article_repository
        self.candidate_window_hours = candidate_window_hours
        self.candidate_limit = candidate_limit
        self.title_similarity_threshold = title_similarity_threshold
        self.candidate_statuses = tuple(candidate_statuses)

    async def assign_article_to_event(
        self,
        article: ArticleRecord | Mapping[str, Any],
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

        target_event = self._pick_best_candidate(seed, candidates)
        if target_event is None:
            return await self._create_new_event(seed, anchor_time)
        return await self._attach_to_existing_event(seed, target_event, anchor_time)


    async def extract_and_persist(
        self,
        article: ArticleRecord | Mapping[str, Any],
        *,
        extracted_features: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        assigned = await self.assign_article_to_event(article)
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
        return {"event": event, "member": member, "created": True}

    async def _attach_to_existing_event(
        self,
        article: Mapping[str, Any],
        event: Mapping[str, Any],
        anchor_time: datetime,
    ) -> dict[str, Any]:
        event_id = self._text(event.get("event_id"))
        article_id = self._text(article.get("article_id"))
        if not event_id:
            raise ValueError("event_id is required for candidate event")

        current_members = await self.event_repository.list_event_members(event_id)
        has_primary = any(bool(member.get("is_primary")) for member in current_members)
        member = await self.event_repository.add_event_member(
            {
                "event_id": event_id,
                "article_id": article_id,
                "role": "supporting" if has_primary else "primary",
                "is_primary": False if has_primary else True,
                "added_at": anchor_time,
            }
        )

        article_count = max(self._safe_int(event.get("article_count")), len(current_members)) + 1
        source_count = await self._estimate_source_count(event_id, current_members, article)

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
                "status": event.get("status", "active") or "active",
                "started_at": started_at,
                "last_updated_at": anchor_time,
                "latest_article_at": latest_article_at,
                "article_count": article_count,
                "source_count": source_count,
            },
        )
        return {"event": updated_event, "member": member, "created": False}

    def _pick_best_candidate(
        self,
        article: Mapping[str, Any],
        candidates: Sequence[Mapping[str, Any]],
    ) -> Mapping[str, Any] | None:
        best: Mapping[str, Any] | None = None
        best_score = 0.0
        article_title = self._article_title(article)
        for candidate in candidates:
            score = self._title_similarity(
                article_title,
                self._text(candidate.get("canonical_title")),
            )
            if score < self.title_similarity_threshold:
                continue
            if score > best_score:
                best = candidate
                best_score = score
        return best

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

    def _build_event_id(self, article_id: str, anchor_time: datetime) -> str:
        digest = hashlib.sha1(
            f"{article_id}:{anchor_time.isoformat()}".encode("utf-8")
        ).hexdigest()[:16]
        return f"evt_{digest}"

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
    def _text(value: Any) -> str:
        if value is None:
            return ""
        if isinstance(value, str):
            return value.strip()
        return str(value).strip()


__all__ = ["EventBuilder"]
