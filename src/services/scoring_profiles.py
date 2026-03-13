from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ScoringProfile:
    name: str
    label: str
    description: str
    threat_score: float
    market_impact_score: float
    novelty_score: float
    corroboration_score: float
    source_quality_score: float
    velocity_score: float
    uncertainty_penalty: float

    def weights(self) -> dict[str, float]:
        return {
            "threat_score": self.threat_score,
            "market_impact_score": self.market_impact_score,
            "novelty_score": self.novelty_score,
            "corroboration_score": self.corroboration_score,
            "source_quality_score": self.source_quality_score,
            "velocity_score": self.velocity_score,
            "uncertainty_penalty": self.uncertainty_penalty,
        }


_SCORING_PROFILES: dict[str, ScoringProfile] = {
    "macro_daily": ScoringProfile(
        name="macro_daily",
        label="Macro Daily",
        description="Macro daily report prioritizes market impact, novelty and corroboration.",
        threat_score=0.14,
        market_impact_score=0.24,
        novelty_score=0.18,
        corroboration_score=0.18,
        source_quality_score=0.14,
        velocity_score=0.08,
        uncertainty_penalty=0.12,
    ),
    "risk_daily": ScoringProfile(
        name="risk_daily",
        label="Risk Daily",
        description="Risk daily emphasizes threat escalation, corroboration and velocity.",
        threat_score=0.28,
        market_impact_score=0.12,
        novelty_score=0.1,
        corroboration_score=0.2,
        source_quality_score=0.12,
        velocity_score=0.18,
        uncertainty_penalty=0.18,
    ),
    "strategy_am": ScoringProfile(
        name="strategy_am",
        label="Strategy AM",
        description="Strategy morning profile emphasizes market impact, novelty and source quality.",
        threat_score=0.06,
        market_impact_score=0.3,
        novelty_score=0.22,
        corroboration_score=0.12,
        source_quality_score=0.18,
        velocity_score=0.08,
        uncertainty_penalty=0.12,
    ),
}


def get_scoring_profile(name: str) -> ScoringProfile:
    normalized = name.strip().lower()
    profile = _SCORING_PROFILES.get(normalized)
    if profile is None:
        raise ValueError(f"Unknown scoring profile: {name}")
    return profile


def list_scoring_profiles() -> list[ScoringProfile]:
    return list(_SCORING_PROFILES.values())


__all__ = ["ScoringProfile", "get_scoring_profile", "list_scoring_profiles"]
