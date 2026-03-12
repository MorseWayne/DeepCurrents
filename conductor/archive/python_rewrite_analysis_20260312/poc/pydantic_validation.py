from pydantic import BaseModel, Field, validator
from typing import List, Optional, Literal
from datetime import datetime
import json

class IntelSource(BaseModel):
    name: str
    tier: int = Field(ge=1, le=4)
    url: Optional[str] = None

class IntelligenceItem(BaseModel):
    content: str
    category: str
    sources: List[IntelSource]
    credibility: Literal['high', 'medium', 'low']
    credibilityReason: str
    importance: Literal['critical', 'high', 'medium', 'low']

class GlobalEvent(BaseModel):
    title: str
    detail: str
    category: Optional[str] = None
    threatLevel: Optional[Literal['critical', 'high', 'medium', 'low', 'info']] = None

class InvestmentTrend(BaseModel):
    assetClass: str
    trend: Literal['Bullish', 'Bearish', 'Neutral']
    rationale: str
    confidence: Optional[float] = Field(None, ge=0, le=100)
    timeframe: Optional[str] = None

class DailyReport(BaseModel):
    date: str
    intelligenceDigest: List[IntelligenceItem]
    executiveSummary: str
    globalEvents: List[GlobalEvent]
    economicAnalysis: str
    investmentTrends: List[InvestmentTrend]
    riskAssessment: Optional[str] = None

def test_validation():
    # 模拟一个正确的 JSON
    valid_data = {
        "date": "2026-03-12",
        "intelligenceDigest": [
            {
                "content": "Gold prices hit new high",
                "category": "economics",
                "sources": [{"name": "Reuters", "tier": 1}],
                "credibility": "high",
                "credibilityReason": "Official source",
                "importance": "high"
            }
        ],
        "executiveSummary": "Global markets are stable.",
        "globalEvents": [{"title": "Fed Meeting", "detail": "Rates remain unchanged."}],
        "economicAnalysis": "Detailed analysis here...",
        "investmentTrends": [{"assetClass": "Gold", "trend": "Bullish", "rationale": "Safe haven"}]
    }
    
    print("Testing valid data...")
    report = DailyReport(**valid_data)
    print(f"Successfully validated report for date: {report.date}")
    
    # 模拟一个错误的 JSON（缺少必填字段）
    invalid_data = valid_data.copy()
    del invalid_data["executiveSummary"]
    
    print("\nTesting invalid data (missing executiveSummary)...")
    try:
        DailyReport(**invalid_data)
    except Exception as e:
        print(f"Validation failed as expected: {e}")

if __name__ == "__main__":
    test_validation()
