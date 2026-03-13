from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from typing import Dict, Any, Optional

import yfinance as yf
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


ENERGY_SYMBOLS = {"CL=F", "BZ=F", "NG=F", "RB=F", "HO=F"}
PRECIOUS_METAL_SYMBOLS = {"GC=F", "SI=F", "PL=F", "PA=F"}
USD_SYMBOLS = {"DX-Y.NYB", "DXY", "UUP"}
EQUITY_SYMBOLS = {"^GSPC", "^IXIC", "^DJI", "SPY", "QQQ"}
RATES_SYMBOLS = {"^TNX", "^IRX", "ZT=F", "ZF=F", "ZN=F", "ZB=F"}


def build_market_context_snapshot(
    prices: Sequence[Mapping[str, Any]],
    *,
    as_of: str | datetime | None = None,
    top_n: int = 3,
) -> dict[str, Any]:
    normalized_prices = [_normalize_price_entry(item) for item in prices]
    filtered_prices = [item for item in normalized_prices if item["symbol"]]
    safe_top_n = max(int(top_n), 1)
    snapshot_as_of = _resolve_as_of(as_of, filtered_prices)

    winners = [
        {"symbol": item["symbol"], "change_percent": item["change_percent"]}
        for item in sorted(
            filtered_prices,
            key=lambda item: (-item["change_percent"], item["symbol"]),
        )
        if item["change_percent"] > 0
    ][:safe_top_n]
    losers = [
        {"symbol": item["symbol"], "change_percent": item["change_percent"]}
        for item in sorted(
            filtered_prices,
            key=lambda item: (item["change_percent"], item["symbol"]),
        )
        if item["change_percent"] < 0
    ][:safe_top_n]
    signals = _build_cross_asset_signals(filtered_prices)

    snapshot = {
        "as_of": snapshot_as_of,
        "prices": filtered_prices,
        "winners": winners,
        "losers": losers,
        "cross_asset_signals": signals,
    }
    snapshot["summary"] = _build_market_summary(snapshot)
    return snapshot


def render_market_context_snapshot(
    snapshot: Mapping[str, Any],
    *,
    max_items: int = 3,
) -> str:
    data = dict(snapshot) if isinstance(snapshot, Mapping) else {}
    summary = _text(data.get("summary"))
    winners = _sequence_of_mappings(data.get("winners"))[: max(int(max_items), 1)]
    losers = _sequence_of_mappings(data.get("losers"))[: max(int(max_items), 1)]
    signals = _text_list(data.get("cross_asset_signals"))[: max(int(max_items), 1)]
    as_of = _text(data.get("as_of"))

    lines: list[str] = []
    if summary:
        lines.append(summary)
    if as_of:
        lines.append(f"As of: {as_of}")
    if winners:
        lines.append(
            "Top movers up: "
            + ", ".join(
                f"{item['symbol']} ({item['change_percent']:+.2f}%)"
                for item in winners
                if item.get("symbol")
            )
        )
    if losers:
        lines.append(
            "Top movers down: "
            + ", ".join(
                f"{item['symbol']} ({item['change_percent']:+.2f}%)"
                for item in losers
                if item.get("symbol")
            )
        )
    if signals:
        lines.append("Cross-asset signals: " + "; ".join(signals))
    return "\n".join(line for line in lines if line.strip())


def _normalize_price_entry(item: Mapping[str, Any]) -> dict[str, Any]:
    symbol = _text(item.get("symbol"))
    price = _safe_float(item.get("price"))
    change_percent = round(_safe_float(item.get("changePercent")), 2)
    timestamp = _text(item.get("timestamp"))
    if not timestamp:
        timestamp = _text(item.get("as_of"))
    direction = "flat"
    if change_percent > 0.1:
        direction = "up"
    elif change_percent < -0.1:
        direction = "down"
    return {
        "symbol": symbol,
        "price": round(price, 2),
        "change_percent": change_percent,
        "direction": direction,
        "timestamp": timestamp,
    }


def _resolve_as_of(
    as_of: str | datetime | None,
    prices: Sequence[Mapping[str, Any]],
) -> str:
    if isinstance(as_of, datetime):
        if as_of.tzinfo is None:
            return as_of.replace(tzinfo=UTC).isoformat()
        return as_of.isoformat()
    if isinstance(as_of, str) and as_of.strip():
        return as_of.strip()
    for item in prices:
        timestamp = _text(item.get("timestamp"))
        if timestamp:
            return timestamp
    return datetime.now(UTC).isoformat()


def _build_cross_asset_signals(
    prices: Sequence[Mapping[str, Any]],
) -> list[str]:
    signals: list[str] = []
    for item in prices:
        symbol = _text(item.get("symbol"))
        change = _safe_float(item.get("change_percent"))
        if symbol in ENERGY_SYMBOLS:
            if change >= 0.5:
                signals.append("energy strength")
            elif change <= -0.5:
                signals.append("energy weakness")
        if symbol in PRECIOUS_METAL_SYMBOLS:
            if change >= 0.5:
                signals.append("precious metals bid")
            elif change <= -0.5:
                signals.append("precious metals offered")
        if symbol in USD_SYMBOLS:
            if change >= 0.4:
                signals.append("usd strength")
            elif change <= -0.4:
                signals.append("usd weakness")
        if symbol in EQUITY_SYMBOLS:
            if change >= 0.5:
                signals.append("equity strength")
            elif change <= -0.5:
                signals.append("equity weakness")
        if symbol in RATES_SYMBOLS:
            if abs(change) >= 0.5:
                signals.append("rates volatility")

    deduped: list[str] = []
    seen = set()
    for signal in signals:
        normalized = signal.casefold()
        if normalized in seen:
            continue
        seen.add(normalized)
        deduped.append(signal)
    return deduped[:4]


def _build_market_summary(snapshot: Mapping[str, Any]) -> str:
    prices = _sequence_of_mappings(snapshot.get("prices"))
    winners = _sequence_of_mappings(snapshot.get("winners"))
    losers = _sequence_of_mappings(snapshot.get("losers"))
    signals = _text_list(snapshot.get("cross_asset_signals"))

    parts = [f"Market snapshot tracks {len(prices)} instruments."]
    if winners:
        top = winners[0]
        parts.append(
            f"Leaders are {top['symbol']} ({top['change_percent']:+.2f}%)"
        )
    if losers:
        laggard = losers[0]
        parts.append(
            f"while laggards are led by {laggard['symbol']} ({laggard['change_percent']:+.2f}%)."
        )
    if signals:
        parts.append("Signals: " + ", ".join(signals[:3]) + ".")
    return " ".join(parts)


def _sequence_of_mappings(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return []
    return [dict(item) for item in value if isinstance(item, Mapping)]


def _text_list(value: Any) -> list[str]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return []
    return [_text(item) for item in value if _text(item)]


def _safe_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    return str(value).strip()
