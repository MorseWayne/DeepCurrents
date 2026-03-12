from __future__ import annotations

from datetime import date
from typing import Any, Mapping, Sequence

from .repository_support import (
    build_update_fields,
    ensure_pool,
    normalize_row,
    normalize_rows,
)


class ReportRepository:
    _REPORT_UPDATE_FIELDS: Sequence[str] = (
        "profile",
        "report_date",
        "status",
        "budget_tokens",
        "input_event_count",
        "selected_event_count",
        "metadata",
    )

    def __init__(self, pool: Any):
        self._pool = pool

    async def create_report_run(self, report_run: Mapping[str, Any]) -> dict[str, Any]:
        pool = ensure_pool(self._pool)
        row = await pool.fetchrow(
            """
            INSERT INTO report_runs (
                report_run_id,
                profile,
                report_date,
                status,
                budget_tokens,
                input_event_count,
                selected_event_count,
                metadata
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
            RETURNING *
            """,
            report_run["report_run_id"],
            report_run["profile"],
            report_run.get("report_date"),
            report_run.get("status", "pending"),
            report_run.get("budget_tokens", 0),
            report_run.get("input_event_count", 0),
            report_run.get("selected_event_count", 0),
            report_run.get("metadata", {}),
        )
        return normalize_row(row) or {}

    async def get_report_run(self, report_run_id: str) -> dict[str, Any] | None:
        pool = ensure_pool(self._pool)
        row = await pool.fetchrow(
            "SELECT * FROM report_runs WHERE report_run_id = $1",
            report_run_id,
        )
        return normalize_row(row)

    async def get_report_run_by_date(
        self, profile: str, report_date: date | None
    ) -> dict[str, Any] | None:
        pool = ensure_pool(self._pool)
        row = await pool.fetchrow(
            """
            SELECT *
            FROM report_runs
            WHERE profile = $1 AND report_date IS NOT DISTINCT FROM $2
            """,
            profile,
            report_date,
        )
        return normalize_row(row)

    async def get_latest_report_run(
        self, profile: str, *, status: str = "completed"
    ) -> dict[str, Any] | None:
        pool = ensure_pool(self._pool)
        row = await pool.fetchrow(
            """
            SELECT *
            FROM report_runs
            WHERE profile = $1 AND status = $2
            ORDER BY report_date DESC NULLS LAST, created_at DESC
            LIMIT 1
            """,
            profile,
            status,
        )
        return normalize_row(row)

    async def update_report_run(
        self, report_run_id: str, fields: Mapping[str, Any]
    ) -> dict[str, Any]:
        pool = ensure_pool(self._pool)
        assignments, values = build_update_fields(
            fields,
            self._REPORT_UPDATE_FIELDS,
            start_index=2,
        )
        row = await pool.fetchrow(
            f"""
            UPDATE report_runs
            SET {", ".join(assignments)}, updated_at = NOW()
            WHERE report_run_id = $1
            RETURNING *
            """,
            report_run_id,
            *values,
        )
        return normalize_row(row) or {}

    async def replace_report_event_links(
        self, report_run_id: str, links: Sequence[Mapping[str, Any]]
    ) -> list[dict[str, Any]]:
        pool = ensure_pool(self._pool)
        inserted_rows: list[dict[str, Any]] = []
        async with pool.acquire() as connection:
            async with connection.transaction():
                await connection.execute(
                    "DELETE FROM report_event_links WHERE report_run_id = $1",
                    report_run_id,
                )
                for link in links:
                    row = await connection.fetchrow(
                        """
                        INSERT INTO report_event_links (
                            report_run_id,
                            event_id,
                            rank,
                            included,
                            rationale
                        )
                        VALUES ($1, $2, $3, $4, $5)
                        RETURNING *
                        """,
                        report_run_id,
                        link["event_id"],
                        link.get("rank", 0),
                        link.get("included", True),
                        link.get("rationale", ""),
                    )
                    normalized = normalize_row(row)
                    if normalized is not None:
                        inserted_rows.append(normalized)
        return inserted_rows

    async def list_report_event_links(self, report_run_id: str) -> list[dict[str, Any]]:
        pool = ensure_pool(self._pool)
        rows = await pool.fetch(
            """
            SELECT *
            FROM report_event_links
            WHERE report_run_id = $1
            ORDER BY rank ASC, created_at ASC
            """,
            report_run_id,
        )
        return normalize_rows(rows)
