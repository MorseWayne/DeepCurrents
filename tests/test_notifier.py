import pytest
import asyncio
from unittest.mock import MagicMock, AsyncMock, patch
from src.services.notifier import Notifier
from src.services.ai_service import DailyReport, GlobalEvent, InvestmentTrend

@pytest.mark.asyncio
async def test_notifier_formatting():
    notifier = Notifier()
    report = DailyReport(
        date="2026-03-12",
        intelligenceDigest=[],
        executiveSummary="Summary",
        globalEvents=[GlobalEvent(title="Event 1", detail="Detail 1", threatLevel="high")],
        economicAnalysis="Analysis",
        investmentTrends=[InvestmentTrend(assetClass="Gold", trend="Bullish", rationale="R")]
    )

    # 验证 send_to_feishu 逻辑（Mock 网络请求）
    with patch('aiohttp.ClientSession.post') as mock_post:
        mock_resp = AsyncMock()
        mock_resp.status = 200
        mock_resp.__aenter__.return_value = mock_resp
        mock_post.return_value = mock_resp
        
        # 设置一个伪 URL 以便测试
        notifier.feishu_url = "http://mock.webhook"
        await notifier.send_to_feishu(report, 10, 2)
        
        mock_post.assert_called_once()
        args, kwargs = mock_post.call_args
        card = kwargs['json']
        assert "🌊 DeepCurrents" in card['card']['header']['title']['content']

if __name__ == "__main__":
    pytest.main([__file__])
