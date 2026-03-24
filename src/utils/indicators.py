"""技术指标计算库 —— 纯函数，无 I/O，无副作用。
来源：基于 TradingAgents-CN indicators.py (Apache 2.0) 适配。
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def ma(close: pd.Series, n: int, min_periods: int = 1) -> pd.Series:
    """简单移动平均 (SMA)"""
    return close.rolling(window=int(n), min_periods=min_periods).mean()


def ema(close: pd.Series, n: int) -> pd.Series:
    """指数移动平均 (EMA)"""
    return close.ewm(span=int(n), adjust=False).mean()


def macd(
    close: pd.Series,
    fast: int = 12,
    slow: int = 26,
    signal: int = 9,
) -> pd.DataFrame:
    """MACD 指标。返回 DataFrame，列：dif / dea / macd_hist"""
    dif = ema(close, fast) - ema(close, slow)
    dea = dif.ewm(span=int(signal), adjust=False).mean()
    return pd.DataFrame({"dif": dif, "dea": dea, "macd_hist": dif - dea})


def rsi(close: pd.Series, n: int = 14) -> pd.Series:
    """RSI 相对强弱指标（Wilder's EMA，国际标准）"""
    delta = close.diff()
    gain = delta.where(delta > 0, 0.0)
    loss = -delta.where(delta < 0, 0.0)
    avg_gain = gain.ewm(alpha=1.0 / float(n), adjust=False).mean()
    avg_loss = loss.ewm(alpha=1.0 / float(n), adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    return 100.0 - (100.0 / (1.0 + rs))


def boll(
    close: pd.Series,
    n: int = 20,
    k: float = 2.0,
    min_periods: int = 1,
) -> pd.DataFrame:
    """布林带。返回 DataFrame，列：boll_mid / boll_upper / boll_lower"""
    mid = close.rolling(window=int(n), min_periods=min_periods).mean()
    std = close.rolling(window=int(n), min_periods=min_periods).std()
    return pd.DataFrame({
        "boll_mid": mid,
        "boll_upper": mid + k * std,
        "boll_lower": mid - k * std,
    })
