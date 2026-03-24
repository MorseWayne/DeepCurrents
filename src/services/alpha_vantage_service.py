"""Alpha Vantage News Sentiment 服务。

免费版：25次/天；付费版：$49.99/月。
文档：https://www.alphavantage.co/documentation/#news-sentiment
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

import aiohttp

from ..utils.logger import get_logger

logger = get_logger("alpha-vantage")

_BASE_URL = "https://www.alphavantage.co/query"


@dataclass
class NewsArticleSentiment:
    title: str
    url: str
    source: str
    published: str
    ticker: str
    sentiment_score: float   # -1.0 (bearish) ~ +1.0 (bullish)
    relevance: float          # 0.0 ~ 1.0


def aggregate_sentiment(articles: list[NewsArticleSentiment]) -> float:
    """加权平均情绪评分（权重=相关性）。空列表返回 0.0。"""
    if not articles:
        return 0.0
    total_weight = sum(a.relevance for a in articles)
    if total_weight == 0:
        return 0.0
    return sum(a.sentiment_score * a.relevance for a in articles) / total_weight


class AlphaVantageService:
    def __init__(self, *, api_key: str, cache: Any = None):
        self._api_key = api_key
        self._cache = cache

    async def get_news_sentiment(
        self,
        ticker: str,
        *,
        days: int = 7,
    ) -> list[NewsArticleSentiment]:
        if not self._api_key:
            logger.debug("Alpha Vantage API key not configured, skipping")
            return []

        cache_key = f"av:news:{ticker}:{days}d"
        if self._cache is not None:
            cached = await self._cache.get(cache_key)
            if cached:
                import json
                raw = json.loads(cached)
                return [NewsArticleSentiment(**item) for item in raw]

        time_from = (
            datetime.now(timezone.utc) - timedelta(days=days)
        ).strftime("%Y%m%dT%H%M%S")

        params = {
            "function": "NEWS_SENTIMENT",
            "tickers": ticker.upper(),
            "time_from": time_from,
            "limit": "50",
            "apikey": self._api_key,
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(_BASE_URL, params=params, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    resp.raise_for_status()
                    data = await resp.json()
        except Exception as exc:
            logger.warning(f"Alpha Vantage API error for {ticker}: {exc}")
            return []

        articles = self._parse_feed(ticker, data.get("feed", []))

        if self._cache is not None and articles:
            import json
            from ..config.settings import CONFIG
            ttl = getattr(CONFIG, "alpha_vantage_cache_ttl_s", 3600)
            await self._cache.setex(
                cache_key,
                ttl,
                json.dumps([vars(a) for a in articles]),
            )

        return articles

    @staticmethod
    def _parse_feed(ticker: str, feed: list[dict]) -> list[NewsArticleSentiment]:
        ticker_upper = ticker.upper()
        results: list[NewsArticleSentiment] = []
        for item in feed:
            for ts in item.get("ticker_sentiment", []):
                if ts.get("ticker", "").upper() == ticker_upper:
                    try:
                        results.append(NewsArticleSentiment(
                            title=item.get("title", ""),
                            url=item.get("url", ""),
                            source=item.get("source", ""),
                            published=item.get("time_published", ""),
                            ticker=ticker_upper,
                            sentiment_score=float(ts.get("ticker_sentiment_score", 0.0)),
                            relevance=float(ts.get("relevance_score", 0.0)),
                        ))
                    except (ValueError, TypeError):
                        continue
        return results
