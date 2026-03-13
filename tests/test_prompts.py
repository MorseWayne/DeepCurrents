from __future__ import annotations

from src.services.prompts import (
    MACRO_ANALYST_PROMPT_V2,
    MARKET_STRATEGIST_PROMPT_V2,
    SENTIMENT_ANALYST_PROMPT_V2,
    build_macro_analyst_input,
    build_market_strategist_input,
    build_sentiment_analyst_input,
)


def test_prompt_v2_mentions_event_theme_market_context():
    assert "event briefs" in MACRO_ANALYST_PROMPT_V2
    assert "theme briefs" in MACRO_ANALYST_PROMPT_V2
    assert "market context" in MACRO_ANALYST_PROMPT_V2
    assert "event/theme/market context" in MARKET_STRATEGIST_PROMPT_V2
    assert "risk-on" in SENTIMENT_ANALYST_PROMPT_V2


def test_prompt_input_helpers_build_stable_sections():
    context_text = "[EVENT BRIEFS]\n- event 1\n\n[THEME BRIEFS]\n- theme 1"
    market_context = "[MARKET CONTEXT]\nTop movers up: CL=F (+1.40%)"

    macro_input = build_macro_analyst_input(context_text)
    sentiment_input = build_sentiment_analyst_input(context_text, market_context)
    strategist_input = build_market_strategist_input(
        context_text,
        {"coreThesis": "能源冲击再定价"},
        {"marketRegime": "Risk-off"},
        market_context,
    )

    assert "[EVENT/THEME/MARKET CONTEXT]" in macro_input
    assert "输出宏观分析 JSON" in macro_input
    assert "[MARKET CONTEXT]" in sentiment_input
    assert "输出情绪分析 JSON" in sentiment_input
    assert "[MACRO ANALYST OUTPUT]" in strategist_input
    assert '"coreThesis": "能源冲击再定价"' in strategist_input
    assert "[SENTIMENT ANALYST OUTPUT]" in strategist_input
