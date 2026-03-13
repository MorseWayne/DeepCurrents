import pytest
from unittest.mock import AsyncMock, patch

from src.services.notifier import Notifier
from src.services.report_models import (
    AssetTransmissionBreakdown,
    DailyReport,
    GlobalEvent,
    InvestmentTrend,
    MacroTransmissionChain,
    MacroTransmissionStep,
)


@pytest.mark.asyncio
async def test_notifier_formatting_uses_threat_labels():
    notifier = Notifier()
    report = DailyReport(
        date="2026-03-12",
        intelligenceDigest=[],
        executiveSummary="Summary",
        macroTransmissionChain=MacroTransmissionChain(
            headline="能源主线正在通过通胀预期重定价跨资产。",
            shockSource="航运扰动",
            macroVariables=["能源供给预期", "通胀预期"],
            marketPricing="原油偏强，风险资产承压。",
            allocationImplication="优先配置能源链。",
            steps=[MacroTransmissionStep(stage="冲击源", driver="航运扰动升级")],
        ),
        globalEvents=[
            GlobalEvent(title="Event 1", detail="Detail 1", threatLevel="high")
        ],
        economicAnalysis="Analysis",
        assetTransmissionBreakdowns=[
            AssetTransmissionBreakdown(
                assetClass="Gold",
                trend="Bullish",
                coreView="黄金承接部分防御需求。",
                transmissionPath="风险溢价上行 -> 黄金受益",
            ),
            AssetTransmissionBreakdown(
                assetClass="Crude Oil",
                trend="Bullish",
                coreView="原油更直接表达供给收缩预期。",
                transmissionPath="供给预期收紧 -> 原油风险溢价抬升",
            ),
        ],
        investmentTrends=[
            InvestmentTrend(assetClass="Gold", trend="Bullish", rationale="R")
        ],
    )

    with patch("aiohttp.ClientSession.post") as mock_post:
        mock_resp = AsyncMock()
        mock_resp.status = 200
        mock_resp.__aenter__.return_value = mock_resp
        mock_post.return_value = mock_resp

        notifier.feishu_url = "http://mock.webhook"
        await notifier.send_to_feishu(report, 10, 2)

        card = mock_post.call_args.kwargs["json"]
        content = card["card"]["elements"][0]["content"]
        assert "🌊 DeepCurrents" in card["card"]["header"]["title"]["content"]
        assert "总主线传导链 | Macro Transmission" in content
        assert "关键资产拆解 | Asset Breakdown" in content
        assert "🟠 HIGH Event 1" in content


if __name__ == "__main__":
    pytest.main([__file__])
