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
