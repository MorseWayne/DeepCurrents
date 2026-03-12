import json
from pathlib import Path
from typing import Any, Dict, List


FIXTURE_ROOT = (
    Path(__file__).resolve().parent.parent / "fixtures" / "event_intelligence"
)


def _load_json_fixture(filename: str, base_dir: Path | None = None) -> Any:
    fixture_dir = base_dir or FIXTURE_ROOT
    fixture_path = fixture_dir / filename
    if not fixture_path.exists():
        raise FileNotFoundError(f"Fixture not found: {fixture_path}")

    with fixture_path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def load_duplicate_pairs(base_dir: Path | None = None) -> List[Dict[str, Any]]:
    payload = _load_json_fixture("duplicate_pairs.json", base_dir=base_dir)
    if not isinstance(payload, list) or not payload:
        raise ValueError("duplicate_pairs.json must be a non-empty list")

    for item in payload:
        if item.get("expected_relation") != "duplicate":
            raise ValueError(
                "duplicate pair entries must use expected_relation=duplicate"
            )
        if "left" not in item or "right" not in item:
            raise ValueError("duplicate pair entries must include left/right articles")
    return payload


def load_same_event_pairs(base_dir: Path | None = None) -> List[Dict[str, Any]]:
    payload = _load_json_fixture("same_event_pairs.json", base_dir=base_dir)
    if not isinstance(payload, list) or not payload:
        raise ValueError("same_event_pairs.json must be a non-empty list")

    for item in payload:
        if item.get("expected_relation") != "same_event":
            raise ValueError("same-event entries must use expected_relation=same_event")
        if "left" not in item or "right" not in item:
            raise ValueError("same-event entries must include left/right articles")
    return payload


def load_top_event_relevance(base_dir: Path | None = None) -> Dict[str, Any]:
    payload = _load_json_fixture("top_event_relevance.json", base_dir=base_dir)
    if not isinstance(payload, dict):
        raise ValueError("top_event_relevance.json must be an object")

    candidates = payload.get("candidates")
    if not isinstance(candidates, list) or not candidates:
        raise ValueError("top_event_relevance.json must contain non-empty candidates")

    for item in candidates:
        if "event_id" not in item or "expected_rank" not in item:
            raise ValueError(
                "top relevance candidates must include event_id and expected_rank"
            )
    return payload
