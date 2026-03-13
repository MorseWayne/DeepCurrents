import aiohttp
import asyncio
import feedparser
from typing import Any, Dict, Mapping, Optional, Protocol, Sequence, cast
from ..config.settings import CONFIG
from ..config.sources import SOURCES, Source, resolve_source_url
from .circuit_breaker import RSSCircuitBreaker
from .article_models import ArticleRecord
from .metrics import default_ingestion_metrics, safe_ratio
from ..utils.extractor import Extractor
from ..utils.logger import get_logger

logger = get_logger("collector")


class ArticleNormalizerLike(Protocol):
    def normalize(self, raw: Mapping[str, Any]) -> ArticleRecord: ...


class ArticleRepositoryLike(Protocol):
    async def create_article(self, article: Mapping[str, Any]) -> dict[str, Any]: ...

    async def get_article(self, article_id: str) -> dict[str, Any] | None: ...


class ArticleFeatureExtractorLike(Protocol):
    async def extract_and_persist(
        self, article: ArticleRecord | Mapping[str, Any]
    ) -> dict[str, Any]: ...


class SemanticDeduperLike(Protocol):
    async def link_cheap_duplicates(
        self, article: ArticleRecord | Mapping[str, Any]
    ) -> list[dict[str, Any]]: ...

    async def link_semantic_duplicates(
        self,
        article: ArticleRecord | Mapping[str, Any],
        *,
        embedding: Sequence[float] | None,
    ) -> list[dict[str, Any]]: ...


class EventCandidateExtractorLike(Protocol):
    async def extract_and_persist(
        self,
        article: ArticleRecord | Mapping[str, Any],
        *,
        extracted_features: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]: ...


class EventEnrichmentLike(Protocol):
    async def enrich_event(
        self,
        event_id: str,
        *,
        event: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]: ...


class RSSCollector:
    def __init__(self):
        self.breaker = RSSCircuitBreaker(
            max_failures=CONFIG.cb_max_failures, cooldown_ms=CONFIG.cb_cooldown_ms
        )
        self.semaphore = asyncio.Semaphore(CONFIG.rss_concurrency)
        self.retry_statuses = {429, 500, 502, 503, 504}
        self.max_retries = 2
        self.retry_base_delay = 0.8
        self.article_normalizer: ArticleNormalizerLike | None = None
        self.article_repository: ArticleRepositoryLike | None = None
        self.article_feature_extractor: ArticleFeatureExtractorLike | None = None
        self.semantic_deduper: SemanticDeduperLike | None = None
        self.event_candidate_extractor: EventCandidateExtractorLike | None = None
        self.event_enrichment: EventEnrichmentLike | None = None

    def configure_event_intelligence(
        self,
        *,
        article_normalizer: ArticleNormalizerLike | None = None,
        article_repository: ArticleRepositoryLike | None = None,
        article_feature_extractor: ArticleFeatureExtractorLike | None = None,
        semantic_deduper: SemanticDeduperLike | None = None,
        event_candidate_extractor: EventCandidateExtractorLike | None = None,
        event_enrichment: EventEnrichmentLike | None = None,
    ) -> None:
        self.article_normalizer = article_normalizer
        self.article_repository = article_repository
        self.article_feature_extractor = article_feature_extractor
        self.semantic_deduper = semantic_deduper
        self.event_candidate_extractor = event_candidate_extractor
        self.event_enrichment = event_enrichment

    def _event_intelligence_enabled(self) -> bool:
        return (
            self.article_normalizer is not None
            and self.article_repository is not None
            and self.article_feature_extractor is not None
        )

    async def collect_all(self) -> Dict[str, Any]:
        """执行全量抓取任务"""
        logger.info("开始扫描全球动态...")

        # 按 tier 排序
        sorted_sources = sorted(SOURCES, key=lambda s: s.tier)
        if not self._event_intelligence_enabled():
            metrics = default_ingestion_metrics(sources_total=len(sorted_sources))
            metrics["sources_skipped"] = len(sorted_sources)
            metrics["skipped"] = len(sorted_sources)
            logger.warning(
                "Event Intelligence ingestion wiring 未就绪，采集任务按 fail-closed 跳过。"
            )
            return metrics

        timeout = aiohttp.ClientTimeout(total=CONFIG.rss_timeout_ms / 1000)
        connector = aiohttp.TCPConnector(limit=max(CONFIG.rss_concurrency * 2, 20))
        async with aiohttp.ClientSession(
            timeout=timeout, connector=connector
        ) as session:
            tasks = [
                self.fetch_source(source, session=session) for source in sorted_sources
            ]
            results = await asyncio.gather(*tasks)

        metrics = default_ingestion_metrics(sources_total=len(sorted_sources))
        total_new = sum(self._safe_int(r.get("new_count")) for r in results)
        total_errors = sum(1 for r in results if "error" in r)
        total_skipped = sum(1 for r in results if r.get("skipped"))

        metrics["sources_skipped"] = total_skipped
        metrics["sources_failed"] = total_errors
        for result in results:
            self._merge_ingestion_metrics(metrics, result)
        metrics["new_items"] = total_new
        metrics["errors"] = total_errors
        metrics["skipped"] = total_skipped
        metrics["article_to_event_compression_ratio"] = safe_ratio(
            self._safe_int(metrics.get("events_touched")),
            self._safe_int(metrics.get("articles_inserted")),
        )

        logger.info(
            f"[采集完成] 新增 {total_new} | 跳过 {total_skipped} | 错误 {total_errors}"
        )

        return metrics

    async def fetch_source(
        self, source: Source, session: Optional[aiohttp.ClientSession] = None
    ) -> Dict[str, Any]:
        """抓取单个源"""
        if not self._event_intelligence_enabled():
            logger.warning(
                f"[SKIP] T{source.tier} {source.name}: event intelligence ingestion unavailable"
            )
            return {
                "skipped": True,
                "reason": "event_intelligence_unavailable",
                **self._empty_source_metrics(),
            }
        if self.breaker.is_on_cooldown(source.name):
            return {"skipped": True, **self._empty_source_metrics()}

        async with self.semaphore:
            managed_session = session is None
            active_session = session or aiohttp.ClientSession()
            request_timeout = aiohttp.ClientTimeout(total=CONFIG.rss_timeout_ms / 1000)
            source_metrics = self._empty_source_metrics()
            try:
                url = resolve_source_url(source)
                proxy = CONFIG.https_proxy if CONFIG.https_proxy else None
                content = None

                for attempt in range(self.max_retries + 1):
                    try:
                        async with active_session.get(
                            url, timeout=request_timeout, proxy=proxy
                        ) as response:
                            if response.status == 200:
                                content = await response.text()
                                break

                            if (
                                response.status in self.retry_statuses
                                and attempt < self.max_retries
                            ):
                                delay = self.retry_base_delay * (2**attempt)
                                logger.warning(
                                    f"⏳ [RSS] T{source.tier} {source.name} 返回 HTTP {response.status}，"
                                    f"{delay:.1f}s 后重试 ({attempt + 1}/{self.max_retries})"
                                )
                                await asyncio.sleep(delay)
                                continue

                            raise RuntimeError(f"HTTP {response.status}")
                    except (
                        asyncio.TimeoutError,
                        aiohttp.ClientConnectionError,
                        aiohttp.ServerDisconnectedError,
                        aiohttp.ClientOSError,
                    ) as e:
                        if attempt < self.max_retries:
                            delay = self.retry_base_delay * (2**attempt)
                            logger.warning(
                                f"⏳ [RSS] T{source.tier} {source.name} 请求异常: {str(e)}，"
                                f"{delay:.1f}s 后重试 ({attempt + 1}/{self.max_retries})"
                            )
                            await asyncio.sleep(delay)
                            continue
                        raise
                    except aiohttp.ClientError:
                        raise

                if content is None:
                    raise RuntimeError("Empty response content after retries")

                feed = feedparser.parse(content)
                new_count = 0

                for entry in feed.entries:
                    raw_link = entry.get("link")
                    raw_title = entry.get("title")
                    link = raw_link.strip() if isinstance(raw_link, str) else ""
                    title = raw_title.strip() if isinstance(raw_title, str) else ""
                    if not link or not title:
                        continue
                    source_metrics["articles_seen"] += 1

                    # 提取内容
                    raw_summary = entry.get("summary", "") or entry.get(
                        "description", ""
                    )
                    summary = raw_summary if isinstance(raw_summary, str) else ""
                    final_content = summary

                    # 高优源尝试全文提取
                    if source.tier <= 2:
                        extracted = await Extractor.extract(
                            link, session=active_session, proxy=proxy
                        )
                        extracted_content = (
                            extracted.get("content", "") if extracted else ""
                        )
                        if isinstance(extracted_content, str) and len(
                            extracted_content
                        ) > len(final_content):
                            final_content = extracted_content

                    raw_published = entry.get("published") or entry.get("updated")
                    published = (
                        raw_published if isinstance(raw_published, str) else None
                    )

                    if self._event_intelligence_enabled():
                        ingest_result = await self._ingest_event_intelligence_article(
                            link=link,
                            title=title,
                            summary=summary,
                            content=final_content,
                            source=source,
                            published=published,
                        )
                        inserted = bool(ingest_result.get("inserted"))
                        self._merge_ingestion_metrics(source_metrics, ingest_result)
                    else:
                        inserted = False

                    if inserted:
                        new_count += 1

                self.breaker.record_success(source.name)
                if new_count > 0:
                    logger.info(f"[+{new_count}] T{source.tier} {source.name}")

                return {"new_count": new_count, **source_metrics}

            except Exception as e:
                self.breaker.record_failure(source.name)
                err = str(e).strip() or e.__class__.__name__
                logger.error(f"[ERR] T{source.tier} {source.name}: {err}")
                return {"error": err, **source_metrics}
            finally:
                if managed_session:
                    await active_session.close()

    async def _ingest_event_intelligence_article(
        self,
        *,
        link: str,
        title: str,
        summary: str,
        content: str,
        source: Source,
        published: str | None,
    ) -> dict[str, Any]:
        article_normalizer = self.article_normalizer
        article_repository = self.article_repository
        article_feature_extractor = self.article_feature_extractor
        semantic_deduper = self.semantic_deduper
        event_candidate_extractor = self.event_candidate_extractor
        event_enrichment = self.event_enrichment
        metrics = self._empty_source_metrics()
        if not self._event_intelligence_enabled():
            return {"inserted": False, **metrics}

        normalizer = cast(ArticleNormalizerLike, article_normalizer)
        repository = cast(ArticleRepositoryLike, article_repository)
        feature_extractor = cast(ArticleFeatureExtractorLike, article_feature_extractor)
        deduper = cast(SemanticDeduperLike | None, semantic_deduper)

        raw_article = {
            "url": link,
            "title": title,
            "summary": summary,
            "content": content,
            "published": published,
            "source": source.name,
            "sourceType": source.type,
            "tier": source.tier,
            "metadata": {
                "source": source.name,
                "sourceType": source.type,
                "tier": source.tier,
            },
        }

        try:
            article = normalizer.normalize(raw_article)
        except Exception as exc:
            logger.error(f"[EIL] Failed to normalize article {link}: {exc}")
            return {"inserted": False, **metrics}

        created = False
        duplicate_refresh = False
        try:
            await repository.create_article(article.to_article_payload())
            created = True
            metrics["articles_inserted"] += 1
        except Exception as exc:
            existing = await repository.get_article(article.article_id)
            if existing is None:
                logger.error(f"[EIL] Failed to persist article {link}: {exc}")
                return {"inserted": False, **metrics}
            logger.warning(
                f"[EIL] Article already exists for {link}; refreshing features: {exc}"
            )
            duplicate_refresh = True
            metrics["duplicate_refreshes"] += 1

        if deduper is not None:
            try:
                cheap_links = await deduper.link_cheap_duplicates(article)
                metrics["cheap_dedup_links"] += len(cheap_links)
            except Exception as exc:
                logger.error(
                    f"[EIL] Failed to create cheap dedup links for {link}: {exc}"
                )

        extracted_features: dict[str, Any] | None = None
        try:
            extracted_features = await feature_extractor.extract_and_persist(article)
        except Exception as exc:
            logger.error(f"[EIL] Failed to extract features for article {link}: {exc}")
            metrics["feature_failures"] += 1

        if deduper is not None and extracted_features is not None:
            try:
                semantic_links = await deduper.link_semantic_duplicates(
                    article,
                    embedding=extracted_features.get("embedding"),
                )
                metrics["semantic_dedup_links"] += len(semantic_links)
            except Exception as exc:
                logger.error(
                    f"[EIL] Failed to create semantic dedup links for article {link}: {exc}"
                )

        event_extractor = cast(
            EventCandidateExtractorLike | None,
            event_candidate_extractor,
        )
        event_enricher = cast(EventEnrichmentLike | None, event_enrichment)
        if event_extractor is not None:
            try:
                event_result = await event_extractor.extract_and_persist(
                    article,
                    extracted_features=extracted_features,
                )
                event_payload = (
                    event_result.get("event")
                    if isinstance(event_result, Mapping)
                    else None
                )
                event_id = (
                    self._text(event_payload.get("event_id"))
                    if isinstance(event_payload, Mapping)
                    else ""
                )
                if event_id:
                    metrics["events_touched"] += 1
                    if bool(event_result.get("created")):
                        metrics["events_created"] += 1
                    else:
                        metrics["events_updated"] += 1
                if event_enricher is not None:
                    if event_id:
                        try:
                            await event_enricher.enrich_event(
                                event_id,
                                event=cast(Mapping[str, Any], event_payload),
                            )
                        except Exception as exc:
                            metrics["event_enrichment_failures"] += 1
                            logger.error(
                                f"[EIL] Failed to enrich event {event_id} for {link}: {exc}"
                            )
            except Exception as exc:
                logger.error(f"[EIL] Failed to upsert event candidate for {link}: {exc}")

        return {
            "inserted": created or duplicate_refresh,
            **metrics,
        }

    @staticmethod
    def _empty_source_metrics() -> dict[str, int]:
        return {
            "articles_seen": 0,
            "articles_inserted": 0,
            "duplicate_refreshes": 0,
            "feature_failures": 0,
            "cheap_dedup_links": 0,
            "semantic_dedup_links": 0,
            "events_created": 0,
            "events_updated": 0,
            "event_enrichment_failures": 0,
            "events_touched": 0,
        }

    def _merge_ingestion_metrics(
        self,
        target: Dict[str, Any],
        payload: Mapping[str, Any],
    ) -> None:
        for key in self._empty_source_metrics():
            target[key] = self._safe_int(target.get(key)) + self._safe_int(
                payload.get(key)
            )

    @staticmethod
    def _safe_int(value: Any) -> int:
        try:
            return int(value)
        except (TypeError, ValueError):
            return 0

    @staticmethod
    def _text(value: Any) -> str:
        if value is None:
            return ""
        if isinstance(value, str):
            return value.strip()
        return str(value).strip()
