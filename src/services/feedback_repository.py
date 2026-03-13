from __future__ import annotations

from typing import Any, Mapping

from .repository_support import (
    ensure_pool,
    normalize_row,
    normalize_rows,
    serialize_jsonb,
)


class FeedbackRepository:
    _JSON_FIELDS = ("label_value",)

    def __init__(self, pool: Any):
        self._pool = pool

    async def create_label(self, label: Mapping[str, Any]) -> dict[str, Any]:
        pool = ensure_pool(self._pool)
        row = await pool.fetchrow(
            """
            INSERT INTO evaluation_labels (
                label_id,
                label_type,
                subject_id,
                label_value,
                source,
                notes
            )
            VALUES ($1, $2, $3, $4, $5, $6)
            RETURNING *
            """,
            label["label_id"],
            label["label_type"],
            label["subject_id"],
            serialize_jsonb(label.get("label_value", {})),
            label.get("source", "manual"),
            label.get("notes", ""),
        )
        return normalize_row(row, json_field_names=self._JSON_FIELDS) or {}

    async def list_labels(
        self,
        *,
        label_type: str | None = None,
        subject_id: str | None = None,
        source: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        pool = ensure_pool(self._pool)
        clauses: list[str] = []
        values: list[Any] = []

        if label_type:
            values.append(label_type)
            clauses.append(f"label_type = ${len(values)}")
        if subject_id:
            values.append(subject_id)
            clauses.append(f"subject_id = ${len(values)}")
        if source:
            values.append(source)
            clauses.append(f"source = ${len(values)}")

        where_sql = ""
        if clauses:
            where_sql = "WHERE " + " AND ".join(clauses)

        values.append(max(int(limit), 0))
        rows = await pool.fetch(
            f"""
            SELECT *
            FROM evaluation_labels
            {where_sql}
            ORDER BY created_at DESC, label_id DESC
            LIMIT ${len(values)}
            """,
            *values,
        )
        return normalize_rows(rows, json_field_names=self._JSON_FIELDS)


__all__ = ["FeedbackRepository"]
