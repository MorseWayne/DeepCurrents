import asyncio
import argparse
import sys
import os
import time
from typing import List, Dict, Any
import aiohttp
import feedparser

# 确保可以导入项目模块
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.config.sources import SOURCES, Source
from src.config.settings import CONFIG
from src.utils.logger import get_logger
from src.utils.network import resolve_request_proxy
from src.services.notifier import Notifier
from src.services.report_models import (
    DailyReport,
    GlobalEvent,
    IntelligenceItem,
    IntelSource,
    InvestmentTrend,
)
from src.utils.market_data import get_market_price

logger = get_logger("test_tools")

class TestSuite:
    __test__ = False  # Prevent pytest from collecting this utility class.

    def __init__(self):
        self.notifier = Notifier()
        self.rss_retry_statuses = {429, 500, 502, 503, 504}
        self.rss_max_retries = 2
        self.rss_retry_base_delay = 0.8

    async def test_rss(self, all_sources: bool = True):
        """测试 RSS 源联通性"""
        targets = SOURCES if all_sources else SOURCES[:5]
        logger.info(f"--- 开始测试 RSS 信息源 (共 {len(targets)} 个) ---")

        timeout = aiohttp.ClientTimeout(total=CONFIG.rss_timeout_ms / 1000)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            # 使用信号量限制并发，防止被封 IP
            sem = asyncio.Semaphore(CONFIG.rss_concurrency)
            async def sem_check(s):
                async with sem:
                    return await self._check_one_rss(session, s)
            
            tasks = [sem_check(s) for s in targets]
            results = await asyncio.gather(*tasks)
        
        passed = sum(1 for r in results if r)
        failed = len(targets) - passed
        logger.info(f"--- RSS 测试报告 ---")
        logger.info(f"总计: {len(targets)} | 通过: {passed} | 失败: {failed}")
        return passed, failed

    async def _check_one_rss(self, session: aiohttp.ClientSession, source: Source) -> bool:
        url = source.url
        # 如果配置了 RSSHUB_BASE_URL 且是 RSSHub 源，则替换 URL
        if source.is_rss_hub and CONFIG.rsshub_base_url:
            url = url.replace("https://rsshub.app", CONFIG.rsshub_base_url.rstrip("/"))
        
        type_label = "[RSSHub]" if source.is_rss_hub else "[RSS]"
        proxy = resolve_request_proxy(url, CONFIG.https_proxy)

        for attempt in range(self.rss_max_retries + 1):
            try:
                # aiohttp 仅原生支持 http 代理，如果是 socks5 需要 aiohttp-socks
                # 这里先尝试标准代理传参
                async with session.get(url, timeout=15, proxy=proxy) as resp:
                    if resp.status == 200:
                        content = await resp.text()
                        feed = feedparser.parse(content)
                        if feed.bozo and not feed.entries:
                            logger.error(f"❌ {type_label} T{source.tier} {source.name} 失败: 解析错误且无条目")
                            return False

                        logger.info(f"✅ {type_label} T{source.tier} {source.name}: {len(feed.entries)} 条新闻")
                        return True

                    if resp.status in self.rss_retry_statuses and attempt < self.rss_max_retries:
                        delay = self.rss_retry_base_delay * (2 ** attempt)
                        logger.warning(
                            f"⏳ {type_label} T{source.tier} {source.name} 返回 HTTP {resp.status}，"
                            f"{delay:.1f}s 后重试 ({attempt + 1}/{self.rss_max_retries})"
                        )
                        await asyncio.sleep(delay)
                        continue

                    logger.error(f"❌ {type_label} T{source.tier} {source.name} 失败: HTTP {resp.status}")
                    return False

            except aiohttp.ClientResponseError as e:
                if e.status in self.rss_retry_statuses and attempt < self.rss_max_retries:
                    delay = self.rss_retry_base_delay * (2 ** attempt)
                    logger.warning(
                        f"⏳ {type_label} T{source.tier} {source.name} 返回 HTTP {e.status}，"
                        f"{delay:.1f}s 后重试 ({attempt + 1}/{self.rss_max_retries})"
                    )
                    await asyncio.sleep(delay)
                    continue

                logger.error(f"❌ {type_label} T{source.tier} {source.name} 失败: {str(e)}")
                return False
            except (
                asyncio.TimeoutError,
                aiohttp.ClientConnectionError,
                aiohttp.ServerDisconnectedError,
                aiohttp.ClientOSError,
            ) as e:
                if attempt < self.rss_max_retries:
                    delay = self.rss_retry_base_delay * (2 ** attempt)
                    logger.warning(
                        f"⏳ {type_label} T{source.tier} {source.name} 请求异常: {str(e)}，"
                        f"{delay:.1f}s 后重试 ({attempt + 1}/{self.rss_max_retries})"
                    )
                    await asyncio.sleep(delay)
                    continue

                logger.error(f"❌ {type_label} T{source.tier} {source.name} 失败: {str(e)}")
                return False
            except aiohttp.ClientError as e:
                logger.error(f"❌ {type_label} T{source.tier} {source.name} 失败: {str(e)}")
                return False
            except Exception as e:
                logger.error(f"❌ {type_label} T{source.tier} {source.name} 失败: {str(e)}")
                return False

        return False

    async def test_llm(self):
        """测试 LLM 联通性"""
        logger.info("--- 开始测试 LLM (AI) 服务 ---")
        if not CONFIG.ai_api_key:
            logger.error("❌ [AI] 未配置 AI_API_KEY")
            return False

        try:
            # 模拟简单的提示词测试
            async with aiohttp.ClientSession() as session:
                headers = {"Authorization": f"Bearer {CONFIG.ai_api_key}"}
                payload = {
                    "model": CONFIG.ai_model,
                    "messages": [{"role": "user", "content": "Say hello and confirm you are online."}],
                    "max_tokens": 50
                }
                async with session.post(CONFIG.ai_api_url, json=payload, headers=headers, timeout=20) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        content = data['choices'][0]['message']['content']
                        logger.info(f"✅ [AI] 主提供商响应成功: {content.strip()}")
                        return True
                    else:
                        text = await resp.text()
                        logger.error(f"❌ [AI] 主提供商失败: HTTP {resp.status} - {text}")
                        return False
        except Exception as e:
            logger.error(f"❌ [AI] 测试异常: {str(e)}")
            return False

    async def test_feishu(self):
        """测试飞书推送"""
        logger.info("--- 开始测试飞书推送 ---")
        if not CONFIG.feishu_webhook:
            logger.warning("⚠️ [Feishu] 未配置 FEISHU_WEBHOOK")
            return False

        # 构造一个模拟研报
        mock_report = self._get_mock_report()
        try:
            await self.notifier.send_to_feishu(mock_report, news_count=10, cluster_count=2)
            logger.info("✅ [Feishu] 测试卡片已发送")
            return True
        except Exception as e:
            logger.error(f"❌ [Feishu] 发送失败: {str(e)}")
            return False

    async def test_tg(self):
        """测试 Telegram 推送"""
        logger.info("--- 开始测试 Telegram 推送 ---")
        if not CONFIG.telegram_bot_token or not CONFIG.telegram_chat_id:
            logger.warning("⚠️ [Telegram] 未配置 TELEGRAM_BOT_TOKEN 或 TELEGRAM_CHAT_ID")
            return False

        mock_report = self._get_mock_report()
        try:
            await self.notifier.send_to_telegram(mock_report)
            logger.info("✅ [Telegram] 测试消息已发送")
            return True
        except Exception as e:
            logger.error(f"❌ [Telegram] 发送失败: {str(e)}")
            return False

    async def test_market(self):
        """测试市场数据获取"""
        logger.info("--- 开始测试市场数据获取 (yfinance) ---")
        symbols = ["GC=F", "CL=F", "^GSPC"] # 黄金, 原油, 标普500
        passed = 0
        for sym in symbols:
            try:
                data = await get_market_price(sym)
                if data:
                    logger.info(f"✅ [Market] {sym}: ${data['price']} ({data['changePercent']:+.2f}%)")
                    passed += 1
                else:
                    logger.error(f"❌ [Market] {sym}: 获取结果为空")
            except Exception as e:
                logger.error(f"❌ [Market] {sym} 失败: {str(e)}")
        return passed == len(symbols)

    def _get_mock_report(self) -> DailyReport:
        return DailyReport(
            date=time.strftime("%Y-%m-%d"),
            executiveSummary="[测试消息] 🌊 DeepCurrents Python v2.2 拨测正常。当前系统各项组件联通性良好。",
            intelligenceDigest=[
                IntelligenceItem(
                    content="系统检测到全球情报采集管线运行平稳，35+ 信息源已准备就绪。",
                    category="meta",
                    importance="low",
                    credibility="high",
                    credibilityReason="内部自动化测试拨测结果",
                    sources=[IntelSource(name="SystemCheck", tier=1, url="internal")]
                )
            ],
            globalEvents=[
                GlobalEvent(title="测试事件: 核心引擎就绪", detail="DeepCurrents 多智能体系统已通过环境检查，支持地缘宏观与市场情绪并行分析。", threatLevel="low")
            ],
            economicAnalysis="这是一段模拟的宏观分析。系统当前运行环境：Python 3.10+, Async I/O, Pydantic v2。",
            investmentTrends=[
                InvestmentTrend(assetClass="Global Equities", trend="Neutral", confidence=100.0, rationale="测试数据，系统连通性良好。", timeframe="Short-term")
            ],
            riskAssessment="低风险。此为自动化拨测产生的临时消息。"
        )

async def main():
    parser = argparse.ArgumentParser(description="DeepCurrents v2.2 集成测试与拨测工具")
    parser.add_argument("--rss", action="store_true", help="并发验证所有 35+ 个信息源 (RSS/RSSHub)")
    parser.add_argument("--llm", action="store_true", help="测试 LLM (AI) 服务联通性")
    parser.add_argument("--feishu", action="store_true", help="发送飞书测试消息")
    parser.add_argument("--tg", action="store_true", help="发送 Telegram 测试消息")
    parser.add_argument("--market", action="store_true", help="测试 yfinance 行情数据")
    parser.add_argument("--all", action="store_true", help="运行所有测试")

    args = parser.parse_args()
    suite = TestSuite()

    if len(sys.argv) == 1:
        parser.print_help()
        return

    if args.all:
        await suite.test_rss()
        await suite.test_llm()
        await suite.test_market()
        await suite.test_feishu()
        await suite.test_tg()
    else:
        if args.rss:
            await suite.test_rss()
        if args.llm:
            await suite.test_llm()
        if args.market:
            await suite.test_market()
        if args.feishu:
            await suite.test_feishu()
        if args.tg:
            await suite.test_tg()

if __name__ == "__main__":
    asyncio.run(main())
