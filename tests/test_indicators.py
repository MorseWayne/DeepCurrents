import pandas as pd
import numpy as np
import pytest
from src.utils.indicators import ma, ema, macd, rsi, boll


def _close(values):
    return pd.Series(values, dtype=float)


def test_ma_basic():
    c = _close([1, 2, 3, 4, 5])
    result = ma(c, 3)
    assert abs(result.iloc[-1] - 4.0) < 1e-9


def test_ema_basic():
    c = _close([1, 2, 3, 4, 5])
    result = ema(c, 3)
    assert result.iloc[-1] > 4.0


def test_macd_columns():
    c = _close(range(1, 35))
    result = macd(c)
    assert set(result.columns) == {"dif", "dea", "macd_hist"}


def test_rsi_range():
    c = _close([10, 11, 10, 12, 11, 13, 12, 14, 13, 15, 14, 16, 15, 17, 16])
    result = rsi(c, 14)
    valid = result.dropna()
    assert all(0 <= v <= 100 for v in valid)


def test_boll_columns():
    c = _close(range(1, 25))
    result = boll(c, 20)
    assert set(result.columns) == {"boll_mid", "boll_upper", "boll_lower"}


def test_boll_upper_gt_lower():
    c = _close(range(1, 25))
    result = boll(c, 20)
    last = result.iloc[-1]
    assert last["boll_upper"] > last["boll_lower"]
