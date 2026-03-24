from __future__ import annotations

from src.utils.market_data import (
    build_market_context_snapshot,
    render_market_context_snapshot,
)


def test_build_market_context_snapshot_extracts_movers_and_signals():
    snapshot = build_market_context_snapshot(
        [
            {
                "symbol": "CL=F",
                "price": 72.4,
                "changePercent": 1.4,
                "timestamp": "2026-03-13T08:00:00+00:00",
            },
            {
                "symbol": "GC=F",
                "price": 2190.0,
                "changePercent": 0.8,
                "timestamp": "2026-03-13T08:00:00+00:00",
            },
            {
                "symbol": "DX-Y.NYB",
                "price": 104.2,
                "changePercent": 0.6,
                "timestamp": "2026-03-13T08:00:00+00:00",
            },
            {
                "symbol": "^GSPC",
                "price": 5080.0,
                "changePercent": -0.9,
                "timestamp": "2026-03-13T08:00:00+00:00",
            },
        ],
        top_n=2,
    )

    assert snapshot["as_of"] == "2026-03-13T08:00:00+00:00"
    assert snapshot["winners"] == [
        {"symbol": "CL=F", "change_percent": 1.4},
        {"symbol": "GC=F", "change_percent": 0.8},
    ]
    assert snapshot["losers"] == [
        {"symbol": "^GSPC", "change_percent": -0.9}
    ]
    assert "energy strength" in snapshot["cross_asset_signals"]
    assert "precious metals bid" in snapshot["cross_asset_signals"]
    assert "usd strength" in snapshot["cross_asset_signals"]
    assert "equity weakness" in snapshot["cross_asset_signals"]
    assert "Market snapshot tracks 4 instruments." in snapshot["summary"]


def test_render_market_context_snapshot_is_prompt_friendly():
    snapshot = build_market_context_snapshot(
        [
            {"symbol": "CL=F", "price": 72.4, "changePercent": 1.4},
            {"symbol": "^GSPC", "price": 5080.0, "changePercent": -0.9},
        ],
        as_of="2026-03-13T08:00:00+00:00",
    )

    rendered = render_market_context_snapshot(snapshot, max_items=2)

    assert "As of: 2026-03-13T08:00:00+00:00" in rendered
    assert "Top movers up: CL=F (+1.40%)" in rendered
    assert "Top movers down: ^GSPC (-0.90%)" in rendered
    assert "Cross-asset signals:" in rendered


import pytest


@pytest.mark.asyncio
async def test_get_asset_technical_analysis_shape():
    """get_asset_technical_analysis should return dict with rsi_14 / macd / boll keys"""
    import pandas as pd
    from unittest.mock import patch, MagicMock

    mock_df = pd.DataFrame({
        "Close": list(range(1, 35)),
        "High":  list(range(2, 36)),
        "Low":   list(range(0, 34)),
        "Volume": [1000] * 34,
    })

    with patch("yfinance.download", return_value=mock_df):
        from src.utils.market_data import get_asset_technical_analysis
        result = await get_asset_technical_analysis("SPY", days=34)

    assert "rsi_14" in result
    assert "macd_hist" in result
    assert "boll_upper" in result
    assert isinstance(result["rsi_14"], float)
