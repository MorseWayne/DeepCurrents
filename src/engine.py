import asyncio
from typing import Optional
from .config.settings import CONFIG
from .services.db_service import DBService
from .services.collector import RSSCollector
from .services.ai_service import AIService
from .services.scorer import PredictionScorer
from .services.notifier import Notifier
from .services.clustering import cluster_news, NewsItemForClustering
from .services.classifier import classify_threat
from .utils.logger import get_logger

logger = get_logger("engine")

class DeepCurrentsEngine:
    def __init__(self):
        self.db = DBService()
        self.collector = RSSCollector(self.db)
        self.ai = AIService(self.db)
        self.scorer = PredictionScorer(self.db)
        self.notifier = Notifier()

    async def start(self):
        await self.db.connect()
        logger.info("DeepCurrents 引擎启动 (Python v2.2)")
        
        # 首次运行立即执行采集和评分
        await self.collect_data()
        await self.scorer.run_scoring_task()

    async def collect_data(self):
        """执行数据采集任务"""
        try:
            stats = await self.collector.collect_all()
            logger.info(f"采集完成: {stats}")
        except Exception as e:
            logger.error(f"采集任务失败: {e}")

    async def generate_and_send_report(self, skip_push: bool = False, skip_mark: bool = False):
        """生成并发送研报"""
        try:
            # 1. 获取未报告新闻
            raw_news = await self.db.get_unreported_news()
            if not raw_news:
                logger.info("没有新的新闻需要报告。")
                return None

            # 2. 执行分类与聚类
            items_for_clustering = []
            for n in raw_news:
                threat = classify_threat(n.title, n.content)
                items_for_clustering.append(NewsItemForClustering(
                    id=n.id, title=n.title, url=n.url, content=n.content,
                    source=n.category, sourceTier=n.tier, timestamp=n.timestamp,
                    threat=threat
                ))
            
            clusters = cluster_news(items_for_clustering)
            
            # 3. 生成 AI 研报
            report = await self.ai.generate_daily_report(raw_news, clusters)
            logger.info(f"成功生成研报: {report.date}")

            # 4. 推送通知
            if not skip_push:
                await self.notifier.deliver_all(report, len(raw_news), len(clusters))
                logger.info("✅ 研报投递完成。")
            else:
                logger.info("已跳过通知推送。")

            # 5. 标记为已报告
            if not skip_mark:
                await self.db.mark_as_reported([n.id for n in raw_news])
            
            return report

    async def cleanup(self):
        """清理过期数据"""
        try:
            count = await self.db.cleanup()
            if count > 0:
                logger.info(f"清理了 {count} 条过期数据")
        except Exception as e:
            logger.error(f"清理任务失败: {e}")
            
    async def stop(self):
        await self.db.close()
        logger.info("引擎已关闭")
