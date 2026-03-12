from __future__ import annotations

from datetime import UTC

from src.services.article_normalizer import ArticleNormalizer, canonicalize_url


def test_canonicalize_url_removes_tracking_params_and_fragment():
    assert (
        canonicalize_url(
            "HTTPS://www.Reuters.com/world/example-attack/?utm_source=rss&foo=1#top"
        )
        == "https://www.reuters.com/world/example-attack?foo=1"
    )
    assert (
        canonicalize_url("https://apnews.com/article/power-grid-outage?taid=123")
        == "https://apnews.com/article/power-grid-outage"
    )


def test_article_normalizer_handles_collector_style_payloads():
    normalizer = ArticleNormalizer()

    record = normalizer.normalize(
        {
            "link": "https://www.reuters.com/world/example-attack?utm_source=rss",
            "title": "Missile strike disrupts Red Sea shipping - Reuters",
            "summary": "<p>Shipping costs <b>jumped</b> after the strike.</p>",
            "source": "Reuters World",
            "published": "Fri, 13 Mar 2026 01:00:00 GMT",
            "meta": {"tier": 1, "sourceType": "wire"},
        }
    )

    assert record.article_id.startswith("art_")
    assert record.source_id == "reuters-world"
    assert record.canonical_url == "https://www.reuters.com/world/example-attack"
    assert record.title == "Missile strike disrupts Red Sea shipping"
    assert record.normalized_title == "missile strike disrupts red sea shipping"
    assert record.content == "Shipping costs jumped after the strike."
    assert record.clean_content == "Shipping costs jumped after the strike."
    assert record.language == "en"
    assert record.published_at is not None
    assert record.published_at == UTC.fromutc(record.published_at.replace(tzinfo=UTC))
    assert record.published_at.isoformat() == "2026-03-13T01:00:00+00:00"
    assert record.tier == 1
    assert record.source_type == "wire"
    assert record.metadata["source"] == "Reuters World"


def test_article_normalizer_detects_zh_and_produces_stable_hashes():
    normalizer = ArticleNormalizer()
    payload = {
        "canonical_url": "https://example.com/news/rate-cut",
        "title": "土耳其央行意外下调基准利率",
        "description": "<div>央行宣布降息，市场感到意外。</div>",
        "source": "财联社",
        "published_at": "2026-03-13T06:08:00Z",
        "tier": 2,
        "type": "market",
    }

    left = normalizer.normalize(payload)
    right = normalizer.normalize(payload)

    assert left.language == "zh"
    assert left.exact_hash == right.exact_hash
    assert left.simhash == right.simhash
    assert len(left.exact_hash) == 64
    assert len(left.simhash) == 16
    assert left.content_length == len("央行宣布降息，市场感到意外。")


def test_article_normalizer_falls_back_to_defaults_for_sparse_payloads():
    normalizer = ArticleNormalizer()

    record = normalizer.normalize(
        {
            "canonical_url": "https://example.com/brief",
            "title": "Short bulletin",
        }
    )

    assert record.source_id == "unknown"
    assert record.source_type == "other"
    assert record.tier == 4
    assert record.content == ""
    assert record.clean_content == ""
    assert record.language == "en"
