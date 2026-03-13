from __future__ import annotations

from datetime import datetime
from typing import Any, Mapping, Sequence

from .repository_support import (
    build_update_fields,
    ensure_pool,
    normalize_row,
    normalize_rows,
)


class EventRepository:
    _EVENT_UPDATE_FIELDS: Sequence[str] = (
        "status",
        "canonical_title",
        "summary",
        "primary_region",
        "event_type",
        "started_at",
        "last_updated_at",
        "latest_article_at",
        "article_count",
        "source_count",
        "metadata",
    )

    def __init__(self, pool: Any):
        self._pool = pool

    async def create_event(self, event: Mapping[str, Any]) -> dict[str, Any]:
        pool = ensure_pool(self._pool)
        row = await pool.fetchrow(
            """
            INSERT INTO events (
                event_id,
                status,
                canonical_title,
                summary,
                primary_region,
                event_type,
                started_at,
                last_updated_at,
                latest_article_at,
                article_count,
                source_count,
                metadata
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12)
            RETURNING *
            """,
            event["event_id"],
            event["status"],
            event["canonical_title"],
            event.get("summary", ""),
            event.get("primary_region", ""),
            event.get("event_type", ""),
            event.get("started_at"),
            event.get("last_updated_at"),
            event.get("latest_article_at"),
            event.get("article_count", 0),
            event.get("source_count", 0),
            event.get("metadata", {}),
        )
        return normalize_row(row) or {}

    async def get_event(self, event_id: str) -> dict[str, Any] | None:
        pool = ensure_pool(self._pool)
        row = await pool.fetchrow("SELECT * FROM events WHERE event_id = $1", event_id)
        return normalize_row(row)

    async def update_event(
        self, event_id: str, fields: Mapping[str, Any]
    ) -> dict[str, Any]:
        pool = ensure_pool(self._pool)
        assignments, values = build_update_fields(
            fields,
            self._EVENT_UPDATE_FIELDS,
            start_index=2,
        )
        row = await pool.fetchrow(
            f"""
            UPDATE events
            SET {", ".join(assignments)}, updated_at = NOW()
            WHERE event_id = $1
            RETURNING *
            """,
            event_id,
            *values,
        )
        return normalize_row(row) or {}

    async def list_recent_events(
        self,
        *,
        statuses: Sequence[str] | None = None,
        since: datetime | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        pool = ensure_pool(self._pool)
        conditions: list[str] = []
        values: list[Any] = []
        next_index = 1

        if statuses:
            conditions.append(f"status = ANY(${next_index}::text[])")
            values.append(list(statuses))
            next_index += 1

        if since is not None:
            conditions.append(
                f"COALESCE(latest_article_at, updated_at) >= ${next_index}"
            )
            values.append(since)
            next_index += 1

        limit_index = next_index
        values.append(limit)
        query = "SELECT * FROM events"
        if conditions:
            query += " WHERE " + " AND ".join(conditions)
        query += f" ORDER BY COALESCE(latest_article_at, updated_at) DESC NULLS LAST, created_at DESC LIMIT ${limit_index}"
        rows = await pool.fetch(query, *values)
        return normalize_rows(rows)

    async def add_event_member(self, member: Mapping[str, Any]) -> dict[str, Any]:
        pool = ensure_pool(self._pool)
        row = await pool.fetchrow(
            """
            INSERT INTO event_members (
                event_id,
                article_id,
                role,
                is_primary,
                added_at
            )
            VALUES ($1, $2, $3, $4, $5)
            ON CONFLICT (event_id, article_id) DO UPDATE SET
                role = EXCLUDED.role,
                is_primary = EXCLUDED.is_primary,
                added_at = EXCLUDED.added_at
            RETURNING *
            """,
            member["event_id"],
            member["article_id"],
            member.get("role", "supporting"),
            member.get("is_primary", False),
            member.get("added_at"),
        )
        return normalize_row(row) or {}

    async def list_event_members(self, event_id: str) -> list[dict[str, Any]]:
        pool = ensure_pool(self._pool)
        rows = await pool.fetch(
            "SELECT * FROM event_members WHERE event_id = $1 ORDER BY added_at ASC",
            event_id,
        )
        return normalize_rows(rows)

    async def upsert_event_score(self, score: Mapping[str, Any]) -> dict[str, Any]:
        pool = ensure_pool(self._pool)
        row = await pool.fetchrow(
            """
            INSERT INTO event_scores (
                event_id,
                profile,
                threat_score,
                market_impact_score,
                novelty_score,
                corroboration_score,
                source_quality_score,
                velocity_score,
                uncertainty_score,
                total_score,
                payload,
                scored_at
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12)
            ON CONFLICT (event_id, profile) DO UPDATE SET
                threat_score = EXCLUDED.threat_score,
                market_impact_score = EXCLUDED.market_impact_score,
                novelty_score = EXCLUDED.novelty_score,
                corroboration_score = EXCLUDED.corroboration_score,
                source_quality_score = EXCLUDED.source_quality_score,
                velocity_score = EXCLUDED.velocity_score,
                uncertainty_score = EXCLUDED.uncertainty_score,
                total_score = EXCLUDED.total_score,
                payload = EXCLUDED.payload,
                scored_at = EXCLUDED.scored_at
            RETURNING *
            """,
            score["event_id"],
            score["profile"],
            score.get("threat_score", 0),
            score.get("market_impact_score", 0),
            score.get("novelty_score", 0),
            score.get("corroboration_score", 0),
            score.get("source_quality_score", 0),
            score.get("velocity_score", 0),
            score.get("uncertainty_score", 0),
            score.get("total_score", 0),
            score.get("payload", {}),
            score.get("scored_at"),
        )
        return normalize_row(row) or {}

    async def get_event_score(
        self, event_id: str, profile: str
    ) -> dict[str, Any] | None:
        pool = ensure_pool(self._pool)
        row = await pool.fetchrow(
            "SELECT * FROM event_scores WHERE event_id = $1 AND profile = $2",
            event_id,
            profile,
        )
        return normalize_row(row)

    async def list_event_scores(self, event_id: str) -> list[dict[str, Any]]:
        pool = ensure_pool(self._pool)
        rows = await pool.fetch(
            """
            SELECT *
            FROM event_scores
            WHERE event_id = $1
            ORDER BY total_score DESC, scored_at DESC, profile ASC
            """,
            event_id,
        )
        return normalize_rows(rows)

    async def record_state_transition(
        self, transition: Mapping[str, Any]
    ) -> dict[str, Any]:
        pool = ensure_pool(self._pool)
        row = await pool.fetchrow(
            """
            INSERT INTO event_state_transitions (
                transition_id,
                event_id,
                from_state,
                to_state,
                trigger_article_id,
                reason,
                metadata
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7)
            RETURNING *
            """,
            transition["transition_id"],
            transition["event_id"],
            transition.get("from_state", ""),
            transition["to_state"],
            transition.get("trigger_article_id"),
            transition.get("reason", ""),
            transition.get("metadata", {}),
        )
        return normalize_row(row) or {}

    async def list_event_state_transitions(self, event_id: str) -> list[dict[str, Any]]:
        pool = ensure_pool(self._pool)
        rows = await pool.fetch(
            """
            SELECT *
            FROM event_state_transitions
            WHERE event_id = $1
            ORDER BY created_at ASC
            """,
            event_id,
        )
        return normalize_rows(rows)
