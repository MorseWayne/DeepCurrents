import pytest
from unittest.mock import AsyncMock, patch

from src.services.notifier import Notifier
from src.services.report_models import DailyReport, GlobalEvent, InvestmentTrend


@pytest.mark.asyncio
async def test_notifier_formatting_uses_threat_labels():
    notifier = Notifier()
    report = DailyReport(
        date="2026-03-12",
        intelligenceDigest=[],
        executiveSummary="Summary",
        globalEvents=[
            GlobalEvent(title="Event 1", detail="Detail 1", threatLevel="high")
        ],
        economicAnalysis="Analysis",
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
        assert "🟠 HIGH Event 1" in content


if __name__ == "__main__":
    pytest.main([__file__])
