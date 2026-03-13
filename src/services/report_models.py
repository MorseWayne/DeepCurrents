from __future__ import annotations

from typing import List, Literal, Optional

from pydantic import BaseModel, Field


class MacroTransmissionStep(BaseModel):
    stage: str
    driver: str


class MacroTransmissionChain(BaseModel):
    headline: str
    shockSource: Optional[str] = None
    macroVariables: List[str] = Field(default_factory=list)
    marketPricing: Optional[str] = None
    allocationImplication: Optional[str] = None
    steps: List[MacroTransmissionStep] = Field(default_factory=list)
    timeframe: Optional[str] = None
    confidence: Optional[float] = Field(None, ge=0, le=100)


class AssetTransmissionBreakdown(BaseModel):
    assetClass: str
    trend: Literal["Bullish", "Bearish", "Neutral"]
    coreView: str
    transmissionPath: str
    keyDrivers: List[str] = Field(default_factory=list)
    watchSignals: List[str] = Field(default_factory=list)
    timeframe: Optional[str] = None
    confidence: Optional[float] = Field(None, ge=0, le=100)


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
    macroTransmissionChain: Optional[MacroTransmissionChain] = None
    globalEvents: List[GlobalEvent]
    economicAnalysis: str
    assetTransmissionBreakdowns: Optional[List[AssetTransmissionBreakdown]] = None
    investmentTrends: List[InvestmentTrend]
    agentInsights: Optional[AgentInsights] = None
    riskAssessment: Optional[str] = None
    sourceAnalysis: Optional[str] = None


__all__ = [
    "AgentInsights",
    "AssetTransmissionBreakdown",
    "DailyReport",
    "GlobalEvent",
    "IntelligenceItem",
    "IntelSource",
    "InvestmentTrend",
    "MacroAnalystOutput",
    "MacroTransmissionChain",
    "MacroTransmissionStep",
    "SentimentAnalystOutput",
]
