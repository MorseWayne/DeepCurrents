from __future__ import annotations

from typing import Any, Mapping, Sequence


def ensure_pool(pool: Any) -> Any:
    if pool is None:
        raise RuntimeError("Repository requires a connected PostgreSQL pool")
    return pool


def normalize_row(row: Any | None) -> dict[str, Any] | None:
    if row is None:
        return None
    return dict(row)


def normalize_rows(rows: Sequence[Any]) -> list[dict[str, Any]]:
    return [dict(row) for row in rows]


def build_update_fields(
    fields: Mapping[str, Any],
    allowed_fields: Sequence[str],
    *,
    start_index: int = 2,
) -> tuple[list[str], list[Any]]:
    filtered = [(key, value) for key, value in fields.items() if key in allowed_fields]
    if not filtered:
        raise ValueError("update requires at least one allowed field")

    assignments = [
        f"{field_name} = ${offset}"
        for offset, (field_name, _) in enumerate(filtered, start=start_index)
    ]
    values = [value for _, value in filtered]
    return assignments, values
