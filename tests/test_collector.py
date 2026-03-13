from unittest.mock import AsyncMock, patch

import pytest

from src.config.sources import Source
from src.services.article_models import ArticleRecord
from src.services.collector import RSSCollector


RSS_ITEM = """<?xml version=\"1.0\" encoding=\"UTF-8\" ?>
<rss version=\"2.0\">
<channel>
  <title>Mock RSS</title>
  <item>
    <title>News 1</title>
    <link>http://news1.com/story</link>
    <description>Content 1</description>
  </item>
</channel>
</rss>"""


class StubNormalizer:
    def __init__(self):
        self.calls = []
        self.article = ArticleRecord(
            article_id="art_news1",
            source_id="test-source",
            canonical_url="https://news1.com/story",
            title="News 1",
            normalized_title="news 1",
            content="Content 1",
            clean_content="Content 1",
            language="en",
            tier=3,
            source_type="wire",
            metadata={"source": "Test Source"},
        )

    def normalize(self, raw):
        self.calls.append(dict(raw))
        return self.article


class StubRepository:
    def __init__(self):
        self.create_article = AsyncMock(return_value={"article_id": "art_news1"})
        self.get_article = AsyncMock(return_value=None)


class StubFeatureExtractor:
    def __init__(self):
        self.extract_and_persist = AsyncMock(
            return_value={"article_id": "art_news1", "embedding": [0.1, 0.2, 0.3]}
        )


class StubSemanticDeduper:
    def __init__(self):
        self.link_cheap_duplicates = AsyncMock(return_value=[])
        self.link_semantic_duplicates = AsyncMock(return_value=[])


class StubEventCandidateExtractor:
    def __init__(self):
        self.extract_and_persist = AsyncMock(
            return_value={
                "event": {"event_id": "evt_1"},
                "member": {"article_id": "art_news1"},
                "created": True,
                "score": None,
            }
        )


class StubEventEnrichment:
    def __init__(self):
        self.enrich_event = AsyncMock(
            return_value={
                "event": {"event_id": "evt_1", "event_type": "general"},
                "enrichment": {"event_type": "general"},
            }
        )


@pytest.fixture
def source():
    return Source(
        name="Test Source",
        url="http://mock.rss",
        category="Test",
        tier=3,
        type="wire",
    )


def mock_rss_response(mock_get, content: str = RSS_ITEM):
    mock_response = AsyncMock()
    mock_response.status = 200
    mock_response.text.return_value = content
    mock_get.return_value.__aenter__.return_value = mock_response


@pytest.mark.asyncio
async def test_collect_all_skips_when_event_intelligence_unavailable(source):
    collector = RSSCollector()

    with patch("src.services.collector.SOURCES", [source]):
        stats = await collector.collect_all()

    assert stats["sources_total"] == 1
    assert stats["sources_skipped"] == 1
    assert stats["skipped"] == 1
    assert stats["articles_inserted"] == 0


@pytest.mark.asyncio
async def test_fetch_source_skips_when_event_intelligence_unavailable(source):
    collector = RSSCollector()

    result = await collector.fetch_source(source)

    assert result["skipped"] is True
    assert result["reason"] == "event_intelligence_unavailable"
    assert result["articles_inserted"] == 0


@pytest.mark.asyncio
async def test_fetch_source_persists_event_intelligence_article_without_legacy_mirror(
    source,
):
    collector = RSSCollector()
    normalizer = StubNormalizer()
    repository = StubRepository()
    feature_extractor = StubFeatureExtractor()
    deduper = StubSemanticDeduper()
    event_extractor = StubEventCandidateExtractor()
    event_enrichment = StubEventEnrichment()
    call_order = []

    async def create_article(payload):
        call_order.append("article-save")
        return {"article_id": payload["article_id"]}

    async def extract_and_persist(article):
        call_order.append("feature-save")
        return {"article_id": article.article_id, "embedding": [0.1, 0.2, 0.3]}

    async def link_cheap_duplicates(article):
        call_order.append("cheap-dedup")
        return []

    async def link_semantic_duplicates(article, *, embedding):
        call_order.append("semantic-dedup")
        assert embedding == [0.1, 0.2, 0.3]
        return []

    async def upsert_event(article, *, extracted_features=None):
        call_order.append("event-upsert")
        assert extracted_features == {"article_id": article.article_id, "embedding": [0.1, 0.2, 0.3]}
        return {
            "event": {"event_id": "evt_1"},
            "member": {"article_id": article.article_id},
            "created": True,
            "score": None,
        }

    async def enrich_event(event_id, *, event=None):
        call_order.append("event-enrich")
        assert event_id == "evt_1"
        assert event == {"event_id": "evt_1"}
        return {"event": {"event_id": event_id}, "enrichment": {"event_type": "general"}}

    repository.create_article = AsyncMock(side_effect=create_article)
    feature_extractor.extract_and_persist = AsyncMock(side_effect=extract_and_persist)
    deduper.link_cheap_duplicates = AsyncMock(side_effect=link_cheap_duplicates)
    deduper.link_semantic_duplicates = AsyncMock(side_effect=link_semantic_duplicates)
    event_extractor.extract_and_persist = AsyncMock(side_effect=upsert_event)
    event_enrichment.enrich_event = AsyncMock(side_effect=enrich_event)
    collector.configure_event_intelligence(
        article_normalizer=normalizer,
        article_repository=repository,
        article_feature_extractor=feature_extractor,
        semantic_deduper=deduper,
        event_candidate_extractor=event_extractor,
        event_enrichment=event_enrichment,
    )

    with patch("aiohttp.ClientSession.get") as mock_get:
        mock_rss_response(mock_get)
        result = await collector.fetch_source(source)

    assert result["new_count"] == 1
    assert normalizer.calls[0]["url"] == "http://news1.com/story"
    assert call_order == [
        "article-save",
        "cheap-dedup",
        "feature-save",
        "semantic-dedup",
        "event-upsert",
        "event-enrich",
    ]
    assert result["articles_seen"] == 1
    assert result["articles_inserted"] == 1
    assert result["cheap_dedup_links"] == 0
    assert result["semantic_dedup_links"] == 0
    assert result["events_created"] == 1
    assert result["events_updated"] == 0
    assert result["events_touched"] == 1
    repository.create_article.assert_awaited_once_with(
        normalizer.article.to_article_payload()
    )
    feature_extractor.extract_and_persist.assert_awaited_once_with(normalizer.article)
    deduper.link_cheap_duplicates.assert_awaited_once_with(normalizer.article)
    deduper.link_semantic_duplicates.assert_awaited_once_with(
        normalizer.article,
        embedding=[0.1, 0.2, 0.3],
    )


@pytest.mark.asyncio
async def test_fetch_source_continues_when_event_intelligence_feature_extraction_fails(
    source,
):
    collector = RSSCollector()
    normalizer = StubNormalizer()
    repository = StubRepository()
    feature_extractor = StubFeatureExtractor()
    deduper = StubSemanticDeduper()
    feature_extractor.extract_and_persist.side_effect = RuntimeError("embedding failed")
    collector.configure_event_intelligence(
        article_normalizer=normalizer,
        article_repository=repository,
        article_feature_extractor=feature_extractor,
        semantic_deduper=deduper,
    )

    with patch("aiohttp.ClientSession.get") as mock_get:
        mock_rss_response(mock_get)
        result = await collector.fetch_source(source)

    assert result["new_count"] == 1
    repository.create_article.assert_awaited_once()
    deduper.link_cheap_duplicates.assert_awaited_once_with(normalizer.article)
    feature_extractor.extract_and_persist.assert_awaited_once_with(normalizer.article)
    deduper.link_semantic_duplicates.assert_not_awaited()


@pytest.mark.asyncio
async def test_fetch_source_does_not_fallback_when_article_persist_fails_without_existing_record(
    source,
):
    collector = RSSCollector()
    normalizer = StubNormalizer()
    repository = StubRepository()
    repository.create_article.side_effect = RuntimeError("db unavailable")
    repository.get_article.return_value = None
    feature_extractor = StubFeatureExtractor()
    collector.configure_event_intelligence(
        article_normalizer=normalizer,
        article_repository=repository,
        article_feature_extractor=feature_extractor,
    )

    with patch("aiohttp.ClientSession.get") as mock_get:
        mock_rss_response(mock_get)
        result = await collector.fetch_source(source)

    assert result["new_count"] == 0
    assert result["articles_inserted"] == 0
    repository.get_article.assert_awaited_once_with(normalizer.article.article_id)
    feature_extractor.extract_and_persist.assert_not_awaited()


@pytest.mark.asyncio
async def test_fetch_source_refreshes_features_for_existing_event_intelligence_article(
    source,
):
    collector = RSSCollector()
    normalizer = StubNormalizer()
    repository = StubRepository()
    repository.create_article.side_effect = RuntimeError("duplicate key")
    repository.get_article.return_value = {"article_id": normalizer.article.article_id}
    feature_extractor = StubFeatureExtractor()
    deduper = StubSemanticDeduper()
    collector.configure_event_intelligence(
        article_normalizer=normalizer,
        article_repository=repository,
        article_feature_extractor=feature_extractor,
        semantic_deduper=deduper,
    )

    with patch("aiohttp.ClientSession.get") as mock_get:
        mock_rss_response(mock_get)
        result = await collector.fetch_source(source)

    assert result["new_count"] == 1
    repository.get_article.assert_awaited_once_with(normalizer.article.article_id)
    deduper.link_cheap_duplicates.assert_awaited_once_with(normalizer.article)
    feature_extractor.extract_and_persist.assert_awaited_once_with(normalizer.article)
    deduper.link_semantic_duplicates.assert_awaited_once_with(
        normalizer.article,
        embedding=[0.1, 0.2, 0.3],
    )


@pytest.mark.asyncio
async def test_collect_all_aggregates_extended_ingestion_metrics(source):
    collector = RSSCollector()
    other_source = source.model_copy(
        update={"name": "Other Source", "url": "http://other.rss", "tier": 2}
    )

    collector.configure_event_intelligence(
        article_normalizer=StubNormalizer(),
        article_repository=StubRepository(),
        article_feature_extractor=StubFeatureExtractor(),
    )
    collector.fetch_source = AsyncMock(
        side_effect=[
            {
                "new_count": 2,
                "articles_seen": 3,
                "articles_inserted": 2,
                "duplicate_refreshes": 1,
                "feature_failures": 0,
                "cheap_dedup_links": 1,
                "semantic_dedup_links": 2,
                "events_created": 1,
                "events_updated": 1,
                "event_enrichment_failures": 0,
                "events_touched": 2,
            },
            {
                "error": "timeout",
                "articles_seen": 1,
                "articles_inserted": 0,
                "duplicate_refreshes": 0,
                "feature_failures": 1,
                "cheap_dedup_links": 0,
                "semantic_dedup_links": 0,
                "events_created": 0,
                "events_updated": 0,
                "event_enrichment_failures": 1,
                "events_touched": 0,
            },
        ]
    )

    class StubClientSession:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

    with patch("src.services.collector.SOURCES", [source, other_source]):
        with patch(
            "src.services.collector.aiohttp.ClientSession",
            return_value=StubClientSession(),
        ):
            stats = await collector.collect_all()

    assert stats["sources_total"] == 2
    assert stats["sources_failed"] == 1
    assert stats["articles_seen"] == 4
    assert stats["articles_inserted"] == 2
    assert stats["events_touched"] == 2
    assert stats["feature_failures"] == 1
    assert stats["new_items"] == 2
    assert stats["errors"] == 1
    assert stats["article_to_event_compression_ratio"] == pytest.approx(1.0)
