import sys
from datetime import UTC, date, datetime
from types import ModuleType, SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.engine import DeepCurrentsEngine, REPORT_EVENT_STATUSES
from src.services.event_intelligence_bootstrap import (
    EventIntelligenceRuntimeConfig,
    EventIntelligenceRuntimeState,
)


@pytest.fixture
def engine():
    return DeepCurrentsEngine()


@pytest.mark.asyncio
async def test_engine_collect_data(engine):
    engine.collector.collect_all = AsyncMock(
        return_value={"new_items": 5, "errors": 0, "articles_inserted": 5}
    )

    with patch("src.engine.log_stage_metrics") as mock_log_metrics:
        await engine.collect_data()

    engine.collector.collect_all.assert_called_once()
    mock_log_metrics.assert_called_once()
    assert mock_log_metrics.call_args.args[1] == "ingestion"


@pytest.mark.asyncio
async def test_engine_start_bootstraps_runtime(engine):
    engine.prediction_repository.connect = AsyncMock()
    engine.event_intelligence.start = AsyncMock(
        return_value=EventIntelligenceRuntimeState(enabled=False)
    )
    engine._configure_event_intelligence_ingestion = MagicMock()
    engine._configure_event_intelligence_reporting = MagicMock()
    engine.collect_data = AsyncMock()
    engine.scorer.run_scoring_task = AsyncMock()

    await engine.start()

    engine.prediction_repository.connect.assert_called_once()
    engine.event_intelligence.start.assert_called_once()
    engine._configure_event_intelligence_ingestion.assert_called_once_with(
        EventIntelligenceRuntimeState(enabled=False)
    )
    engine._configure_event_intelligence_reporting.assert_called_once_with(
        EventIntelligenceRuntimeState(enabled=False)
    )
    engine.collect_data.assert_called_once()
    engine.scorer.run_scoring_task.assert_called_once()


@pytest.mark.asyncio
async def test_engine_stop_closes_prediction_repository(engine):
    engine._runtime_ready = True
    engine.event_intelligence.stop = AsyncMock()
    engine.prediction_repository.close = AsyncMock()

    await engine.stop()

    engine.event_intelligence.stop.assert_called_once()
    engine.prediction_repository.close.assert_called_once()


@pytest.mark.asyncio
async def test_engine_generate_report_flow_uses_event_orchestrator(engine):
    report = MagicMock(date="2026-03-13", investmentTrends=[])
    latest_run = {"updated_at": datetime(2026, 3, 13, 6, 0, tzinfo=UTC)}
    engine._report_profile = "risk_daily"
    engine._report_repository = MagicMock()
    engine._report_repository.get_latest_report_run = AsyncMock(return_value=latest_run)
    engine._report_orchestrator = MagicMock()
    engine._report_orchestrator.generate_event_centric_report = AsyncMock(
        return_value=report
    )
    engine._report_orchestrator.last_report_metrics = {
        "profile": "risk_daily",
        "context_event_count": 2,
        "context_theme_count": 1,
        "cluster_count": 1,
        "report_generated": True,
        "investment_trend_count": 0,
        "guard_pre_tokens": 100,
        "guard_post_tokens": 80,
        "trimmed_sections": ["context"],
        "budget_truncation_rate": 0.2,
        "final_hard_cap_hit": False,
    }
    engine._report_orchestrator.last_report_guard_stats = {
        "pre_guard_tokens": 100,
        "post_guard_tokens": 80,
        "trimmed_sections": ["context"],
    }
    engine.notifier.deliver_all = AsyncMock()

    with patch("src.engine.log_stage_metrics") as mock_log_metrics:
        result = await engine.generate_and_send_report()

    assert result is report
    engine._report_repository.get_latest_report_run.assert_called_once_with("risk_daily")
    engine._report_orchestrator.generate_event_centric_report.assert_called_once()
    report_call = engine._report_orchestrator.generate_event_centric_report.call_args
    assert report_call.kwargs["statuses"] == REPORT_EVENT_STATUSES
    assert report_call.kwargs["since"] == datetime(2026, 3, 13, 6, 0, tzinfo=UTC)
    assert report_call.kwargs["profile"] == "risk_daily"
    assert isinstance(report_call.kwargs["report_date"], date)
    engine.notifier.deliver_all.assert_called_once_with(report, 0, 2)
    mock_log_metrics.assert_called_once()
    assert mock_log_metrics.call_args.args[1] == "report"
    assert mock_log_metrics.call_args.args[2]["report_generated"] is True
    assert mock_log_metrics.call_args.kwargs["profile"] == "risk_daily"


@pytest.mark.asyncio
async def test_engine_generate_report_flow_force_ignores_last_report_since(engine):
    report = MagicMock(date="2026-03-13", investmentTrends=[])
    engine._report_profile = "risk_daily"
    engine._report_repository = MagicMock()
    engine._report_repository.get_latest_report_run = AsyncMock(
        return_value={"updated_at": datetime(2026, 3, 13, 6, 0, tzinfo=UTC)}
    )
    engine._report_orchestrator = MagicMock()
    engine._report_orchestrator.generate_event_centric_report = AsyncMock(
        return_value=report
    )
    engine._report_orchestrator.last_report_metrics = {
        "profile": "risk_daily",
        "context_event_count": 2,
        "context_theme_count": 1,
        "cluster_count": 1,
        "report_generated": True,
        "investment_trend_count": 0,
        "guard_pre_tokens": 100,
        "guard_post_tokens": 80,
        "trimmed_sections": [],
        "budget_truncation_rate": 0.0,
        "final_hard_cap_hit": False,
    }
    engine._report_orchestrator.last_report_guard_stats = {
        "pre_guard_tokens": 100,
        "post_guard_tokens": 80,
        "trimmed_sections": [],
    }
    engine.notifier.deliver_all = AsyncMock()

    with patch("src.engine.log_stage_metrics"):
        result = await engine.generate_and_send_report(force=True)

    assert result is report
    engine._report_repository.get_latest_report_run.assert_not_called()
    report_call = engine._report_orchestrator.generate_event_centric_report.call_args
    assert report_call.kwargs["since"] is None
    assert report_call.kwargs["profile"] == "risk_daily"
    assert isinstance(report_call.kwargs["report_date"], date)


@pytest.mark.asyncio
async def test_engine_generate_report_flow_skips_when_no_event_changes(engine):
    engine._report_profile = "macro_daily"
    engine._report_repository = MagicMock()
    engine._report_repository.get_latest_report_run = AsyncMock(return_value=None)
    engine._report_orchestrator = MagicMock()
    engine._report_orchestrator.generate_event_centric_report = AsyncMock(
        return_value=None
    )
    engine._report_orchestrator.last_report_metrics = {
        "profile": "macro_daily",
        "context_event_count": 0,
        "context_theme_count": 0,
        "cluster_count": 0,
        "report_generated": False,
        "investment_trend_count": 0,
        "guard_pre_tokens": 0,
        "guard_post_tokens": 0,
        "trimmed_sections": [],
        "budget_truncation_rate": 0.0,
        "final_hard_cap_hit": False,
    }
    engine._report_orchestrator.last_report_guard_stats = {}
    engine.notifier.deliver_all = AsyncMock()

    with patch("src.engine.log_stage_metrics") as mock_log_metrics:
        result = await engine.generate_and_send_report()

    assert result is None
    engine._report_orchestrator.generate_event_centric_report.assert_called_once()
    report_call = engine._report_orchestrator.generate_event_centric_report.call_args
    assert report_call.kwargs["statuses"] == REPORT_EVENT_STATUSES
    assert report_call.kwargs["since"] is None
    assert report_call.kwargs["profile"] == "macro_daily"
    assert isinstance(report_call.kwargs["report_date"], date)
    engine.notifier.deliver_all.assert_not_called()
    mock_log_metrics.assert_called_once()
    assert mock_log_metrics.call_args.kwargs["reason"] == "no_event_changes"


@pytest.mark.asyncio
async def test_engine_generate_report_flow_returns_none_when_report_stack_unavailable(
    engine,
):
    engine._report_profile = "macro_daily"
    engine._report_orchestrator = None

    with patch("src.engine.log_stage_metrics") as mock_log_metrics:
        result = await engine.generate_and_send_report()

    assert result is None
    mock_log_metrics.assert_called_once()
    assert mock_log_metrics.call_args.kwargs["reason"] == "report_stack_unavailable"


@pytest.mark.asyncio
async def test_bootstrap_runtime_passes_state_to_ingestion_configuration(engine):
    runtime_state = EventIntelligenceRuntimeState(enabled=True, started=True)
    engine.prediction_repository.connect = AsyncMock()
    engine.event_intelligence.start = AsyncMock(return_value=runtime_state)
    engine._configure_event_intelligence_ingestion = MagicMock()
    engine._configure_event_intelligence_reporting = MagicMock()

    await engine.bootstrap_runtime()

    engine.prediction_repository.connect.assert_called_once()
    engine.event_intelligence.start.assert_called_once()
    engine._configure_event_intelligence_ingestion.assert_called_once_with(
        runtime_state
    )
    engine._configure_event_intelligence_reporting.assert_called_once_with(
        runtime_state
    )
    assert engine._runtime_ready is True


@pytest.mark.asyncio
async def test_configure_event_intelligence_ingestion_clears_side_path_when_runtime_not_started(
    engine,
):
    engine.collector.configure_event_intelligence = MagicMock()

    engine._configure_event_intelligence_ingestion(
        EventIntelligenceRuntimeState(enabled=True, started=False)
    )

    engine.collector.configure_event_intelligence.assert_called_once_with()


@pytest.mark.asyncio
async def test_configure_event_intelligence_reporting_clears_side_path_when_runtime_not_started(
    engine,
):
    engine._report_repository = object()

    engine._configure_event_intelligence_reporting(
        EventIntelligenceRuntimeState(enabled=True, started=False)
    )

    assert engine._report_repository is None
    assert engine._report_orchestrator is None


@pytest.mark.asyncio
async def test_engine_configures_report_stack_from_runtime_stores(engine):
    fake_modules = {
        "src.services.article_repository": ModuleType("src.services.article_repository"),
        "src.services.event_repository": ModuleType("src.services.event_repository"),
        "src.services.brief_repository": ModuleType("src.services.brief_repository"),
        "src.services.report_repository": ModuleType("src.services.report_repository"),
        "src.services.event_enrichment": ModuleType("src.services.event_enrichment"),
        "src.services.event_query_service": ModuleType("src.services.event_query_service"),
        "src.services.event_ranker": ModuleType("src.services.event_ranker"),
        "src.services.evidence_selector": ModuleType("src.services.evidence_selector"),
        "src.services.report_context_builder": ModuleType("src.services.report_context_builder"),
        "src.services.report_orchestrator": ModuleType("src.services.report_orchestrator"),
        "src.services.report_run_tracker": ModuleType("src.services.report_run_tracker"),
        "src.services.event_summarizer": ModuleType("src.services.event_summarizer"),
        "src.services.theme_summarizer": ModuleType("src.services.theme_summarizer"),
    }

    class ArticleRepository:
        def __init__(self, pool):
            self.pool = pool

    class EventRepository:
        def __init__(self, pool):
            self.pool = pool

    class BriefRepository:
        def __init__(self, pool):
            self.pool = pool

    class ReportRepository:
        def __init__(self, pool):
            self.pool = pool

    class EventEnrichmentService:
        def __init__(self, event_repository, article_repository, **kwargs):
            self.event_repository = event_repository
            self.article_repository = article_repository

    class EventQueryService:
        def __init__(self, event_repository, article_repository, event_enrichment):
            self.event_repository = event_repository
            self.article_repository = article_repository
            self.event_enrichment = event_enrichment

    class EventRanker:
        def __init__(self, event_repository, article_repository, event_query_service, **kwargs):
            self.event_repository = event_repository
            self.article_repository = article_repository
            self.event_query_service = event_query_service

    class EvidenceSelector:
        def __init__(self, article_repository, event_query_service, event_ranker, **kwargs):
            self.article_repository = article_repository
            self.event_query_service = event_query_service
            self.event_ranker = event_ranker

    class EventSummarizer:
        def __init__(self, brief_repository, event_query_service, evidence_selector, **kwargs):
            self.brief_repository = brief_repository
            self.event_query_service = event_query_service
            self.evidence_selector = evidence_selector

    class ThemeSummarizer:
        def __init__(self, brief_repository, event_summarizer):
            self.brief_repository = brief_repository
            self.event_summarizer = event_summarizer

    class ReportContextBuilder:
        def __init__(self, event_summarizer, theme_summarizer):
            self.event_summarizer = event_summarizer
            self.theme_summarizer = theme_summarizer

    class ReportRunTracker:
        def __init__(self, report_repository):
            self.report_repository = report_repository

    class ReportOrchestrator:
        def __init__(self, ai_service, report_context_builder, report_run_tracker=None):
            self.ai_service = ai_service
            self.report_context_builder = report_context_builder
            self.report_run_tracker = report_run_tracker

    fake_modules["src.services.article_repository"].ArticleRepository = ArticleRepository
    fake_modules["src.services.event_repository"].EventRepository = EventRepository
    fake_modules["src.services.brief_repository"].BriefRepository = BriefRepository
    fake_modules["src.services.report_repository"].ReportRepository = ReportRepository
    fake_modules["src.services.event_enrichment"].EventEnrichmentService = EventEnrichmentService
    fake_modules["src.services.event_query_service"].EventQueryService = EventQueryService
    fake_modules["src.services.event_ranker"].EventRanker = EventRanker
    fake_modules["src.services.evidence_selector"].EvidenceSelector = EvidenceSelector
    fake_modules["src.services.event_summarizer"].EventSummarizer = EventSummarizer
    fake_modules["src.services.theme_summarizer"].ThemeSummarizer = ThemeSummarizer
    fake_modules["src.services.report_context_builder"].ReportContextBuilder = ReportContextBuilder
    fake_modules["src.services.report_run_tracker"].ReportRunTracker = ReportRunTracker
    fake_modules["src.services.report_orchestrator"].ReportOrchestrator = ReportOrchestrator

    runtime_state = EventIntelligenceRuntimeState(
        enabled=True,
        started=True,
        config=EventIntelligenceRuntimeConfig(
            postgres_dsn="postgresql://localhost/deepcurrents",
            qdrant_url="http://localhost:6333",
            qdrant_api_key="",
            redis_url="redis://localhost:6379/0",
            embedding_model="bge-m3",
            reranker_model="bge-reranker-v2-m3",
            report_profile="risk_daily",
        ),
        stores={
            "postgres": SimpleNamespace(pool=object()),
        },
    )

    original_modules = {name: sys.modules.get(name) for name in fake_modules}
    try:
        sys.modules.update(fake_modules)
        engine._configure_event_intelligence_reporting(runtime_state)
    finally:
        for name, module in original_modules.items():
            if module is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = module

    assert isinstance(engine._report_repository, ReportRepository)
    assert isinstance(engine._report_run_tracker, ReportRunTracker)
    assert isinstance(engine._report_context_builder, ReportContextBuilder)
    assert isinstance(engine._report_orchestrator, ReportOrchestrator)
    assert engine._report_profile == "risk_daily"


@pytest.mark.asyncio
async def test_engine_collect_data_does_not_fallback_when_runtime_unavailable(engine):
    engine.collector.collect_all = AsyncMock(
        return_value={
            "sources_total": 2,
            "sources_skipped": 2,
            "sources_failed": 0,
            "skipped": 2,
            "errors": 0,
            "articles_seen": 0,
            "articles_inserted": 0,
        }
    )

    with patch("src.engine.log_stage_metrics") as mock_log_metrics:
        await engine.collect_data()

    mock_log_metrics.assert_called_once()
    assert mock_log_metrics.call_args.kwargs["event_intelligence_enabled"] is False
    assert mock_log_metrics.call_args.args[2]["sources_skipped"] == 2
