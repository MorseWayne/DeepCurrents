from __future__ import annotations

from datetime import date
from typing import Any, Mapping, Sequence

from .repository_support import ensure_pool, normalize_row, normalize_rows


class BriefRepository:
    def __init__(self, pool: Any):
        self._pool = pool

    async def upsert_event_brief(self, brief: Mapping[str, Any]) -> dict[str, Any]:
        pool = ensure_pool(self._pool)
        row = await pool.fetchrow(
            """
            INSERT INTO event_briefs (
                brief_id,
                event_id,
                version,
                summary,
                brief_json,
                model
            )
            VALUES ($1, $2, $3, $4, $5, $6)
            ON CONFLICT (event_id, version) DO UPDATE SET
                summary = EXCLUDED.summary,
                brief_json = EXCLUDED.brief_json,
                model = EXCLUDED.model,
                updated_at = NOW()
            RETURNING *
            """,
            brief["brief_id"],
            brief["event_id"],
            brief.get("version", "v1"),
            brief.get("summary", ""),
            brief.get("brief_json", {}),
            brief.get("model", ""),
        )
        return normalize_row(row) or {}

    async def get_event_brief(
        self, event_id: str, *, version: str = "v1"
    ) -> dict[str, Any] | None:
        pool = ensure_pool(self._pool)
        row = await pool.fetchrow(
            "SELECT * FROM event_briefs WHERE event_id = $1 AND version = $2",
            event_id,
            version,
        )
        return normalize_row(row)

    async def list_event_briefs(
        self, event_ids: Sequence[str], *, version: str = "v1"
    ) -> list[dict[str, Any]]:
        if not event_ids:
            return []
        pool = ensure_pool(self._pool)
        rows = await pool.fetch(
            """
            SELECT *
            FROM event_briefs
            WHERE event_id = ANY($1::text[]) AND version = $2
            ORDER BY created_at DESC
            """,
            list(event_ids),
            version,
        )
        return normalize_rows(rows)

    async def upsert_theme_brief(self, brief: Mapping[str, Any]) -> dict[str, Any]:
        pool = ensure_pool(self._pool)
        row = await pool.fetchrow(
            """
            INSERT INTO theme_briefs (
                theme_brief_id,
                theme_key,
                report_date,
                version,
                brief_json
            )
            VALUES ($1, $2, $3, $4, $5)
            ON CONFLICT (theme_key, report_date, version) DO UPDATE SET
                brief_json = EXCLUDED.brief_json,
                updated_at = NOW()
            RETURNING *
            """,
            brief["theme_brief_id"],
            brief["theme_key"],
            brief.get("report_date"),
            brief.get("version", "v1"),
            brief.get("brief_json", {}),
        )
        return normalize_row(row) or {}

    async def get_theme_brief(
        self,
        theme_key: str,
        report_date: date | None,
        *,
        version: str = "v1",
    ) -> dict[str, Any] | None:
        pool = ensure_pool(self._pool)
        row = await pool.fetchrow(
            """
            SELECT *
            FROM theme_briefs
            WHERE theme_key = $1 AND report_date IS NOT DISTINCT FROM $2 AND version = $3
            """,
            theme_key,
            report_date,
            version,
        )
        return normalize_row(row)

    async def list_theme_briefs(
        self, report_date: date | None, *, version: str = "v1"
    ) -> list[dict[str, Any]]:
        pool = ensure_pool(self._pool)
        rows = await pool.fetch(
            """
            SELECT *
            FROM theme_briefs
            WHERE report_date IS NOT DISTINCT FROM $1 AND version = $2
            ORDER BY theme_key ASC
            """,
            report_date,
            version,
        )
        return normalize_rows(rows)
