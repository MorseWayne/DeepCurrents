from __future__ import annotations

from src.services.report_models import (
    AgentInsights,
    DailyReport,
    GlobalEvent,
    IntelligenceItem,
    IntelSource,
    InvestmentTrend,
    MacroAnalystOutput,
    SentimentAnalystOutput,
)


def test_daily_report_models_instantiate_cleanly():
    report = DailyReport(
        date="2026-03-13",
        intelligenceDigest=[
            IntelligenceItem(
                content="油运风险上升",
                category="energy",
                sources=[IntelSource(name="Reuters", tier=1, url="https://example.com")],
                credibility="high",
                credibilityReason="多源交叉验证",
                importance="high",
            )
        ],
        executiveSummary="主线是能源与运价冲击。",
        globalEvents=[
            GlobalEvent(
                title="红海航运扰动",
                detail="袭击推动运价与原油风险溢价上升。",
                category="conflict",
                threatLevel="high",
            )
        ],
        economicAnalysis="能源价格上行增加通胀粘性。",
        investmentTrends=[
            InvestmentTrend(
                assetClass="Brent",
                trend="Bullish",
                rationale="供应与运价风险抬升。",
                confidence=82,
                timeframe="short-term",
            )
        ],
        agentInsights=AgentInsights(
            macro="通胀风险回升",
            sentiment="risk-off 边际抬升",
        ),
    )

    assert report.globalEvents[0].title == "红海航运扰动"
    assert report.investmentTrends[0].trend == "Bullish"
    assert report.agentInsights is not None


def test_analyst_output_models_capture_v2_schema():
    macro = MacroAnalystOutput(
        coreThesis="能源冲击重新推高通胀尾部风险。",
        keyDrivers=["航运扰动", "原油上涨"],
        riskScenarios=["冲突升级", "供应进一步中断"],
        watchpoints=["保险成本", "OPEC 表态"],
        confidence=78,
    )
    sentiment = SentimentAnalystOutput(
        marketRegime="Risk-off",
        sentimentDrivers=["避险买盘", "美元走强"],
        crossAssetSignals=["能源走强", "股指走弱"],
        positioningRisks=["原油多头拥挤"],
        confidence=72,
    )

    assert macro.keyDrivers == ["航运扰动", "原油上涨"]
    assert sentiment.marketRegime == "Risk-off"
