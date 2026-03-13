from __future__ import annotations

import pytest

from src.services.context_quota_policy import get_context_quota_policy


def test_context_quota_policy_returns_expected_profiles():
    macro = get_context_quota_policy("macro_daily")
    risk = get_context_quota_policy("risk_daily")
    strategy = get_context_quota_policy("strategy_am")

    assert macro.market_budget_share == pytest.approx(0.25)
    assert risk.event_budget_share == pytest.approx(0.65)
    assert strategy.market_budget_share == pytest.approx(0.35)
    assert risk.max_events_per_theme == 3
    assert strategy.max_region_themes == 1
    assert macro.prefer_taxonomy_themes is True


def test_context_quota_policy_allocate_budget_is_stable():
    policy = get_context_quota_policy("strategy_am")

    budgets = policy.allocate_budget(1000)

    assert budgets == {
        "event_budget": 450,
        "theme_budget": 200,
        "market_budget": 350,
    }


def test_context_quota_policy_raises_for_unknown_profile():
    with pytest.raises(ValueError, match="unknown context quota profile: intraday"):
        get_context_quota_policy("intraday")
