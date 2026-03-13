from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class ContextQuotaPolicy:
    name: str
    event_budget_share: float
    theme_budget_share: float
    market_budget_share: float
    max_events_per_theme: int
    max_events_per_region: int
    max_region_themes: int
    prefer_taxonomy_themes: bool = True

    def allocate_budget(self, token_budget: int) -> dict[str, int]:
        normalized_budget = max(int(token_budget), 0)
        market_budget = int(normalized_budget * self.market_budget_share)
        theme_budget = int(normalized_budget * self.theme_budget_share)
        event_budget = max(0, normalized_budget - market_budget - theme_budget)
        return {
            "event_budget": event_budget,
            "theme_budget": theme_budget,
            "market_budget": market_budget,
        }

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


_POLICIES: dict[str, ContextQuotaPolicy] = {
    "macro_daily": ContextQuotaPolicy(
        name="macro_daily",
        event_budget_share=0.55,
        theme_budget_share=0.20,
        market_budget_share=0.25,
        max_events_per_theme=2,
        max_events_per_region=2,
        max_region_themes=1,
        prefer_taxonomy_themes=True,
    ),
    "risk_daily": ContextQuotaPolicy(
        name="risk_daily",
        event_budget_share=0.65,
        theme_budget_share=0.15,
        market_budget_share=0.20,
        max_events_per_theme=3,
        max_events_per_region=2,
        max_region_themes=1,
        prefer_taxonomy_themes=True,
    ),
    "strategy_am": ContextQuotaPolicy(
        name="strategy_am",
        event_budget_share=0.45,
        theme_budget_share=0.20,
        market_budget_share=0.35,
        max_events_per_theme=2,
        max_events_per_region=2,
        max_region_themes=1,
        prefer_taxonomy_themes=True,
    ),
}


def get_context_quota_policy(profile: str) -> ContextQuotaPolicy:
    normalized = str(profile or "").strip()
    if normalized in _POLICIES:
        return _POLICIES[normalized]
    raise ValueError(f"unknown context quota profile: {normalized or '<empty>'}")


__all__ = ["ContextQuotaPolicy", "get_context_quota_policy"]
