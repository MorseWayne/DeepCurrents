import json
from unittest.mock import AsyncMock, patch, MagicMock

import pytest

from src.services.alpha_vantage_service import AlphaVantageService, NewsArticleSentiment


@pytest.fixture
def av_service():
    return AlphaVantageService(api_key="demo", cache=None)


MOCK_RESPONSE = {
    "feed": [
        {
            "title": "Fed holds rates steady",
            "url": "https://example.com/1",
            "time_published": "20240101T120000",
            "source": "Reuters",
            "overall_sentiment_label": "Neutral",
            "overall_sentiment_score": 0.05,
            "ticker_sentiment": [
                {
                    "ticker": "SPY",
                    "ticker_sentiment_label": "Bearish",
                    "ticker_sentiment_score": -0.3,
                    "relevance_score": 0.85,
                }
            ],
        }
    ]
}


@pytest.mark.asyncio
async def test_get_news_sentiment_returns_articles(av_service):
    mock_resp = AsyncMock()
    mock_resp.json = AsyncMock(return_value=MOCK_RESPONSE)
    mock_resp.raise_for_status = MagicMock()

    with patch("aiohttp.ClientSession.get") as mock_get:
        mock_get.return_value.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_get.return_value.__aexit__ = AsyncMock(return_value=False)

        articles = await av_service.get_news_sentiment("SPY", days=7)

    assert len(articles) == 1
    assert articles[0].ticker == "SPY"
    assert articles[0].sentiment_score == pytest.approx(-0.3, abs=1e-6)
    assert articles[0].relevance == pytest.approx(0.85, abs=1e-6)


@pytest.mark.asyncio
async def test_get_news_sentiment_empty_feed(av_service):
    mock_resp = AsyncMock()
    mock_resp.json = AsyncMock(return_value={"feed": []})
    mock_resp.raise_for_status = MagicMock()

    with patch("aiohttp.ClientSession.get") as mock_get:
        mock_get.return_value.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_get.return_value.__aexit__ = AsyncMock(return_value=False)

        articles = await av_service.get_news_sentiment("UNKNOWN", days=7)

    assert articles == []


def test_aggregate_sentiment_weighted():
    from src.services.alpha_vantage_service import aggregate_sentiment
    articles = [
        NewsArticleSentiment(
            title="A", url="u1", source="s", published="",
            ticker="SPY", sentiment_score=0.8, relevance=1.0
        ),
        NewsArticleSentiment(
            title="B", url="u2", source="s", published="",
            ticker="SPY", sentiment_score=-0.2, relevance=0.5
        ),
    ]
    score = aggregate_sentiment(articles)
    # weighted: (0.8*1.0 + -0.2*0.5) / (1.0+0.5) = 0.7/1.5 ≈ 0.467
    assert abs(score - 0.467) < 0.01
