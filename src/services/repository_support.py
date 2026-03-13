from __future__ import annotations

import json

from typing import Any, Mapping, Sequence


def ensure_pool(pool: Any) -> Any:
    if pool is None:
        raise RuntimeError("Repository requires a connected PostgreSQL pool")
    return pool


def normalize_row(
    row: Any | None,
    *,
    json_field_names: Sequence[str] = (),
) -> dict[str, Any] | None:
    if row is None:
        return None
    return deserialize_jsonb_fields(dict(row), json_field_names)


def normalize_rows(
    rows: Sequence[Any],
    *,
    json_field_names: Sequence[str] = (),
) -> list[dict[str, Any]]:
    return [deserialize_jsonb_fields(dict(row), json_field_names) for row in rows]


def serialize_jsonb(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, default=str)


def deserialize_jsonb(value: Any) -> Any:
    current = value
    # Some historical rows were double-serialized into jsonb string payloads.
    # Iterate a few times so "\"{...}\"" eventually normalizes to mapping/list.
    for _ in range(3):
        if isinstance(current, bytes):
            text = current.decode("utf-8", errors="ignore").strip()
        elif isinstance(current, str):
            text = current.strip()
        else:
            return current

        if not text:
            return current

        try:
            current = json.loads(text)
        except json.JSONDecodeError:
            return current

    return current


def deserialize_jsonb_fields(
    fields: Mapping[str, Any],
    jsonb_field_names: Sequence[str],
) -> dict[str, Any]:
    deserialized = dict(fields)
    for field_name in jsonb_field_names:
        if field_name in deserialized:
            deserialized[field_name] = deserialize_jsonb(deserialized[field_name])
    return deserialized


def serialize_jsonb_fields(
    fields: Mapping[str, Any],
    jsonb_field_names: Sequence[str],
) -> dict[str, Any]:
    serialized = dict(fields)
    for field_name in jsonb_field_names:
        if field_name in serialized:
            serialized[field_name] = serialize_jsonb(serialized[field_name])
    return serialized


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
