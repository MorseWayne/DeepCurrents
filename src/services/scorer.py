import asyncio
import time
from datetime import datetime
from ..services.db_service import DBService
from ..utils.market_data import get_market_price
from ..utils.logger import get_logger

logger = get_logger("scorer")

class PredictionScorer:
    def __init__(self, db: DBService = None):
        self.db = db or DBService()

    async def run_scoring_task(self):
        """运行评分任务：处理所有待评分的预测记录"""
        logger.info("开始运行预测评分任务...")
        pending = await self.db.get_pending_predictions()
        
        if not pending:
            logger.info("没有待评分的预测记录。")
            return

        for p in pending:
            try:
                # 检查预测时间是否已超过 10 秒 (演示逻辑)
                # 生产环境通常需要 12h+
                timestamp_str = p['base_timestamp'].replace('Z', '+00:00')
                prediction_time = datetime.fromisoformat(timestamp_str).timestamp()
                if time.time() - prediction_time < 10:
                    logger.debug(f"预测 {p['id']} 时间过短，跳过评分。")
                    continue

                current_data = await get_market_price(p['asset_symbol'])
                current_price = current_data['price']
                base_price = p['base_price']
                change_percent = ((current_price - base_price) / base_price) * 100
                
                score = 50.0 # 基准分
                p_type = p['prediction_type'].lower()
                
                if p_type == 'bullish':
                    if change_percent > 0.5: score = 90.0 + min(10.0, change_percent)
                    elif change_percent > 0: score = 70.0
                    elif change_percent < -0.5: score = 10.0
                    else: score = 40.0
                elif p_type == 'bearish':
                    if change_percent < -0.5: score = 90.0 + min(10.0, abs(change_percent))
                    elif change_percent < 0: score = 70.0
                    elif change_percent > 0.5: score = 10.0
                    else: score = 40.0
                else: # Neutral
                    if abs(change_percent) < 0.2: score = 90.0
                    elif abs(change_percent) < 0.5: score = 60.0
                    else: score = 20.0

                await self.db.update_prediction_score(p['id'], score, current_price)
                logger.info(f"✅ 预测已评分 [{p['id']}]: {p['asset_symbol']} 类型:{p_type} 基准:{base_price} 当前:{current_price} 变化:{change_percent:.2f}% 得分:{score}")
            
            except Exception as e:
                logger.error(f"[Scorer] 评分 {p['id']} 失败: {e}")
