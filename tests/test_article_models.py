from __future__ import annotations

from datetime import datetime, timezone

import pytest

from src.services.article_models import ArticleRecord


def test_article_record_requires_core_fields():
    with pytest.raises(ValueError, match="canonical_url"):
        ArticleRecord(
            article_id="art_1",
            source_id="reuters",
            canonical_url="   ",
            title="Headline",
        )


def test_article_record_applies_safe_defaults_and_derives_content_length():
    record = ArticleRecord(
        article_id="art_1",
        source_id="reuters",
        canonical_url="https://example.com/a",
        title="Headline",
        content="raw body",
    )

    assert record.normalized_title == "Headline"
    assert record.clean_content == "raw body"
    assert record.content_length == len("raw body")
    assert record.tier == 4
    assert record.source_type == "other"
    assert record.metadata == {}


def test_article_record_validates_tier_and_metadata_types():
    with pytest.raises(ValueError, match="tier"):
        ArticleRecord(
            article_id="art_1",
            source_id="reuters",
            canonical_url="https://example.com/a",
            title="Headline",
            tier=5,
        )

    with pytest.raises(TypeError, match="tier"):
        ArticleRecord(
            article_id="art_1",
            source_id="reuters",
            canonical_url="https://example.com/a",
            title="Headline",
            tier=True,
        )

    with pytest.raises(TypeError, match="metadata"):
        ArticleRecord.from_mapping(
            {
                "article_id": "art_1",
                "source_id": "reuters",
                "canonical_url": "https://example.com/a",
                "title": "Headline",
                "metadata": ["bad"],
            }
        )


def test_article_record_from_mapping_supports_repository_and_legacy_source_type_keys():
    record = ArticleRecord.from_mapping(
        {
            "article_id": "art_1",
            "source_id": "reuters",
            "canonical_url": "https://example.com/a",
            "title": "Headline",
            "sourceType": "wire",
        }
    )

    assert record.source_type == "wire"
    assert record.to_article_payload()["source_type"] == "wire"


def test_article_record_round_trips_repository_row_to_payload():
    published_at = datetime(2026, 3, 13, 8, 0, tzinfo=timezone.utc)
    row = {
        "article_id": "art_1",
        "source_id": "reuters",
        "canonical_url": "https://example.com/a",
        "title": "Headline",
        "normalized_title": "headline",
        "content": "raw",
        "clean_content": "clean",
        "language": "en",
        "published_at": published_at,
        "tier": 2,
        "source_type": "wire",
        "exact_hash": "exact-1",
        "simhash": "sim-1",
        "content_length": 5,
        "quality_score": 0.75,
        "metadata": {"region": "us"},
    }

    record = ArticleRecord.from_repository_row(row)
    payload = record.to_article_payload()

    assert payload["article_id"] == "art_1"
    assert payload["normalized_title"] == "headline"
    assert payload["clean_content"] == "clean"
    assert payload["published_at"] == published_at
    assert payload["metadata"] == {"region": "us"}


def test_article_record_to_feature_seed_keeps_extractor_inputs_stable():
    record = ArticleRecord(
        article_id="art_1",
        source_id="reuters",
        canonical_url="https://example.com/a",
        title="Headline",
        content="raw",
        clean_content="clean",
        language="en",
        simhash="sim-1",
        quality_score=0.8,
        metadata={"topic": "energy"},
    )

    assert record.to_feature_seed() == {
        "article_id": "art_1",
        "source_id": "reuters",
        "canonical_url": "https://example.com/a",
        "title": "Headline",
        "normalized_title": "Headline",
        "content": "raw",
        "clean_content": "clean",
        "language": "en",
        "published_at": None,
        "ingested_at": None,
        "tier": 4,
        "source_type": "other",
        "exact_hash": "",
        "simhash": "sim-1",
        "content_length": 5,
        "quality_score": 0.8,
        "metadata": {"topic": "energy"},
    }


def test_article_record_content_length_falls_back_to_content_when_clean_content_empty():
    record = ArticleRecord(
        article_id="art_1",
        source_id="reuters",
        canonical_url="https://example.com/a",
        title="Headline",
        content="raw body",
        clean_content="",
    )

    assert record.content_length == len("raw body")
