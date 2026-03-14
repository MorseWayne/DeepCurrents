from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta
from typing import Any, Mapping, Protocol, Sequence

from loguru import logger

from ..config.settings import CONFIG
from ..utils.text_similarity import (
    dice_coefficient,
    generate_trigrams,
    jaccard_similarity,
)
from ..utils.tokenizer import tokenize
from .article_models import ArticleRecord

# ── Lazy optional: datasketch (MinHash+LSH near-dedup) ──
_datasketch: Any = None


def _ensure_datasketch() -> Any:
    global _datasketch
    if _datasketch is None:
        try:
            import datasketch as _ds

            _datasketch = _ds
        except ImportError:
            _datasketch = False
            logger.debug("datasketch not installed; MinHash dedup disabled")
    return _datasketch


class ArticleRepositoryLike(Protocol):
    async def find_articles_by_exact_hash(
        self, exact_hash: str, *, limit: int = 20
    ) -> list[dict[str, Any]]: ...

    async def list_recent_articles(
        self, *, since: datetime | None = None, limit: int = 100
    ) -> list[dict[str, Any]]: ...

    async def get_article_features(self, article_id: str) -> dict[str, Any] | None: ...

    async def create_dedup_link(self, link: Mapping[str, Any]) -> dict[str, Any]: ...


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


class SemanticDeduper:
    def __init__(
        self,
        article_repository: ArticleRepositoryLike,
        vector_store: VectorStoreLike | None,
        *,
        recent_hours: int = CONFIG.dedup_hours_back,
        recent_limit: int = 100,
        exact_limit: int = 20,
        semantic_limit: int = 8,
        near_title_threshold: float = CONFIG.dedup_similarity_threshold,
        near_simhash_threshold: float = 0.9,
        semantic_score_threshold: float = 0.82,
        semantic_strong_score_threshold: float = 0.92,
        vector_collection: str = "article_features",
        minhash_threshold: float = 0.5,
        minhash_num_perm: int = 128,
    ):
        self.article_repository = article_repository
        self.vector_store = vector_store
        self.recent_hours = recent_hours
        self.recent_limit = recent_limit
        self.exact_limit = exact_limit
        self.semantic_limit = semantic_limit
        self.near_title_threshold = near_title_threshold
        self.near_simhash_threshold = near_simhash_threshold
        self.semantic_score_threshold = semantic_score_threshold
        self.semantic_strong_score_threshold = semantic_strong_score_threshold
        self.vector_collection = vector_collection
        self.minhash_threshold = minhash_threshold
        self.minhash_num_perm = minhash_num_perm

    async def link_cheap_duplicates(
        self, article: ArticleRecord | Mapping[str, Any]
    ) -> list[dict[str, Any]]:
        seed = self._coerce_article(article)
        links = []
        exact_links = await self._link_exact_duplicates(seed)
        links.extend(exact_links)
        seed_id = self._text(seed.get("article_id"))
        matched_ids: set[str] = set()
        for link in exact_links:
            left_id = self._text(link.get("left_article_id"))
            right_id = self._text(link.get("right_article_id"))
            if left_id and left_id != seed_id:
                matched_ids.add(left_id)
            if right_id and right_id != seed_id:
                matched_ids.add(right_id)
        minhash_links = await self._link_minhash_duplicates(
            seed, skip_candidate_ids=matched_ids
        )
        links.extend(minhash_links)
        for link in minhash_links:
            left_id = self._text(link.get("left_article_id"))
            right_id = self._text(link.get("right_article_id"))
            if left_id and left_id != seed_id:
                matched_ids.add(left_id)
            if right_id and right_id != seed_id:
                matched_ids.add(right_id)
        links.extend(
            await self._link_near_duplicates(
                seed,
                skip_candidate_ids=matched_ids,
            )
        )
        return links

    async def link_semantic_duplicates(
        self,
        article: ArticleRecord | Mapping[str, Any],
        *,
        embedding: Sequence[float] | None,
    ) -> list[dict[str, Any]]:
        if self.vector_store is None or not embedding:
            return []

        seed = self._coerce_article(article)
        source_features = (
            await self.article_repository.get_article_features(seed["article_id"]) or {}
        )
        recent_candidates = await self.article_repository.list_recent_articles(
            since=self._candidate_since(seed),
            limit=self.recent_limit,
        )
        recent_by_id = {
            candidate.get("article_id"): candidate
            for candidate in recent_candidates
            if candidate.get("article_id")
            and candidate.get("article_id") != seed["article_id"]
        }
        if not recent_by_id:
            return []

        scored_points = await self.vector_store.query_similar_points(
            self.vector_collection,
            query_vector=embedding,
            limit=self.semantic_limit,
            score_threshold=self.semantic_score_threshold,
            with_payload=True,
        )

        links = []
        seen_ids: set[str] = set()
        for point in scored_points:
            payload = point.get("payload") or {}
            candidate_id = self._text(payload.get("article_id") or point.get("id"))
            if (
                not candidate_id
                or candidate_id == seed["article_id"]
                or candidate_id in seen_ids
                or candidate_id not in recent_by_id
            ):
                continue

            seen_ids.add(candidate_id)
            score = self._safe_float(point.get("score"))
            candidate_features = (
                await self.article_repository.get_article_features(candidate_id) or {}
            )
            entity_overlap = self._entity_overlap(
                source_features, candidate_features, payload
            )
            if score < self.semantic_score_threshold:
                continue
            if entity_overlap <= 0 and score < self.semantic_strong_score_threshold:
                continue

            confidence = round(
                min(1.0, (score + max(entity_overlap, 0.0)) / 2)
                if entity_overlap > 0
                else score,
                3,
            )
            links.append(
                await self._create_link(
                    seed["article_id"],
                    candidate_id,
                    relation_type="semantic",
                    confidence=confidence,
                    reason={
                        "score": round(score, 3),
                        "entity_overlap": round(entity_overlap, 3),
                    },
                )
            )
        return links

    async def _link_exact_duplicates(
        self, seed: Mapping[str, Any]
    ) -> list[dict[str, Any]]:
        exact_hash = self._text(seed.get("exact_hash"))
        if not exact_hash:
            return []

        candidates = await self.article_repository.find_articles_by_exact_hash(
            exact_hash,
            limit=self.exact_limit,
        )
        links = []
        for candidate in candidates:
            candidate_id = self._text(candidate.get("article_id"))
            if not candidate_id or candidate_id == seed["article_id"]:
                continue
            links.append(
                await self._create_link(
                    seed["article_id"],
                    candidate_id,
                    relation_type="exact",
                    confidence=1.0,
                    reason={"exact_hash": exact_hash},
                )
            )
        return links

    async def _link_near_duplicates(
        self,
        seed: Mapping[str, Any],
        *,
        skip_candidate_ids: set[str] | None = None,
    ) -> list[dict[str, Any]]:
        candidates = await self.article_repository.list_recent_articles(
            since=self._candidate_since(seed),
            limit=self.recent_limit,
        )
        links = []
        seen_ids: set[str] = set()
        for candidate in candidates:
            candidate_id = self._text(candidate.get("article_id"))
            if (
                not candidate_id
                or candidate_id == seed["article_id"]
                or (skip_candidate_ids and candidate_id in skip_candidate_ids)
                or candidate_id in seen_ids
            ):
                continue
            seen_ids.add(candidate_id)

            simhash_similarity = self._simhash_similarity(
                seed.get("simhash"),
                candidate.get("simhash"),
            )
            title_similarity = self._title_similarity(seed, candidate)
            if not self._is_near_duplicate(simhash_similarity, title_similarity):
                continue

            links.append(
                await self._create_link(
                    seed["article_id"],
                    candidate_id,
                    relation_type="near",
                    confidence=round(max(simhash_similarity, title_similarity), 3),
                    reason={
                        "simhash_similarity": round(simhash_similarity, 3),
                        "title_similarity": round(title_similarity, 3),
                    },
                )
            )
        return links

    async def _link_minhash_duplicates(
        self,
        seed: Mapping[str, Any],
        *,
        skip_candidate_ids: set[str] | None = None,
    ) -> list[dict[str, Any]]:
        ds = _ensure_datasketch()
        if not ds:
            return []

        seed_shingles = self._content_shingles(seed)
        if not seed_shingles:
            return []

        candidates = await self.article_repository.list_recent_articles(
            since=self._candidate_since(seed),
            limit=self.recent_limit,
        )
        if not candidates:
            return []

        seed_minhash = self._compute_minhash(ds, seed_shingles, self.minhash_num_perm)
        lsh = ds.MinHashLSH(
            threshold=self.minhash_threshold, num_perm=self.minhash_num_perm
        )

        candidate_map: dict[str, Mapping[str, Any]] = {}
        candidate_minhashes: dict[str, Any] = {}
        for candidate in candidates:
            cid = self._text(candidate.get("article_id"))
            if (
                not cid
                or cid == seed.get("article_id")
                or (skip_candidate_ids and cid in skip_candidate_ids)
            ):
                continue
            shingles = self._content_shingles(candidate)
            if not shingles:
                continue
            mh = self._compute_minhash(ds, shingles, self.minhash_num_perm)
            try:
                lsh.insert(cid, mh)
            except ValueError:
                continue
            candidate_map[cid] = candidate
            candidate_minhashes[cid] = mh

        try:
            hit_ids: list[str] = lsh.query(seed_minhash)
        except Exception:
            return []

        links: list[dict[str, Any]] = []
        for cid in hit_ids:
            if cid not in candidate_minhashes:
                continue
            jaccard_est = seed_minhash.jaccard(candidate_minhashes[cid])
            if jaccard_est < self.minhash_threshold:
                continue
            links.append(
                await self._create_link(
                    self._text(seed.get("article_id")),
                    cid,
                    relation_type="minhash",
                    confidence=round(jaccard_est, 3),
                    reason={
                        "minhash_jaccard": round(jaccard_est, 3),
                        "num_perm": self.minhash_num_perm,
                    },
                )
            )
        return links

    def _content_shingles(
        self, article: Mapping[str, Any], shingle_size: int = 3
    ) -> set[str]:
        text = self._text(
            article.get("clean_content")
            or article.get("content")
            or article.get("normalized_title")
            or article.get("title")
        )
        if not text:
            return set()
        tokens = list(tokenize(text))
        if len(tokens) < shingle_size:
            return set(tokens) if tokens else set()
        return {
            " ".join(tokens[i : i + shingle_size])
            for i in range(len(tokens) - shingle_size + 1)
        }

    @staticmethod
    def _compute_minhash(ds: Any, shingles: set[str], num_perm: int = 128) -> Any:
        mh = ds.MinHash(num_perm=num_perm)
        for s in shingles:
            mh.update(s.encode("utf-8"))
        return mh

    def _coerce_article(
        self, article: ArticleRecord | Mapping[str, Any]
    ) -> dict[str, Any]:
        if isinstance(article, ArticleRecord):
            return article.to_feature_seed()
        if not isinstance(article, Mapping):
            raise TypeError("article must be an ArticleRecord or mapping")
        return dict(article)

    def _candidate_since(self, article: Mapping[str, Any]) -> datetime | None:
        anchor = self._article_time(article)
        if anchor is None:
            return None
        return anchor - timedelta(hours=self.recent_hours)

    def _article_time(self, article: Mapping[str, Any]) -> datetime | None:
        for key in ("published_at", "ingested_at"):
            value = article.get(key)
            if isinstance(value, datetime):
                if value.tzinfo is None:
                    return value.replace(tzinfo=UTC)
                return value
        return datetime.now(UTC)

    def _title_similarity(
        self,
        left: Mapping[str, Any],
        right: Mapping[str, Any],
    ) -> float:
        left_title = self._text(left.get("normalized_title") or left.get("title"))
        right_title = self._text(right.get("normalized_title") or right.get("title"))
        if not left_title or not right_title:
            return 0.0
        if left_title == right_title:
            return 1.0
        token_score = jaccard_similarity(tokenize(left_title), tokenize(right_title))
        trigram_score = dice_coefficient(
            generate_trigrams(left_title),
            generate_trigrams(right_title),
        )
        return max(token_score, trigram_score)

    def _is_near_duplicate(
        self,
        simhash_similarity: float,
        title_similarity: float,
    ) -> bool:
        if simhash_similarity >= self.near_simhash_threshold:
            return True
        return (
            title_similarity >= self.near_title_threshold and simhash_similarity >= 0.65
        )

    def _simhash_similarity(self, left: Any, right: Any) -> float:
        left_text = self._text(left)
        right_text = self._text(right)
        if not left_text or not right_text:
            return 0.0
        try:
            left_value = int(left_text, 16)
            right_value = int(right_text, 16)
        except ValueError:
            return 0.0
        distance = (left_value ^ right_value).bit_count()
        bits = max(len(left_text), len(right_text), 1) * 4
        return max(0.0, 1 - (distance / bits))

    def _entity_overlap(
        self,
        source_features: Mapping[str, Any],
        candidate_features: Mapping[str, Any],
        payload: Mapping[str, Any],
    ) -> float:
        left_entities = self._entity_names(
            source_features.get("entities") or payload.get("entities")
        )
        right_entities = self._entity_names(
            candidate_features.get("entities") or payload.get("entities")
        )
        if not left_entities or not right_entities:
            return 0.0
        return jaccard_similarity(left_entities, right_entities)

    def _entity_names(self, entities: Any) -> set[str]:
        if not entities:
            return set()
        if isinstance(entities, Mapping):
            name = self._text(
                entities.get("name") or entities.get("value") or entities.get("text")
            )
            return {name.casefold()} if name else set()
        if isinstance(entities, str):
            return {entities.casefold()} if entities else set()
        if isinstance(entities, Sequence) and not isinstance(
            entities, (bytes, bytearray)
        ):
            names: set[str] = set()
            for item in entities:
                names.update(self._entity_names(item))
            return names
        text = self._text(entities)
        return {text.casefold()} if text else set()

    async def _create_link(
        self,
        left_article_id: str,
        right_article_id: str,
        *,
        relation_type: str,
        confidence: float,
        reason: Mapping[str, Any],
    ) -> dict[str, Any]:
        left_id, right_id = sorted((left_article_id, right_article_id))
        digest = hashlib.sha1(
            f"{relation_type}:{left_id}:{right_id}".encode("utf-8")
        ).hexdigest()[:16]
        return await self.article_repository.create_dedup_link(
            {
                "link_id": f"dup_{digest}",
                "left_article_id": left_id,
                "right_article_id": right_id,
                "relation_type": relation_type,
                "confidence": confidence,
                "reason": self._normalize_reason(reason),
            }
        )

    @staticmethod
    def _normalize_reason(reason: Mapping[str, Any]) -> dict[str, Any]:
        return json.loads(json.dumps(dict(reason), default=str))

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


__all__ = ["SemanticDeduper"]
