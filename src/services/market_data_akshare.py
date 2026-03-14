from __future__ import annotations

from typing import Any

from loguru import logger

# ── AkShare lazy import ──

_akshare: Any = None


def _ensure_akshare() -> Any:
    global _akshare
    if _akshare is None:
        try:
            import akshare as _ak

            _akshare = _ak
        except ImportError:
            _akshare = False
            logger.debug("akshare not installed; CN macro data disabled")
    return _akshare


# ── AkShare CN Macro Adapter ──


class AkShareAdapter:
    async def get_cn_bond_yield(self) -> dict[str, Any]:
        ak = _ensure_akshare()
        if not ak:
            return {}

        import asyncio
        from datetime import datetime

        loop = asyncio.get_event_loop()
        try:

            def _fetch() -> dict[str, Any]:
                today = datetime.now().strftime("%Y%m%d")
                df = ak.bond_china_yield(start_date=today, end_date=today)
                if df is None or df.empty:
                    return {}
                row = df.iloc[-1]
                return {
                    "value": round(float(row.get("中国国债收益率10年", 0.0)), 4),
                    "timestamp": str(row.get("日期", today)),
                    "source": "akshare/bond_china_yield",
                }

            return await loop.run_in_executor(None, _fetch)
        except Exception as exc:
            logger.warning(f"AkShare get_cn_bond_yield failed: {exc}")
            return {}

    async def get_shibor(self) -> dict[str, Any]:
        ak = _ensure_akshare()
        if not ak:
            return {}

        import asyncio

        loop = asyncio.get_event_loop()
        try:

            def _fetch() -> dict[str, Any]:
                df = ak.rate_interbank(
                    market="上海银行间同业拆放利率(Shibor)", indicator="1月"
                )
                if df is None or df.empty:
                    return {}
                row = df.iloc[-1]
                return {
                    "value": round(float(row.get("利率", 0.0)), 4),
                    "timestamp": str(row.get("报告日", "")),
                    "source": "akshare/shibor_1m",
                }

            return await loop.run_in_executor(None, _fetch)
        except Exception as exc:
            logger.warning(f"AkShare get_shibor failed: {exc}")
            return {}

    async def get_a_share_index(self, symbol: str = "sh000300") -> dict[str, Any]:
        ak = _ensure_akshare()
        if not ak:
            return {}

        import asyncio

        loop = asyncio.get_event_loop()
        try:

            def _fetch() -> dict[str, Any]:
                df = ak.stock_zh_index_daily(symbol=symbol)
                if df is None or df.empty:
                    return {}
                row = df.iloc[-1]
                close = float(row.get("close", 0.0))
                prev = float(row.get("open", close))
                change_pct = ((close - prev) / prev * 100) if prev else 0.0
                return {
                    "symbol": symbol,
                    "price": round(close, 2),
                    "change_percent": round(change_pct, 2),
                    "timestamp": str(row.get("date", "")),
                    "source": "akshare/stock_zh_index_daily",
                }

            return await loop.run_in_executor(None, _fetch)
        except Exception as exc:
            logger.warning(f"AkShare get_a_share_index({symbol}) failed: {exc}")
            return {}


__all__ = ["AkShareAdapter"]
