import sys
from datetime import UTC, date, datetime
from types import ModuleType, SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio

from src.engine import DeepCurrentsEngine, REPORT_EVENT_STATUSES
from src.services.event_intelligence_bootstrap import (
    EventIntelligenceRuntimeConfig,
    EventIntelligenceRuntimeState,
)


@pytest_asyncio.fixture
async def engine():
    with patch("src.services.db_service.DBService.connect", new_callable=AsyncMock):
        with patch("src.services.db_service.DBService.close", new_callable=AsyncMock):
            runtime_engine = DeepCurrentsEngine()
            yield runtime_engine


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
    engine.db.connect = AsyncMock()
    engine.event_intelligence.start = AsyncMock(
        return_value=EventIntelligenceRuntimeState(enabled=False)
    )
    engine._configure_event_intelligence_ingestion = MagicMock()
    engine._configure_event_intelligence_reporting = MagicMock()
    engine.collect_data = AsyncMock()
    engine.scorer.run_scoring_task = AsyncMock()

    await engine.start()

    engine.db.connect.assert_called_once()
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
async def test_engine_stop_stops_bootstrap(engine):
    engine._runtime_ready = True
    engine.event_intelligence.stop = AsyncMock()
    engine.db.close = AsyncMock()

    await engine.stop()

    engine.event_intelligence.stop.assert_called_once()
    engine.db.close.assert_called_once()


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
    engine.ai.generate_daily_report = AsyncMock()
    engine.db.mark_as_reported = AsyncMock()

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
    engine.ai.generate_daily_report.assert_not_called()
    engine.db.mark_as_reported.assert_not_called()
    engine.notifier.deliver_all.assert_called_once_with(report, 0, 2)
    mock_log_metrics.assert_called_once()
    assert mock_log_metrics.call_args.args[1] == "report"
    assert mock_log_metrics.call_args.args[2]["report_generated"] is True
    assert mock_log_metrics.call_args.kwargs["profile"] == "risk_daily"


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
    engine.ai.generate_daily_report = AsyncMock()

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
    engine.ai.generate_daily_report.assert_not_called()
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
    engine.db.connect = AsyncMock()
    engine.event_intelligence.start = AsyncMock(return_value=runtime_state)
    engine._configure_event_intelligence_ingestion = MagicMock()
    engine._configure_event_intelligence_reporting = MagicMock()

    await engine.bootstrap_runtime()

    engine.db.connect.assert_called_once()
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
    engine._report_run_tracker = object()
    engine._report_context_builder = object()
    engine._report_orchestrator = object()
    engine._report_profile = "risk_daily"

    engine._configure_event_intelligence_reporting(
        EventIntelligenceRuntimeState(enabled=True, started=False)
    )

    assert engine._report_repository is None
    assert engine._report_run_tracker is None
    assert engine._report_context_builder is None
    assert engine._report_orchestrator is None
    assert engine._report_profile == "macro_daily"


@pytest.mark.asyncio
async def test_configure_event_intelligence_ingestion_wires_collector_when_runtime_is_ready(
    engine,
):
    engine.collector.configure_event_intelligence = MagicMock()
    postgres_store = SimpleNamespace(pool=object())
    vector_store = object()
    runtime_state = EventIntelligenceRuntimeState(
        enabled=True,
        started=True,
        config=EventIntelligenceRuntimeConfig(
            postgres_dsn="postgresql://localhost:5432/deepcurrents",
            qdrant_url="http://localhost:6333",
            qdrant_api_key="",
            redis_url="redis://localhost:6379/0",
            embedding_model="bge-m3",
            reranker_model="bge-reranker-v2-m3",
            report_profile="default",
        ),
        stores={
            "postgres": postgres_store,
            "vector_store": vector_store,
        },
    )

    fake_normalizer_module = ModuleType("src.services.article_normalizer")
    fake_repository_module = ModuleType("src.services.article_repository")
    fake_extractor_module = ModuleType("src.services.article_feature_extractor")
    fake_deduper_module = ModuleType("src.services.semantic_deduper")
    fake_event_repository_module = ModuleType("src.services.event_repository")
    fake_event_builder_module = ModuleType("src.services.event_builder")
    fake_event_enrichment_module = ModuleType("src.services.event_enrichment")

    normalizer_instance = object()
    repository_instance = object()
    extractor_instance = object()
    deduper_instance = object()
    event_repository_instance = object()
    event_builder_instance = object()
    event_enrichment_instance = object()

    setattr(
        fake_normalizer_module,
        "ArticleNormalizer",
        MagicMock(return_value=normalizer_instance),
    )
    setattr(
        fake_repository_module,
        "ArticleRepository",
        MagicMock(return_value=repository_instance),
    )
    setattr(
        fake_extractor_module,
        "ArticleFeatureExtractor",
        MagicMock(return_value=extractor_instance),
    )
    setattr(
        fake_deduper_module,
        "SemanticDeduper",
        MagicMock(return_value=deduper_instance),
    )
    setattr(
        fake_event_repository_module,
        "EventRepository",
        MagicMock(return_value=event_repository_instance),
    )
    setattr(
        fake_event_builder_module,
        "EventBuilder",
        MagicMock(return_value=event_builder_instance),
    )
    setattr(
        fake_event_enrichment_module,
        "EventEnrichmentService",
        MagicMock(return_value=event_enrichment_instance),
    )

    with patch.dict(
        sys.modules,
        {
            "src.services.article_normalizer": fake_normalizer_module,
            "src.services.article_repository": fake_repository_module,
            "src.services.article_feature_extractor": fake_extractor_module,
            "src.services.semantic_deduper": fake_deduper_module,
            "src.services.event_repository": fake_event_repository_module,
            "src.services.event_builder": fake_event_builder_module,
            "src.services.event_enrichment": fake_event_enrichment_module,
        },
    ):
        engine._configure_event_intelligence_ingestion(runtime_state)

    fake_repository_module.ArticleRepository.assert_called_once_with(
        postgres_store.pool
    )
    fake_extractor_module.ArticleFeatureExtractor.assert_called_once_with(
        repository_instance,
        vector_store,
        embedding_model="bge-m3",
    )
    fake_deduper_module.SemanticDeduper.assert_called_once_with(
        repository_instance,
        vector_store,
    )
    fake_event_repository_module.EventRepository.assert_called_once_with(
        postgres_store.pool
    )
    fake_event_enrichment_module.EventEnrichmentService.assert_called_once_with(
        event_repository_instance,
        repository_instance,
    )
    fake_event_builder_module.EventBuilder.assert_called_once_with(
        event_repository_instance,
        repository_instance,
        vector_store,
    )
    engine.collector.configure_event_intelligence.assert_called_once_with(
        article_normalizer=normalizer_instance,
        article_repository=repository_instance,
        article_feature_extractor=extractor_instance,
        semantic_deduper=deduper_instance,
        event_candidate_extractor=event_builder_instance,
        event_enrichment=event_enrichment_instance,
    )


@pytest.mark.asyncio
async def test_configure_event_intelligence_reporting_wires_report_stack_when_runtime_is_ready(
    engine,
):
    postgres_store = SimpleNamespace(pool=object())
    runtime_state = EventIntelligenceRuntimeState(
        enabled=True,
        started=True,
        config=EventIntelligenceRuntimeConfig(
            postgres_dsn="postgresql://localhost:5432/deepcurrents",
            qdrant_url="http://localhost:6333",
            qdrant_api_key="",
            redis_url="redis://localhost:6379/0",
            embedding_model="bge-m3",
            reranker_model="bge-reranker-v2-m3",
            report_profile="risk_daily",
        ),
        stores={"postgres": postgres_store},
    )

    fake_article_repository_module = ModuleType("src.services.article_repository")
    fake_brief_repository_module = ModuleType("src.services.brief_repository")
    fake_event_repository_module = ModuleType("src.services.event_repository")
    fake_event_enrichment_module = ModuleType("src.services.event_enrichment")
    fake_event_query_module = ModuleType("src.services.event_query_service")
    fake_event_ranker_module = ModuleType("src.services.event_ranker")
    fake_evidence_selector_module = ModuleType("src.services.evidence_selector")
    fake_event_summarizer_module = ModuleType("src.services.event_summarizer")
    fake_theme_summarizer_module = ModuleType("src.services.theme_summarizer")
    fake_report_context_builder_module = ModuleType(
        "src.services.report_context_builder"
    )
    fake_report_repository_module = ModuleType("src.services.report_repository")
    fake_report_run_tracker_module = ModuleType("src.services.report_run_tracker")
    fake_report_orchestrator_module = ModuleType("src.services.report_orchestrator")

    article_repository_instance = object()
    brief_repository_instance = object()
    event_repository_instance = object()
    event_enrichment_instance = object()
    event_query_instance = object()
    event_ranker_instance = object()
    evidence_selector_instance = object()
    event_summarizer_instance = object()
    theme_summarizer_instance = object()
    report_context_builder_instance = object()
    report_repository_instance = object()
    report_run_tracker_instance = object()
    report_orchestrator_instance = object()

    setattr(
        fake_article_repository_module,
        "ArticleRepository",
        MagicMock(return_value=article_repository_instance),
    )
    setattr(
        fake_brief_repository_module,
        "BriefRepository",
        MagicMock(return_value=brief_repository_instance),
    )
    setattr(
        fake_event_repository_module,
        "EventRepository",
        MagicMock(return_value=event_repository_instance),
    )
    setattr(
        fake_event_enrichment_module,
        "EventEnrichmentService",
        MagicMock(return_value=event_enrichment_instance),
    )
    setattr(
        fake_event_query_module,
        "EventQueryService",
        MagicMock(return_value=event_query_instance),
    )
    setattr(
        fake_event_ranker_module,
        "EventRanker",
        MagicMock(return_value=event_ranker_instance),
    )
    setattr(
        fake_evidence_selector_module,
        "EvidenceSelector",
        MagicMock(return_value=evidence_selector_instance),
    )
    setattr(
        fake_event_summarizer_module,
        "EventSummarizer",
        MagicMock(return_value=event_summarizer_instance),
    )
    setattr(
        fake_theme_summarizer_module,
        "ThemeSummarizer",
        MagicMock(return_value=theme_summarizer_instance),
    )
    setattr(
        fake_report_context_builder_module,
        "ReportContextBuilder",
        MagicMock(return_value=report_context_builder_instance),
    )
    setattr(
        fake_report_repository_module,
        "ReportRepository",
        MagicMock(return_value=report_repository_instance),
    )
    setattr(
        fake_report_run_tracker_module,
        "ReportRunTracker",
        MagicMock(return_value=report_run_tracker_instance),
    )
    setattr(
        fake_report_orchestrator_module,
        "ReportOrchestrator",
        MagicMock(return_value=report_orchestrator_instance),
    )

    with patch.dict(
        sys.modules,
        {
            "src.services.article_repository": fake_article_repository_module,
            "src.services.brief_repository": fake_brief_repository_module,
            "src.services.event_repository": fake_event_repository_module,
            "src.services.event_enrichment": fake_event_enrichment_module,
            "src.services.event_query_service": fake_event_query_module,
            "src.services.event_ranker": fake_event_ranker_module,
            "src.services.evidence_selector": fake_evidence_selector_module,
            "src.services.event_summarizer": fake_event_summarizer_module,
            "src.services.theme_summarizer": fake_theme_summarizer_module,
            "src.services.report_context_builder": fake_report_context_builder_module,
            "src.services.report_repository": fake_report_repository_module,
            "src.services.report_run_tracker": fake_report_run_tracker_module,
            "src.services.report_orchestrator": fake_report_orchestrator_module,
        },
    ):
        engine._configure_event_intelligence_reporting(runtime_state)

    fake_article_repository_module.ArticleRepository.assert_called_once_with(
        postgres_store.pool
    )
    fake_brief_repository_module.BriefRepository.assert_called_once_with(
        postgres_store.pool
    )
    fake_event_repository_module.EventRepository.assert_called_once_with(
        postgres_store.pool
    )
    fake_event_enrichment_module.EventEnrichmentService.assert_called_once_with(
        event_repository_instance,
        article_repository_instance,
    )
    fake_event_query_module.EventQueryService.assert_called_once_with(
        event_repository_instance,
        article_repository_instance,
        event_enrichment_instance,
    )
    fake_event_ranker_module.EventRanker.assert_called_once_with(
        event_repository_instance,
        article_repository_instance,
        event_query_instance,
    )
    fake_evidence_selector_module.EvidenceSelector.assert_called_once_with(
        article_repository_instance,
        event_query_instance,
        event_ranker_instance,
    )
    fake_event_summarizer_module.EventSummarizer.assert_called_once_with(
        brief_repository_instance,
        event_query_instance,
        evidence_selector_instance,
    )
    fake_theme_summarizer_module.ThemeSummarizer.assert_called_once_with(
        brief_repository_instance,
        event_summarizer_instance,
    )
    fake_report_context_builder_module.ReportContextBuilder.assert_called_once_with(
        event_summarizer_instance,
        theme_summarizer_instance,
    )
    fake_report_repository_module.ReportRepository.assert_called_once_with(
        postgres_store.pool
    )
    fake_report_run_tracker_module.ReportRunTracker.assert_called_once_with(
        report_repository_instance
    )
    fake_report_orchestrator_module.ReportOrchestrator.assert_called_once_with(
        engine.ai,
        report_context_builder_instance,
        report_run_tracker=report_run_tracker_instance,
    )
    assert engine._report_repository is report_repository_instance
    assert engine._report_run_tracker is report_run_tracker_instance
    assert engine._report_context_builder is report_context_builder_instance
    assert engine._report_orchestrator is report_orchestrator_instance
    assert engine._report_profile == "risk_daily"
