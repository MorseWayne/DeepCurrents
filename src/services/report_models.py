from __future__ import annotations

from typing import List, Literal, Optional

from pydantic import BaseModel, Field


class GlobalEvent(BaseModel):
    title: str
    detail: str
    category: Optional[str] = None
    threatLevel: Optional[str] = None


class InvestmentTrend(BaseModel):
    assetClass: str
    trend: Literal["Bullish", "Bearish", "Neutral"]
    rationale: str
    confidence: Optional[float] = Field(None, ge=0, le=100)
    timeframe: Optional[str] = None


class IntelSource(BaseModel):
    name: str
    tier: int
    url: Optional[str] = None


class IntelligenceItem(BaseModel):
    content: str
    category: str
    sources: List[IntelSource]
    credibility: str
    credibilityReason: str
    importance: str


class AgentInsights(BaseModel):
    macro: Optional[str] = None
    sentiment: Optional[str] = None


class MacroAnalystOutput(BaseModel):
    coreThesis: str
    keyDrivers: list[str]
    riskScenarios: list[str]
    watchpoints: list[str]
    confidence: Optional[float] = Field(None, ge=0, le=100)


class SentimentAnalystOutput(BaseModel):
    marketRegime: str
    sentimentDrivers: list[str]
    crossAssetSignals: list[str]
    positioningRisks: list[str]
    confidence: Optional[float] = Field(None, ge=0, le=100)


class DailyReport(BaseModel):
    date: str
    intelligenceDigest: List[IntelligenceItem]
    executiveSummary: str
    globalEvents: List[GlobalEvent]
    economicAnalysis: str
    investmentTrends: List[InvestmentTrend]
    agentInsights: Optional[AgentInsights] = None
    riskAssessment: Optional[str] = None
    sourceAnalysis: Optional[str] = None


__all__ = [
    "AgentInsights",
    "DailyReport",
    "GlobalEvent",
    "IntelligenceItem",
    "IntelSource",
    "InvestmentTrend",
    "MacroAnalystOutput",
    "SentimentAnalystOutput",
]
