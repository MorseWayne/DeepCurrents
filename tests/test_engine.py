import sys
from types import ModuleType, SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio

from src.engine import DeepCurrentsEngine
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
    engine.collector.collect_all = AsyncMock(return_value={"new_items": 5, "errors": 0})

    await engine.collect_data()

    engine.collector.collect_all.assert_called_once()


@pytest.mark.asyncio
async def test_engine_start_bootstraps_runtime(engine):
    engine.db.connect = AsyncMock()
    engine.event_intelligence.start = AsyncMock(
        return_value=EventIntelligenceRuntimeState(enabled=False)
    )
    engine._configure_event_intelligence_ingestion = MagicMock()
    engine.collect_data = AsyncMock()
    engine.scorer.run_scoring_task = AsyncMock()

    await engine.start()

    engine.db.connect.assert_called_once()
    engine.event_intelligence.start.assert_called_once()
    engine._configure_event_intelligence_ingestion.assert_called_once_with(
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
async def test_engine_generate_report_flow(engine):
    engine.db.get_unreported_news = AsyncMock(
        return_value=[
            MagicMock(
                id="1",
                title="Gold up",
                url="u1",
                content="C1",
                category="C",
                tier=1,
                timestamp="2026-03-12T12:00:00",
            )
        ]
    )
    engine.ai.generate_daily_report = AsyncMock(
        return_value=MagicMock(date="2026-03-12")
    )
    engine.db.mark_as_reported = AsyncMock()

    await engine.generate_and_send_report()

    engine.ai.generate_daily_report.assert_called_once()
    engine.db.mark_as_reported.assert_called_once()


@pytest.mark.asyncio
async def test_bootstrap_runtime_passes_state_to_ingestion_configuration(engine):
    runtime_state = EventIntelligenceRuntimeState(enabled=True, started=True)
    engine.db.connect = AsyncMock()
    engine.event_intelligence.start = AsyncMock(return_value=runtime_state)
    engine._configure_event_intelligence_ingestion = MagicMock()

    await engine.bootstrap_runtime()

    engine.db.connect.assert_called_once()
    engine.event_intelligence.start.assert_called_once()
    engine._configure_event_intelligence_ingestion.assert_called_once_with(
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

    normalizer_instance = object()
    repository_instance = object()
    extractor_instance = object()

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

    with patch.dict(
        sys.modules,
        {
            "src.services.article_normalizer": fake_normalizer_module,
            "src.services.article_repository": fake_repository_module,
            "src.services.article_feature_extractor": fake_extractor_module,
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
    engine.collector.configure_event_intelligence.assert_called_once_with(
        article_normalizer=normalizer_instance,
        article_repository=repository_instance,
        article_feature_extractor=extractor_instance,
    )
