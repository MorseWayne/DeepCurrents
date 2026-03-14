import asyncio
from datetime import UTC, date, datetime, time
from typing import TYPE_CHECKING, Any, cast
from .config.settings import CONFIG
from .services.collector import RSSCollector
from .services.ai_service import AIService
from .services.translator import translate_event_briefs
from .services.prediction_repository import PredictionRepository
from .services.scorer import PredictionScorer
from .services.notifier import Notifier
from .services.event_intelligence_bootstrap import (
    EventIntelligenceBootstrap,
    EventIntelligenceRuntimeState,
)
from .services.metrics import build_report_metrics, default_ingestion_metrics, log_stage_metrics
from .utils.logger import get_logger

logger = get_logger("engine")

if TYPE_CHECKING:
    from .services.article_feature_extractor import VectorStoreLike
    from .services.collector import EventCandidateExtractorLike

REPORT_EVENT_STATUSES = (
    "new",
    "active",
    "updated",
    "escalating",
    "stabilizing",
    "resolved",
)


class DeepCurrentsEngine:
    def __init__(self):
        self.prediction_repository = PredictionRepository()
        self.collector = RSSCollector()
        self.ai = AIService(self.prediction_repository)
        self.scorer = PredictionScorer(self.prediction_repository)
        self.notifier = Notifier()
        self.event_intelligence = EventIntelligenceBootstrap(CONFIG)
        self._report_repository: Any = None
        self._report_run_tracker: Any = None
        self._report_context_builder: Any = None
        self._report_orchestrator: Any = None
        self._event_ranker: Any = None
        self._event_summarizer: Any = None
        self._report_profile = CONFIG.event_intelligence_report_profile
        self._runtime_ready = False

    async def bootstrap_runtime(self):
        if self._runtime_ready:
            return

        await self.prediction_repository.connect()
        runtime_state = await self.event_intelligence.start()
        self._configure_event_intelligence_ingestion(runtime_state)
        self._configure_event_intelligence_reporting(runtime_state)
        self._runtime_ready = True

    def _configure_event_intelligence_ingestion(
        self, runtime_state: EventIntelligenceRuntimeState
    ) -> None:
        if runtime_state.started is not True:
            self.collector.configure_event_intelligence()
            return

        try:
            config = runtime_state.config
            stores = runtime_state.stores or {}
            postgres_store = stores.get("postgres")
            vector_store = stores.get("vector_store")
            postgres_pool = getattr(postgres_store, "pool", None)

            if config is None or postgres_pool is None or vector_store is None:
                logger.warning(
                    "Event Intelligence ingestion wiring skipped: runtime stores unavailable"
                )
                self.collector.configure_event_intelligence()
                return

            from .services.article_feature_extractor import ArticleFeatureExtractor
            from .services.event_enrichment import EventEnrichmentService
            from .services.article_normalizer import ArticleNormalizer
            from .services.article_repository import ArticleRepository
            from .services.event_builder import EventBuilder
            from .services.event_repository import EventRepository
            from .services.semantic_deduper import SemanticDeduper

            article_repository = ArticleRepository(postgres_pool)
            article_feature_extractor = ArticleFeatureExtractor(
                article_repository,
                cast("VectorStoreLike", vector_store),
                embedding_model=config.embedding_model,
            )
            semantic_deduper = SemanticDeduper(
                article_repository,
                cast("VectorStoreLike", vector_store),
            )
            event_repository = EventRepository(postgres_pool)
            cache_store = stores.get("cache")
            event_enrichment = EventEnrichmentService(
                event_repository,
                article_repository,
                ai_service=self.ai,
                cache=cache_store,
            )
            event_builder = EventBuilder(
                event_repository,
                article_repository,
                cast("VectorStoreLike", vector_store),
            )
            self.collector.configure_event_intelligence(
                article_normalizer=ArticleNormalizer(),
                article_repository=article_repository,
                article_feature_extractor=article_feature_extractor,
                semantic_deduper=semantic_deduper,
                event_candidate_extractor=cast(
                    "EventCandidateExtractorLike", event_builder
                ),
                event_enrichment=event_enrichment,
            )
        except Exception as exc:
            self.collector.configure_event_intelligence()
            logger.error(f"Event Intelligence ingestion wiring failed: {exc}")

    def _configure_event_intelligence_reporting(
        self, runtime_state: EventIntelligenceRuntimeState
    ) -> None:
        if runtime_state.started is not True:
            self._clear_event_intelligence_reporting()
            return

        try:
            config = runtime_state.config
            stores = runtime_state.stores or {}
            postgres_store = stores.get("postgres")
            postgres_pool = getattr(postgres_store, "pool", None)

            if config is None or postgres_pool is None:
                logger.warning(
                    "Event Intelligence report wiring skipped: runtime stores unavailable"
                )
                self._clear_event_intelligence_reporting()
                return

            from .services.article_repository import ArticleRepository
            from .services.brief_repository import BriefRepository
            from .services.event_enrichment import EventEnrichmentService
            from .services.event_query_service import EventQueryService
            from .services.event_ranker import EventRanker
            from .services.event_repository import EventRepository
            from .services.evidence_selector import EvidenceSelector
            from .services.report_context_builder import ReportContextBuilder
            from .services.report_orchestrator import ReportOrchestrator
            from .services.report_repository import ReportRepository
            from .services.report_run_tracker import ReportRunTracker
            from .services.event_summarizer import EventSummarizer
            from .services.theme_summarizer import ThemeSummarizer

            article_repository = ArticleRepository(postgres_pool)
            event_repository = EventRepository(postgres_pool)
            brief_repository = BriefRepository(postgres_pool)
            report_repository = ReportRepository(postgres_pool)
            cache_store = stores.get("cache")
            event_enrichment = EventEnrichmentService(
                event_repository,
                article_repository,
                ai_service=self.ai,
                cache=cache_store,
            )
            event_query_service = EventQueryService(
                event_repository,
                article_repository,
                event_enrichment,
            )
            event_ranker = EventRanker(
                event_repository,
                article_repository,
                event_query_service,
            )
            evidence_selector = EvidenceSelector(
                article_repository,
                event_query_service,
                event_ranker,
            )
            event_summarizer = EventSummarizer(
                brief_repository,
                event_query_service,
                evidence_selector,
                ai_service=self.ai,
            )
            theme_summarizer = ThemeSummarizer(
                brief_repository,
                event_summarizer,
            )
            report_context_builder = ReportContextBuilder(
                event_summarizer,
                theme_summarizer,
            )
            report_run_tracker = ReportRunTracker(report_repository)
            report_orchestrator = ReportOrchestrator(
                self.ai,
                report_context_builder,
                report_run_tracker=report_run_tracker,
            )

            self._report_repository = report_repository
            self._report_run_tracker = report_run_tracker
            self._report_context_builder = report_context_builder
            self._report_orchestrator = report_orchestrator
            self._event_ranker = event_ranker
            self._event_summarizer = event_summarizer
            self._report_profile = config.report_profile or self._report_profile
        except Exception as exc:
            self._clear_event_intelligence_reporting()
            logger.error(f"Event Intelligence report wiring failed: {exc}")

    def _clear_event_intelligence_reporting(self) -> None:
        self._report_repository = None
        self._report_run_tracker = None
        self._report_context_builder = None
        self._report_orchestrator = None
        self._event_ranker = None
        self._event_summarizer = None
        self._report_profile = CONFIG.event_intelligence_report_profile

    async def start(self):
        await self.bootstrap_runtime()
        logger.info("DeepCurrents 引擎启动 (Python v2.2)")

        # 首次运行立即执行采集和评分
        await self.collect_data()
        await self.scorer.run_scoring_task()

    async def collect_data(self):
        """执行数据采集任务"""
        try:
            stats = await self.collector.collect_all()
            log_stage_metrics(
                logger,
                "ingestion",
                stats,
                service="DeepCurrentsEngine.collect_data",
                event_intelligence_enabled=self.collector._event_intelligence_enabled(),
            )
            logger.info(f"采集完成: {stats}")
        except Exception as e:
            log_stage_metrics(
                logger,
                "ingestion",
                default_ingestion_metrics(),
                service="DeepCurrentsEngine.collect_data",
                event_intelligence_enabled=self.collector._event_intelligence_enabled(),
                error=str(e),
            )
            logger.error(f"采集任务失败: {e}")

    async def generate_and_send_report(
        self,
        skip_push: bool = False,
        skip_mark: bool = False,
        *,
        force: bool = False,
    ):
        """生成并发送研报"""
        cluster_count = 0
        profile = self._report_profile
        try:
            if self._report_orchestrator is None:
                log_stage_metrics(
                    logger,
                    "report",
                    build_report_metrics(
                        raw_news_input_count=0,
                        cluster_count=0,
                        report_generated=False,
                        investment_trend_count=0,
                    ),
                    service="DeepCurrentsEngine.generate_and_send_report",
                    reason="report_stack_unavailable",
                    profile=profile,
                    skip_push=skip_push,
                    skip_mark=skip_mark,
                )
                logger.warning("Event-centric report stack 未就绪，跳过研报生成。")
                return None

            since = None if force else await self._resolve_last_report_since(profile)
            report = await self._report_orchestrator.generate_event_centric_report(
                statuses=REPORT_EVENT_STATUSES,
                since=since,
                profile=profile,
                report_date=datetime.now(UTC).date(),
            )
            report_metrics = (
                dict(self._report_orchestrator.last_report_metrics)
                if self._report_orchestrator.last_report_metrics
                else build_report_metrics(
                    raw_news_input_count=0,
                    cluster_count=0,
                    report_generated=report is not None,
                    investment_trend_count=len(
                        getattr(report, "investmentTrends", []) or []
                    ),
                    guard_stats=self.ai.last_report_guard_stats,
                )
            )
            report_metrics["profile"] = profile
            cluster_count = max(
                self._safe_int(report_metrics.get("context_event_count")),
                self._safe_int(report_metrics.get("cluster_count")),
            )

            if report is None:
                report_metrics["report_generated"] = False
                log_stage_metrics(
                    logger,
                    "report",
                    report_metrics,
                    service="DeepCurrentsEngine.generate_and_send_report",
                    reason="no_event_changes",
                    profile=profile,
                    since=since.isoformat() if since else "",
                    skip_push=skip_push,
                    skip_mark=skip_mark,
                    force=force,
                )
                logger.info("没有新的事件变化需要报告。")
                return None

            logger.info(f"成功生成研报: {report.date}")
            report_metrics["cluster_count"] = cluster_count
            report_metrics["report_generated"] = report is not None
            report_metrics["investment_trend_count"] = len(
                getattr(report, "investmentTrends", []) or []
            )
            log_stage_metrics(
                logger,
                "report",
                report_metrics,
                service="DeepCurrentsEngine.generate_and_send_report",
                profile=profile,
                since=since.isoformat() if since else "",
                skip_push=skip_push,
                skip_mark=skip_mark,
                force=force,
            )

            if not skip_push:
                await self.notifier.deliver_all(report, 0, cluster_count)
                logger.info("✅ 研报投递完成。")
            else:
                logger.info("已跳过通知推送。")

            return report
        except Exception as e:
            guard_stats = (
                dict(self._report_orchestrator.last_report_guard_stats)
                if self._report_orchestrator is not None
                else dict(self.ai.last_report_guard_stats)
            )
            log_stage_metrics(
                logger,
                "report",
                build_report_metrics(
                    raw_news_input_count=0,
                    cluster_count=cluster_count,
                    report_generated=False,
                    investment_trend_count=0,
                    guard_stats=guard_stats,
                ),
                service="DeepCurrentsEngine.generate_and_send_report",
                profile=profile,
                skip_push=skip_push,
                skip_mark=skip_mark,
                error=str(e),
            )
            logger.error(f"研报生成任务失败: {e}")
            return None

    async def send_core_events(
        self,
        *,
        skip_push: bool = False,
        force: bool = False,
        translate: bool = True,
        event_limit: int = 12,
        evidence_limit: int = 4,
    ):
        """独立排序核心事件并推送到飞书（不生成研报）"""
        profile = self._report_profile
        try:
            if self._event_summarizer is None:
                logger.warning("Event Intelligence 未就绪，跳过事件推送。")
                return None

            since = None if force else await self._resolve_last_report_since(profile)
            event_briefs = await self._event_summarizer.summarize_ranked_events(
                statuses=REPORT_EVENT_STATUSES,
                since=since,
                profile=profile,
                limit=event_limit,
                evidence_limit=evidence_limit,
            )

            if not event_briefs:
                logger.info("没有新的核心事件需要推送。")
                return []

            logger.info(f"已整理 {len(event_briefs)} 个核心事件")

            if translate:
                event_briefs = await translate_event_briefs(event_briefs)

            if not skip_push:
                report_date = datetime.now(UTC).strftime("%Y-%m-%d")
                await self.notifier.deliver_events(
                    event_briefs,
                    report_date=report_date,
                )
                logger.info("✅ 核心事件速报推送完成。")
            else:
                logger.info("已跳过事件推送。")

            return event_briefs
        except Exception as e:
            logger.error(f"核心事件推送失败: {e}")
            return None

    async def _resolve_last_report_since(self, profile: str) -> datetime | None:
        if self._report_repository is None:
            return None
        latest_run = await self._report_repository.get_latest_report_run(profile)
        if not latest_run:
            return None

        updated_at = self._optional_datetime(latest_run.get("updated_at"))
        if updated_at is not None:
            return updated_at

        created_at = self._optional_datetime(latest_run.get("created_at"))
        if created_at is not None:
            return created_at

        report_date = latest_run.get("report_date")
        if isinstance(report_date, datetime):
            return self._optional_datetime(report_date)
        if isinstance(report_date, date):
            return datetime.combine(report_date, time.min, tzinfo=UTC)
        return None

    async def stop(self):
        if self._runtime_ready:
            await self.event_intelligence.stop()
        await self.prediction_repository.close()
        self._clear_event_intelligence_reporting()
        self._runtime_ready = False
        logger.info("引擎已关闭")

    @staticmethod
    def _optional_datetime(value: Any) -> datetime | None:
        if not isinstance(value, datetime):
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value

    @staticmethod
    def _safe_int(value: Any) -> int:
        try:
            return int(value)
        except (TypeError, ValueError):
            return 0
