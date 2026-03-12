from pathlib import Path

import pytest

from tests.evaluation.fixture_loader import (
    FIXTURE_ROOT,
    load_duplicate_pairs,
    load_same_event_pairs,
    load_top_event_relevance,
)


def test_duplicate_pairs_fixture_loads():
    pairs = load_duplicate_pairs()

    assert FIXTURE_ROOT.exists()
    assert len(pairs) >= 2
    assert pairs[0]["expected_relation"] == "duplicate"
    assert "canonical_url" in pairs[0]["left"]


def test_same_event_pairs_fixture_loads():
    pairs = load_same_event_pairs()

    assert len(pairs) >= 2
    assert pairs[0]["expected_relation"] == "same_event"
    assert "title" in pairs[0]["right"]


def test_top_event_relevance_fixture_loads():
    payload = load_top_event_relevance()

    assert payload["query_id"] == "top-2026-03-13-am"
    assert payload["candidates"][0]["expected_rank"] == 1


def test_missing_fixture_raises(tmp_path: Path):
    with pytest.raises(FileNotFoundError):
        load_duplicate_pairs(base_dir=tmp_path)


def test_invalid_duplicate_fixture_raises(tmp_path: Path):
    invalid_path = tmp_path / "duplicate_pairs.json"
    invalid_path.write_text('[{"expected_relation": "same_event"}]', encoding="utf-8")

    with pytest.raises(ValueError):
        load_duplicate_pairs(base_dir=tmp_path)
