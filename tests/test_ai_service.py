import pytest
import asyncio
from unittest.mock import MagicMock, AsyncMock, patch
from src.services.ai_service import AIService, DailyReport, DEFAULT_CONTEXT_WINDOW
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

    with patch.object(AIService, '_resolve_shared_context_window', new_callable=AsyncMock, return_value=(16000, {"Primary:gpt-4o": 16000})):
        with patch.object(AIService, 'build_market_price_context', new_callable=AsyncMock, return_value='[REAL-TIME MARKET DATA]'):
            with patch.object(AIService, 'call_agent', side_effect=[mock_macro, mock_sentiment, mock_final]):
                report = await ai_service.generate_daily_report(mock_news)
                
                assert isinstance(report, DailyReport)
                assert report.date == "2026-03-12"
                assert report.executiveSummary == "Summary"
                assert ai_service.last_report_metrics["report_generated"] is True
                assert ai_service.last_report_metrics["raw_news_input_count"] == 1
                assert ai_service.last_report_metrics["cluster_count"] == 0
                assert ai_service.last_report_metrics["guard_pre_tokens"] >= ai_service.last_report_metrics["guard_post_tokens"]

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

    with patch.object(AIService, '_resolve_shared_context_window', new_callable=AsyncMock, return_value=(16000, {"Primary:gpt-4o": 16000})):
        with patch.object(AIService, 'build_market_price_context', new_callable=AsyncMock, return_value='[REAL-TIME MARKET DATA]'):
            with patch.object(AIService, 'call_agent', side_effect=[mock_macro, mock_sentiment, broken_final, repaired_final]) as mock_call:
                report = await ai_service.generate_daily_report(mock_news)

                assert isinstance(report, DailyReport)
                assert report.date == "2026-03-12"
                assert report.executiveSummary == "Summary"
                assert mock_call.call_count == 4


@pytest.mark.asyncio
async def test_parse_daily_report_json_normalizes_legacy_schema(mock_db):
    ai_service = AIService(mock_db)
    legacy_payload = """{
        "date": "2026-03-13",
        "intelligenceDigest": [
            {"topic": "宏观主线", "confidence": 0.82, "evidence": "多源交叉验证"}
        ],
        "executiveSummary": "主线总结",
        "globalEvents": [
            {"region": "Global", "description": "能源与航运风险抬升", "severity": "high"}
        ],
        "economicAnalysis": "宏观分析",
        "investmentTrends": [
            {"theme": "原油与航运", "trend": "建议偏多配置", "horizon": "中短期"}
        ]
    }"""

    parsed = await ai_service.parse_daily_report_json(legacy_payload)
    report = DailyReport(**parsed)

    assert report.intelligenceDigest[0].content == "宏观主线"
    assert report.intelligenceDigest[0].importance in {"critical", "high", "medium", "low"}
    assert report.globalEvents[0].title == "Global"
    assert report.globalEvents[0].threatLevel == "high"
    assert report.investmentTrends[0].assetClass == "原油与航运"
    assert report.investmentTrends[0].trend == "Bullish"
    assert report.investmentTrends[0].timeframe == "中短期"


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

    with patch.object(AIService, '_resolve_shared_context_window', new_callable=AsyncMock, return_value=(16000, {"Primary:gpt-4o": 16000})):
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

    with patch.object(AIService, '_resolve_shared_context_window', new_callable=AsyncMock, return_value=(16000, {"Primary:gpt-4o": 16000})):
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


@pytest.mark.asyncio
async def test_resolve_shared_context_window_uses_min_provider_window(mock_db):
    ai_service = AIService(mock_db)
    providers = [
        {"name": "Primary", "url": "https://a.example/v1/chat/completions", "key": "k1", "model": "m1"},
        {"name": "Fallback", "url": "https://b.example/v1/chat/completions", "key": "k2", "model": "m2"},
    ]
    with patch.object(AIService, '_active_providers', return_value=providers):
        with patch.object(AIService, '_fetch_provider_model_window', new_callable=AsyncMock, side_effect=[64000, 32000]):
            baseline, windows = await ai_service._resolve_shared_context_window()
            assert baseline == 32000
            assert windows["Primary:m1"] == 64000
            assert windows["Fallback:m2"] == 32000


@pytest.mark.asyncio
async def test_fetch_provider_model_window_falls_back_to_default_when_metadata_and_mapping_fail(mock_db):
    ai_service = AIService(mock_db)
    provider = {"name": "Primary", "url": "https://api.example.com/v1/chat/completions", "key": "k", "model": "unknown-model"}
    mock_client = MagicMock()
    mock_client.models.retrieve = AsyncMock(side_effect=RuntimeError("metadata unavailable"))
    with patch("src.services.ai_service.AsyncOpenAI", return_value=mock_client):
        window = await ai_service._fetch_provider_model_window(provider)
    assert window == DEFAULT_CONTEXT_WINDOW


def test_build_news_context_degrades_to_header_only(mock_db):
    ai_service = AIService(mock_db)
    news = [
        NewsRecord(
            id='1',
            url='u1',
            title='Very Important Headline',
            content='A' * 2000,
            category='C',
            timestamp='2026-03-12T12:00:00',
            threatLevel='high',
            tier=1,
        )
    ]
    full_context, full_tokens = ai_service.build_news_context(news, 9999)
    header_only_context, header_only_tokens = ai_service.build_news_context(news, 30)

    assert full_tokens > header_only_tokens
    assert '▸' in full_context
    assert '▸' not in header_only_context
    assert header_only_tokens <= 30


def test_guard_final_strategist_input_trims_oversized_payload(mock_db):
    ai_service = AIService(mock_db)
    news = [
        NewsRecord(
            id='1',
            url='u1',
            title='Headline 1',
            content='B' * 3000,
            category='C',
            timestamp='2026-03-12T12:00:00',
            threatLevel='high',
            tier=1,
        ),
        NewsRecord(
            id='2',
            url='u2',
            title='Headline 2',
            content='C' * 3000,
            category='C',
            timestamp='2026-03-12T12:00:00',
            threatLevel='low',
            tier=4,
        ),
    ]
    news_context, _ = ai_service.build_news_context(news, 5000)
    macro = '{"macro":"' + ('x' * 8000) + '"}'
    sentiment = '{"sentiment":"' + ('y' * 8000) + '"}'
    market = '[REAL-TIME MARKET DATA]\n- GC=F: 2500'
    final_input, stats = ai_service._guard_final_strategist_input(
        news_list=news,
        clusters=None,
        macro_out=macro,
        sentiment_out=sentiment,
        market_price_context=market,
        usable_budget=400,
        news_context=news_context,
        cluster_context='',
    )
    assert stats["post_guard_tokens"] <= 400
    assert len(stats["trimmed_sections"]) > 0
    assert isinstance(final_input, str) and len(final_input) > 0

if __name__ == "__main__":
    pytest.main([__file__])
