from __future__ import annotations

from datetime import datetime
from typing import Any, Mapping, Sequence

from .repository_support import (
    ensure_pool,
    normalize_row,
    normalize_rows,
    serialize_jsonb,
)


class ArticleRepository:
    _ARTICLE_JSON_FIELDS = ("metadata",)
    _FEATURE_JSON_FIELDS = ("entities", "keywords")
    _DEDUP_JSON_FIELDS = ("reason",)

    def __init__(self, pool: Any):
        self._pool = pool

    async def create_article(self, article: Mapping[str, Any]) -> dict[str, Any]:
        pool = ensure_pool(self._pool)
        content = article.get("content", "")
        clean_content = article.get("clean_content", content)
        content_length = article.get("content_length", len(clean_content or content))
        row = await pool.fetchrow(
            """
            INSERT INTO articles (
                article_id,
                source_id,
                canonical_url,
                title,
                normalized_title,
                content,
                clean_content,
                language,
                published_at,
                ingested_at,
                tier,
                source_type,
                exact_hash,
                simhash,
                content_length,
                quality_score,
                metadata
            )
            VALUES (
                $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17
            )
            RETURNING *
            """,
            article["article_id"],
            article["source_id"],
            article["canonical_url"],
            article["title"],
            article.get("normalized_title", article["title"]),
            content,
            clean_content,
            article.get("language", ""),
            article.get("published_at"),
            article.get("ingested_at"),
            article.get("tier", 4),
            article.get("source_type", "other"),
            article.get("exact_hash", ""),
            article.get("simhash", ""),
            content_length,
            article.get("quality_score", 0),
            serialize_jsonb(article.get("metadata", {})),
        )
        return normalize_row(row, json_field_names=self._ARTICLE_JSON_FIELDS) or {}

    async def get_article(self, article_id: str) -> dict[str, Any] | None:
        pool = ensure_pool(self._pool)
        row = await pool.fetchrow(
            "SELECT * FROM articles WHERE article_id = $1",
            article_id,
        )
        return normalize_row(row, json_field_names=self._ARTICLE_JSON_FIELDS)

    async def get_articles_batch(
        self, article_ids: Sequence[str]
    ) -> dict[str, dict[str, Any]]:
        """批量获取文章，返回 article_id -> article 的映射。空 ID 或不存在的不在结果中。"""
        if not article_ids:
            return {}
        unique_ids = list(dict.fromkeys(aid for aid in article_ids if aid))
        if not unique_ids:
            return {}
        pool = ensure_pool(self._pool)
        rows = await pool.fetch(
            "SELECT * FROM articles WHERE article_id = ANY($1::text[])",
            unique_ids,
        )
        normalized = normalize_rows(
            rows, json_field_names=self._ARTICLE_JSON_FIELDS
        )
        return {row["article_id"]: row for row in normalized if row.get("article_id")}

    async def get_article_by_canonical_url(
        self, canonical_url: str
    ) -> dict[str, Any] | None:
        pool = ensure_pool(self._pool)
        row = await pool.fetchrow(
            "SELECT * FROM articles WHERE canonical_url = $1",
            canonical_url,
        )
        return normalize_row(row, json_field_names=self._ARTICLE_JSON_FIELDS)

    async def find_articles_by_exact_hash(
        self, exact_hash: str, *, limit: int = 20
    ) -> list[dict[str, Any]]:
        pool = ensure_pool(self._pool)
        rows = await pool.fetch(
            """
            SELECT *
            FROM articles
            WHERE exact_hash = $1
            ORDER BY ingested_at DESC, created_at DESC
            LIMIT $2
            """,
            exact_hash,
            limit,
        )
        return normalize_rows(rows, json_field_names=self._ARTICLE_JSON_FIELDS)

    async def list_recent_articles(
        self, *, since: datetime | None = None, limit: int = 100
    ) -> list[dict[str, Any]]:
        pool = ensure_pool(self._pool)
        if since is None:
            rows = await pool.fetch(
                """
                SELECT *
                FROM articles
                ORDER BY COALESCE(published_at, ingested_at) DESC, created_at DESC
                LIMIT $1
                """,
                limit,
            )
        else:
            rows = await pool.fetch(
                """
                SELECT *
                FROM articles
                WHERE COALESCE(published_at, ingested_at) >= $1
                ORDER BY COALESCE(published_at, ingested_at) DESC, created_at DESC
                LIMIT $2
                """,
                since,
                limit,
            )
        return normalize_rows(rows, json_field_names=self._ARTICLE_JSON_FIELDS)

    async def upsert_article_features(
        self, features: Mapping[str, Any]
    ) -> dict[str, Any]:
        pool = ensure_pool(self._pool)
        row = await pool.fetchrow(
            """
            INSERT INTO article_features (
                article_id,
                embedding_model,
                embedding_vector_id,
                language,
                simhash,
                entities,
                keywords,
                quality_score,
                feature_version
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
            ON CONFLICT (article_id) DO UPDATE SET
                embedding_model = EXCLUDED.embedding_model,
                embedding_vector_id = EXCLUDED.embedding_vector_id,
                language = EXCLUDED.language,
                simhash = EXCLUDED.simhash,
                entities = EXCLUDED.entities,
                keywords = EXCLUDED.keywords,
                quality_score = EXCLUDED.quality_score,
                feature_version = EXCLUDED.feature_version,
                updated_at = NOW()
            RETURNING *
            """,
            features["article_id"],
            features.get("embedding_model", ""),
            features.get("embedding_vector_id", ""),
            features.get("language", ""),
            features.get("simhash", ""),
            serialize_jsonb(features.get("entities", [])),
            serialize_jsonb(features.get("keywords", [])),
            features.get("quality_score", 0),
            features.get("feature_version", "v1"),
        )
        return normalize_row(row, json_field_names=self._FEATURE_JSON_FIELDS) or {}

    async def get_article_features(self, article_id: str) -> dict[str, Any] | None:
        pool = ensure_pool(self._pool)
        row = await pool.fetchrow(
            "SELECT * FROM article_features WHERE article_id = $1",
            article_id,
        )
        return normalize_row(row, json_field_names=self._FEATURE_JSON_FIELDS)

    async def create_dedup_link(self, link: Mapping[str, Any]) -> dict[str, Any]:
        pool = ensure_pool(self._pool)
        row = await pool.fetchrow(
            """
            INSERT INTO article_dedup_links (
                link_id,
                left_article_id,
                right_article_id,
                relation_type,
                confidence,
                reason
            )
            VALUES ($1, $2, $3, $4, $5, $6)
            ON CONFLICT (left_article_id, right_article_id, relation_type) DO UPDATE SET
                confidence = EXCLUDED.confidence,
                reason = EXCLUDED.reason
            RETURNING *
            """,
            link["link_id"],
            link["left_article_id"],
            link["right_article_id"],
            link["relation_type"],
            link.get("confidence", 0),
            serialize_jsonb(link.get("reason", {})),
        )
        return normalize_row(row, json_field_names=self._DEDUP_JSON_FIELDS) or {}

    async def list_dedup_links(self, article_id: str) -> list[dict[str, Any]]:
        pool = ensure_pool(self._pool)
        rows = await pool.fetch(
            """
            SELECT *
            FROM article_dedup_links
            WHERE left_article_id = $1 OR right_article_id = $1
            ORDER BY created_at DESC
            """,
            article_id,
        )
        return normalize_rows(rows, json_field_names=self._DEDUP_JSON_FIELDS)

    async def list_dedup_links_batch(
        self, article_ids: Sequence[str]
    ) -> dict[str, list[dict[str, Any]]]:
        """批量获取文章的 dedup 链接，返回 article_id -> [links] 的映射。"""
        if not article_ids:
            return {}
        unique_ids = list(dict.fromkeys(aid for aid in article_ids if aid))
        if not unique_ids:
            return {}
        pool = ensure_pool(self._pool)
        rows = await pool.fetch(
            """
            SELECT *
            FROM article_dedup_links
            WHERE left_article_id = ANY($1::text[]) OR right_article_id = ANY($1::text[])
            ORDER BY created_at DESC
            """,
            unique_ids,
        )
        normalized = normalize_rows(rows, json_field_names=self._DEDUP_JSON_FIELDS)
        result: dict[str, list[dict[str, Any]]] = {aid: [] for aid in unique_ids}
        for link in normalized:
            left = link.get("left_article_id") or ""
            right = link.get("right_article_id") or ""
            if left in result:
                result[left].append(link)
            if right in result and right != left:
                result[right].append(link)
        return result
