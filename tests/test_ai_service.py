import pytest
import asyncio
from unittest.mock import MagicMock, AsyncMock, patch
from src.services.ai_service import AIService, DailyReport
from src.services.db_service import NewsRecord

@pytest.fixture
def mock_db():
    return MagicMock()

@pytest.mark.asyncio
async def test_generate_daily_report(mock_db):
    ai_service = AIService(mock_db)
    
    mock_news = [
        NewsRecord(id='1', url='u1', title='T1', content='C1', category='C', timestamp='2026-03-12T12:00:00', threatLevel='high')
    ]

    # Mock call_agent
    mock_macro = '{"keyDrivers": []}'
    mock_sentiment = '{"marketRegime": "Neutral"}'
    mock_final = """{
        "date": "2026-03-12",
        "intelligenceDigest": [],
        "executiveSummary": "Summary",
        "globalEvents": [],
        "economicAnalysis": "Analysis",
        "investmentTrends": []
    }"""

    with patch.object(AIService, 'build_market_price_context', new_callable=AsyncMock, return_value='[REAL-TIME MARKET DATA]'):
        with patch.object(AIService, 'call_agent', side_effect=[mock_macro, mock_sentiment, mock_final]):
            report = await ai_service.generate_daily_report(mock_news)
            
            assert isinstance(report, DailyReport)
            assert report.date == "2026-03-12"
            assert report.executiveSummary == "Summary"

@pytest.mark.asyncio
async def test_generate_daily_report_with_json_repair(mock_db):
    ai_service = AIService(mock_db)

    mock_news = [
        NewsRecord(id='1', url='u1', title='T1', content='C1', category='C', timestamp='2026-03-12T12:00:00', threatLevel='high')
    ]

    # 第三次返回无效 JSON，触发修复链路；第四次返回修复后的合法 JSON
    mock_macro = '{"keyDrivers": []}'
    mock_sentiment = '{"marketRegime": "Neutral"}'
    broken_final = '{"date":"2026-03-12","intelligenceDigest":[]'
    repaired_final = """{
        "date": "2026-03-12",
        "intelligenceDigest": [],
        "executiveSummary": "Summary",
        "globalEvents": [],
        "economicAnalysis": "Analysis",
        "investmentTrends": []
    }"""

    with patch.object(AIService, 'build_market_price_context', new_callable=AsyncMock, return_value='[REAL-TIME MARKET DATA]'):
        with patch.object(AIService, 'call_agent', side_effect=[mock_macro, mock_sentiment, broken_final, repaired_final]) as mock_call:
            report = await ai_service.generate_daily_report(mock_news)

            assert isinstance(report, DailyReport)
            assert report.date == "2026-03-12"
            assert report.executiveSummary == "Summary"
            assert mock_call.call_count == 4


@pytest.mark.asyncio
async def test_generate_daily_report_persists_predictions(mock_db):
    ai_service = AIService(mock_db)
    ai_service.db.save_prediction = AsyncMock()

    mock_news = [
        NewsRecord(id='1', url='u1', title='T1', content='C1', category='C', timestamp='2026-03-12T12:00:00', threatLevel='high')
    ]
    mock_macro = '{"keyDrivers": []}'
    mock_sentiment = '{"marketRegime": "Neutral"}'
    mock_final = """{
        "date": "2026-03-12",
        "intelligenceDigest": [],
        "executiveSummary": "Summary",
        "globalEvents": [],
        "economicAnalysis": "Analysis",
        "investmentTrends": [
            {"assetClass": "Gold", "trend": "Bullish", "rationale": "Inflation hedge"}
        ]
    }"""

    with patch.object(AIService, 'build_market_price_context', new_callable=AsyncMock, return_value='[REAL-TIME MARKET DATA]'):
        with patch.object(AIService, 'call_agent', side_effect=[mock_macro, mock_sentiment, mock_final]):
            with patch('src.services.ai_service.get_market_price', new_callable=AsyncMock) as mock_market:
                mock_market.return_value = {"price": 2500.0}
                report = await ai_service.generate_daily_report(mock_news)

                assert isinstance(report, DailyReport)
                ai_service.db.save_prediction.assert_called_once()
                call_data = ai_service.db.save_prediction.call_args.args[0]
                assert call_data["asset"] == "GC=F"
                assert call_data["type"] == "bullish"


@pytest.mark.asyncio
async def test_generate_daily_report_auto_resolves_symbol_by_search(mock_db):
    ai_service = AIService(mock_db)
    ai_service.db.save_prediction = AsyncMock()

    mock_news = [
        NewsRecord(id='1', url='u1', title='T1', content='C1', category='C', timestamp='2026-03-12T12:00:00', threatLevel='high')
    ]
    mock_macro = '{"keyDrivers": []}'
    mock_sentiment = '{"marketRegime": "Neutral"}'
    mock_final = """{
        "date": "2026-03-12",
        "intelligenceDigest": [],
        "executiveSummary": "Summary",
        "globalEvents": [],
        "economicAnalysis": "Analysis",
        "investmentTrends": [
            {"assetClass": "Silver spot", "trend": "Bullish", "rationale": "Industrial demand"}
        ]
    }"""

    with patch.object(AIService, 'build_market_price_context', new_callable=AsyncMock, return_value='[REAL-TIME MARKET DATA]'):
        with patch.object(AIService, 'call_agent', side_effect=[mock_macro, mock_sentiment, mock_final]):
            with patch('src.services.ai_service.resolve_asset_symbol', return_value=None):
                with patch('src.services.ai_service.search_market_symbol', new_callable=AsyncMock, return_value="SI=F") as mock_search:
                    with patch('src.services.ai_service.get_market_price', new_callable=AsyncMock) as mock_market:
                        mock_market.return_value = {"price": 30.0}
                        report = await ai_service.generate_daily_report(mock_news)

                        assert isinstance(report, DailyReport)
                        mock_search.assert_called_once_with("Silver spot")
                        ai_service.db.save_prediction.assert_called_once()
                        call_data = ai_service.db.save_prediction.call_args.args[0]
                        assert call_data["asset"] == "SI=F"

if __name__ == "__main__":
    pytest.main([__file__])
