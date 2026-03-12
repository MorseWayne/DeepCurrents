import asyncio
import aiohttp
import feedparser
from typing import Any, Dict, Mapping, Optional, Protocol, cast
from ..config.settings import CONFIG
from ..config.sources import SOURCES, Source, resolve_source_url
from .circuit_breaker import RSSCircuitBreaker
from .db_service import DBService
from .article_models import ArticleRecord
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


class RSSCollector:
    def __init__(self, db: DBService):
        self.db = db
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

    def configure_event_intelligence(
        self,
        *,
        article_normalizer: ArticleNormalizerLike | None = None,
        article_repository: ArticleRepositoryLike | None = None,
        article_feature_extractor: ArticleFeatureExtractorLike | None = None,
    ) -> None:
        self.article_normalizer = article_normalizer
        self.article_repository = article_repository
        self.article_feature_extractor = article_feature_extractor

    async def collect_all(self) -> Dict[str, int]:
        """执行全量抓取任务"""
        logger.info("开始扫描全球动态...")

        # 按 tier 排序
        sorted_sources = sorted(SOURCES, key=lambda s: s.tier)

        timeout = aiohttp.ClientTimeout(total=CONFIG.rss_timeout_ms / 1000)
        connector = aiohttp.TCPConnector(limit=max(CONFIG.rss_concurrency * 2, 20))
        async with aiohttp.ClientSession(
            timeout=timeout, connector=connector
        ) as session:
            tasks = [
                self.fetch_source(source, session=session) for source in sorted_sources
            ]
            results = await asyncio.gather(*tasks)

        total_new = sum(r.get("new_count", 0) for r in results)
        total_errors = sum(1 for r in results if "error" in r)
        total_skipped = sum(1 for r in results if r.get("skipped"))

        logger.info(
            f"[采集完成] 新增 {total_new} | 跳过 {total_skipped} | 错误 {total_errors}"
        )

        return {
            "new_items": total_new,
            "errors": total_errors,
            "skipped": total_skipped,
        }

    async def fetch_source(
        self, source: Source, session: Optional[aiohttp.ClientSession] = None
    ) -> Dict[str, Any]:
        """抓取单个源"""
        if self.breaker.is_on_cooldown(source.name):
            return {"skipped": True}

        async with self.semaphore:
            managed_session = session is None
            active_session = session or aiohttp.ClientSession()
            request_timeout = aiohttp.ClientTimeout(total=CONFIG.rss_timeout_ms / 1000)
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

                    if await self.db.has_news(link):
                        continue
                    if await self.db.has_similar_title(title):
                        continue

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

                    # 保存新闻
                    inserted = await self.db.save_news(
                        link,
                        title,
                        final_content,
                        source.name,
                        meta={"tier": source.tier, "sourceType": source.type},
                    )
                    if inserted:
                        new_count += 1
                        raw_published = entry.get("published") or entry.get("updated")
                        await self._sync_event_intelligence_article(
                            link=link,
                            title=title,
                            summary=summary,
                            content=final_content,
                            source=source,
                            published=raw_published
                            if isinstance(raw_published, str)
                            else None,
                        )

                self.breaker.record_success(source.name)
                if new_count > 0:
                    logger.info(f"[+{new_count}] T{source.tier} {source.name}")

                return {"new_count": new_count}

            except Exception as e:
                self.breaker.record_failure(source.name)
                err = str(e).strip() or e.__class__.__name__
                logger.error(f"[ERR] T{source.tier} {source.name}: {err}")
                return {"error": err}
            finally:
                if managed_session:
                    await active_session.close()

    async def _sync_event_intelligence_article(
        self,
        *,
        link: str,
        title: str,
        summary: str,
        content: str,
        source: Source,
        published: str | None,
    ) -> None:
        article_normalizer = self.article_normalizer
        article_repository = self.article_repository
        article_feature_extractor = self.article_feature_extractor
        if (
            article_normalizer is None
            or article_repository is None
            or article_feature_extractor is None
        ):
            return

        normalizer = cast(ArticleNormalizerLike, article_normalizer)
        repository = cast(ArticleRepositoryLike, article_repository)
        feature_extractor = cast(ArticleFeatureExtractorLike, article_feature_extractor)

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
            try:
                await repository.create_article(article.to_article_payload())
            except Exception as exc:
                existing = await repository.get_article(article.article_id)
                if existing is None:
                    raise
                logger.warning(
                    f"[EIL] Article already exists for {link}; refreshing features: {exc}"
                )
            await feature_extractor.extract_and_persist(article)
        except Exception as exc:
            logger.error(f"[EIL] Failed to persist article {link}: {exc}")
