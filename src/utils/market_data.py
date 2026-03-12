import yfinance as yf
from typing import Dict, Any, Optional
from datetime import datetime
from ..utils.logger import get_logger

logger = get_logger("market-data")

async def get_market_price(symbol: str) -> Dict[str, Any]:
    """获取资产的实时行情"""
    try:
        # yfinance 是同步库，在异步环境中建议使用 run_in_executor
        import asyncio
        loop = asyncio.get_event_loop()
        
        def fetch():
            ticker = yf.Ticker(symbol)
            data = ticker.history(period="1d")
            if data.empty:
                raise Exception(f"No data found for {symbol}")
            
            current_price = data['Close'].iloc[-1]
            prev_close = ticker.info.get('previousClose', current_price)
            change_percent = ((current_price - prev_close) / prev_close) * 100
            
            return {
                "symbol": symbol,
                "price": round(float(current_price), 2),
                "changePercent": round(float(change_percent), 2),
                "timestamp": data.index[-1].isoformat()
            }
            
        return await loop.run_in_executor(None, fetch)
    except Exception as e:
        logger.error(f"Failed to fetch market data for {symbol}: {e}")
        raise e


def _select_symbol_from_quotes(quotes: list, query: str) -> Optional[str]:
    if not quotes:
        return None

    query_norm = query.lower().strip()
    valid_types = {
        "EQUITY", "ETF", "FUTURE", "MUTUALFUND", "INDEX",
        "CRYPTOCURRENCY", "CURRENCY", "CURRENCYPAIR"
    }

    best_symbol = None
    best_score = -1
    for q in quotes:
        if not isinstance(q, dict):
            continue

        symbol = q.get("symbol")
        if not symbol or not isinstance(symbol, str):
            continue

        quote_type = str(q.get("quoteType", "")).upper()
        if quote_type and quote_type not in valid_types:
            continue

        name = str(q.get("shortname") or q.get("longname") or "").lower()
        symbol_norm = symbol.lower()

        score = 0
        if symbol_norm == query_norm:
            score += 100
        if query_norm in symbol_norm:
            score += 60
        if query_norm in name:
            score += 50
        if q.get("isYahooFinance"):
            score += 10
        if quote_type:
            score += 5

        if score > best_score:
            best_score = score
            best_symbol = symbol

    return best_symbol


async def search_market_symbol(query: str) -> Optional[str]:
    """Auto-resolve a market symbol from free-form asset text."""
    if not query or not query.strip():
        return None

    try:
        import asyncio
        loop = asyncio.get_event_loop()

        def search():
            result = yf.Search(query=query, max_results=12, news_count=0)
            quotes = getattr(result, "quotes", None)
            return _select_symbol_from_quotes(quotes or [], query)

        symbol = await loop.run_in_executor(None, search)
        if symbol:
            logger.info(f"Auto-resolved symbol: '{query}' -> {symbol}")
        return symbol
    except Exception as e:
        logger.warning(f"Failed to auto-resolve symbol for '{query}': {e}")
        return None
