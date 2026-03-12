from unittest.mock import AsyncMock, MagicMock, patch

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
        self.extract_and_persist = AsyncMock(return_value={"article_id": "art_news1"})


@pytest.fixture
def mock_db():
    db = MagicMock()
    db.has_news = AsyncMock(return_value=False)
    db.has_similar_title = AsyncMock(return_value=False)
    db.save_news = AsyncMock(return_value=True)
    return db


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
async def test_fetch_source_success(mock_db, source):
    collector = RSSCollector(mock_db)

    with patch("aiohttp.ClientSession.get") as mock_get:
        mock_rss_response(mock_get)

        result = await collector.fetch_source(source)

    assert result["new_count"] == 1
    mock_db.save_news.assert_called_once()


@pytest.mark.asyncio
async def test_fetch_source_runs_event_intelligence_side_path_after_save(
    mock_db, source
):
    collector = RSSCollector(mock_db)
    normalizer = StubNormalizer()
    repository = StubRepository()
    feature_extractor = StubFeatureExtractor()
    collector.configure_event_intelligence(
        article_normalizer=normalizer,
        article_repository=repository,
        article_feature_extractor=feature_extractor,
    )

    with patch("aiohttp.ClientSession.get") as mock_get:
        mock_rss_response(mock_get)

        result = await collector.fetch_source(source)

    assert result["new_count"] == 1
    assert normalizer.calls[0]["url"] == "http://news1.com/story"
    repository.create_article.assert_awaited_once_with(
        normalizer.article.to_article_payload()
    )
    feature_extractor.extract_and_persist.assert_awaited_once_with(normalizer.article)


@pytest.mark.asyncio
async def test_fetch_source_continues_when_event_intelligence_feature_extraction_fails(
    mock_db, source
):
    collector = RSSCollector(mock_db)
    normalizer = StubNormalizer()
    repository = StubRepository()
    feature_extractor = StubFeatureExtractor()
    feature_extractor.extract_and_persist.side_effect = RuntimeError("embedding failed")
    collector.configure_event_intelligence(
        article_normalizer=normalizer,
        article_repository=repository,
        article_feature_extractor=feature_extractor,
    )

    with patch("aiohttp.ClientSession.get") as mock_get:
        mock_rss_response(mock_get)

        result = await collector.fetch_source(source)

    assert result["new_count"] == 1
    repository.create_article.assert_awaited_once()
    feature_extractor.extract_and_persist.assert_awaited_once_with(normalizer.article)


@pytest.mark.asyncio
async def test_fetch_source_refreshes_features_for_existing_event_intelligence_article(
    mock_db, source
):
    collector = RSSCollector(mock_db)
    normalizer = StubNormalizer()
    repository = StubRepository()
    repository.create_article.side_effect = RuntimeError("duplicate key")
    repository.get_article.return_value = {"article_id": normalizer.article.article_id}
    feature_extractor = StubFeatureExtractor()
    collector.configure_event_intelligence(
        article_normalizer=normalizer,
        article_repository=repository,
        article_feature_extractor=feature_extractor,
    )

    with patch("aiohttp.ClientSession.get") as mock_get:
        mock_rss_response(mock_get)

        result = await collector.fetch_source(source)

    assert result["new_count"] == 1
    repository.get_article.assert_awaited_once_with(normalizer.article.article_id)
    feature_extractor.extract_and_persist.assert_awaited_once_with(normalizer.article)


@pytest.mark.asyncio
async def test_circuit_breaker_cooldown(mock_db, source):
    collector = RSSCollector(mock_db)
    failure_source = source.model_copy(update={"name": "Failure Source"})

    with patch("aiohttp.ClientSession.get", side_effect=Exception("Network Error")):
        for _ in range(3):
            await collector.fetch_source(failure_source)

    result = await collector.fetch_source(failure_source)
    assert result.get("skipped") is True
