import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.services.ai_service import AIService, DailyReport, DEFAULT_CONTEXT_WINDOW


@pytest.fixture
def mock_prediction_repository():
    repository = MagicMock()
    repository.save_prediction = AsyncMock(return_value="pred_1")
    return repository


@pytest.mark.asyncio
async def test_parse_daily_report_json_normalizes_legacy_schema(
    mock_prediction_repository,
):
    ai_service = AIService(mock_prediction_repository)
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
async def test_resolve_shared_context_window_uses_min_provider_window(
    mock_prediction_repository,
):
    ai_service = AIService(mock_prediction_repository)
    providers = [
        {"name": "Primary", "url": "https://a.example/v1/chat/completions", "key": "k1", "model": "m1"},
        {"name": "Fallback", "url": "https://b.example/v1/chat/completions", "key": "k2", "model": "m2"},
    ]
    with patch.object(AIService, "_active_providers", return_value=providers):
        with patch.object(
            AIService,
            "_fetch_provider_model_window",
            new_callable=AsyncMock,
            side_effect=[64000, 32000],
        ):
            baseline, windows = await ai_service._resolve_shared_context_window()
            assert baseline == 32000
            assert windows["Primary:m1"] == 64000
            assert windows["Fallback:m2"] == 32000


@pytest.mark.asyncio
async def test_fetch_provider_model_window_falls_back_to_default_when_metadata_and_mapping_fail(
    mock_prediction_repository,
):
    ai_service = AIService(mock_prediction_repository)
    provider = {
        "name": "Primary",
        "url": "https://api.example.com/v1/chat/completions",
        "key": "k",
        "model": "unknown-model",
    }
    mock_client = MagicMock()
    mock_client.models.retrieve = AsyncMock(side_effect=RuntimeError("metadata unavailable"))
    with patch("src.services.ai_service.AsyncOpenAI", return_value=mock_client):
        window = await ai_service._fetch_provider_model_window(provider)
    assert window == DEFAULT_CONTEXT_WINDOW


@pytest.mark.asyncio
async def test_persist_predictions_uses_resolved_symbol(mock_prediction_repository):
    ai_service = AIService(mock_prediction_repository)
    report = DailyReport(
        date="2026-03-12",
        intelligenceDigest=[],
        executiveSummary="Summary",
        globalEvents=[],
        economicAnalysis="Analysis",
        investmentTrends=[
            {
                "assetClass": "Gold",
                "trend": "Bullish",
                "rationale": "Inflation hedge",
            }
        ],
    )

    with patch("src.services.ai_service.get_market_price", new_callable=AsyncMock) as mock_market:
        mock_market.return_value = {"price": 2500.0}
        await ai_service._persist_predictions(report)

    mock_prediction_repository.save_prediction.assert_awaited_once()
    payload = mock_prediction_repository.save_prediction.await_args.args[0]
    assert payload["asset"] == "GC=F"
    assert payload["type"] == "bullish"


@pytest.mark.asyncio
async def test_persist_predictions_auto_resolves_symbol_by_search(
    mock_prediction_repository,
):
    ai_service = AIService(mock_prediction_repository)
    report = DailyReport(
        date="2026-03-12",
        intelligenceDigest=[],
        executiveSummary="Summary",
        globalEvents=[],
        economicAnalysis="Analysis",
        investmentTrends=[
            {
                "assetClass": "Silver spot",
                "trend": "Bullish",
                "rationale": "Industrial demand",
            }
        ],
    )

    with patch("src.services.ai_service.resolve_asset_symbol", return_value=None):
        with patch(
            "src.services.ai_service.search_market_symbol",
            new_callable=AsyncMock,
            return_value="SI=F",
        ) as mock_search:
            with patch(
                "src.services.ai_service.get_market_price",
                new_callable=AsyncMock,
                return_value={"price": 30.0},
            ):
                await ai_service._persist_predictions(report)

    mock_search.assert_awaited_once_with("Silver spot")
    payload = mock_prediction_repository.save_prediction.await_args.args[0]
    assert payload["asset"] == "SI=F"


if __name__ == "__main__":
    pytest.main([__file__])
