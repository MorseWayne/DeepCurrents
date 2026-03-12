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

    with patch.object(AIService, 'call_agent', side_effect=[mock_macro, mock_sentiment, mock_final]):
        report = await ai_service.generate_daily_report(mock_news)
        
        assert isinstance(report, DailyReport)
        assert report.date == "2026-03-12"
        assert report.executiveSummary == "Summary"

if __name__ == "__main__":
    pytest.main([__file__])
