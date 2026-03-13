from __future__ import annotations

from src.services.report_models import (
    AgentInsights,
    AssetTransmissionBreakdown,
    DailyReport,
    GlobalEvent,
    IntelligenceItem,
    IntelSource,
    InvestmentTrend,
    MacroAnalystOutput,
    MacroTransmissionChain,
    MacroTransmissionStep,
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
        macroTransmissionChain=MacroTransmissionChain(
            headline="能源与航运扰动正在通过通胀预期重定价跨资产。",
            shockSource="航运扰动升级",
            macroVariables=["能源供给预期", "通胀预期"],
            marketPricing="原油与黄金偏强，风险资产承压。",
            allocationImplication="优先配置能源链与防御性资产。",
            steps=[
                MacroTransmissionStep(stage="冲击源", driver="航运扰动升级"),
                MacroTransmissionStep(stage="宏观变量", driver="能源供给预期与通胀预期上修"),
            ],
            timeframe="short-term",
            confidence=81,
        ),
        globalEvents=[
            GlobalEvent(
                title="红海航运扰动",
                detail="袭击推动运价与原油风险溢价上升。",
                category="conflict",
                threatLevel="high",
            )
        ],
        economicAnalysis="能源价格上行增加通胀粘性。",
        assetTransmissionBreakdowns=[
            AssetTransmissionBreakdown(
                assetClass="Brent",
                trend="Bullish",
                coreView="原油更直接表达供给收缩预期。",
                transmissionPath="航运扰动 -> 供给预期收紧 -> 原油风险溢价抬升 -> Brent 偏强",
                keyDrivers=["能源供给预期", "航运风险"],
                watchSignals=["运价", "库存"],
                timeframe="short-term",
                confidence=82,
            )
        ],
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
    assert report.macroTransmissionChain is not None
    assert report.assetTransmissionBreakdowns is not None
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
