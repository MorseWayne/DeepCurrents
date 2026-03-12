import asyncio
import aiohttp
import feedparser
from typing import List, Dict, Any, Optional
from ..config.settings import CONFIG
from ..config.sources import SOURCES, Source, resolve_source_url
from .circuit_breaker import RSSCircuitBreaker
from .db_service import DBService
from ..utils.extractor import Extractor
from ..utils.logger import get_logger

logger = get_logger("collector")

class RSSCollector:
    def __init__(self, db: DBService):
        self.db = db
        self.breaker = RSSCircuitBreaker(
            max_failures=CONFIG.cb_max_failures,
            cooldown_ms=CONFIG.cb_cooldown_ms
        )
        self.semaphore = asyncio.Semaphore(CONFIG.rss_concurrency)

    async def collect_all(self) -> Dict[str, int]:
        """执行全量抓取任务"""
        logger.info("开始扫描全球动态...")
        
        # 按 tier 排序
        sorted_sources = sorted(SOURCES, key=lambda s: s.tier)

        timeout = aiohttp.ClientTimeout(total=CONFIG.rss_timeout_ms / 1000)
        connector = aiohttp.TCPConnector(limit=max(CONFIG.rss_concurrency * 2, 20))
        async with aiohttp.ClientSession(timeout=timeout, connector=connector) as session:
            tasks = [self.fetch_source(source, session=session) for source in sorted_sources]
            results = await asyncio.gather(*tasks)
        
        total_new = sum(r.get('new_count', 0) for r in results)
        total_errors = sum(1 for r in results if r.get('error'))
        total_skipped = sum(1 for r in results if r.get('skipped'))
        
        logger.info(f"[采集完成] 新增 {total_new} | 跳过 {total_skipped} | 错误 {total_errors}")
        
        return {
            "new_items": total_new,
            "errors": total_errors,
            "skipped": total_skipped
        }

    async def fetch_source(self, source: Source, session: Optional[aiohttp.ClientSession] = None) -> Dict[str, Any]:
        """抓取单个源"""
        if self.breaker.is_on_cooldown(source.name):
            return {"skipped": True}

        async with self.semaphore:
            managed_session = session is None
            active_session = session or aiohttp.ClientSession()
            try:
                url = resolve_source_url(source)
                async with active_session.get(url, timeout=CONFIG.rss_timeout_ms / 1000) as response:
                    if response.status != 200:
                        raise Exception(f"HTTP {response.status}")
                    content = await response.text()
                
                feed = feedparser.parse(content)
                new_count = 0
                
                for entry in feed.entries:
                    link = entry.get('link')
                    title = entry.get('title')
                    if not link or not title: continue

                    if await self.db.has_news(link): continue
                    if await self.db.has_similar_title(title): continue

                    # 提取内容
                    summary = entry.get('summary', '') or entry.get('description', '')
                    final_content = summary

                    # 高优源尝试全文提取
                    if source.tier <= 2:
                        extracted = await Extractor.extract(link, session=active_session)
                        if extracted and len(extracted['content']) > len(final_content):
                            final_content = extracted['content']

                    # 保存新闻
                    inserted = await self.db.save_news(
                        link, title, final_content, source.name,
                        meta={
                            'tier': source.tier,
                            'sourceType': source.type
                        }
                    )
                    if inserted:
                        new_count += 1

                self.breaker.record_success(source.name)
                if new_count > 0:
                    logger.info(f"[+{new_count}] T{source.tier} {source.name}")
                
                return {"new_count": new_count}

            except Exception as e:
                self.breaker.record_failure(source.name)
                logger.error(f"[ERR] T{source.tier} {source.name}: {e}")
                return {"error": str(e)}
            finally:
                if managed_session:
                    await active_session.close()
