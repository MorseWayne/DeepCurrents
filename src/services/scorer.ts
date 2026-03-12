import { DBService } from './db.service';
import { getMarketPrice } from '../utils/market-data';
import { getLogger } from '../utils/logger';

const logger = getLogger('scorer');

export class PredictionScorer {
  private db = new DBService();

  /**
   * 运行评分任务：处理所有待评分的预测记录
   */
  public async runScoringTask() {
    logger.info('开始运行预测评分任务...');
    const pending = this.db.getPendingPredictions();
    
    if (pending.length === 0) {
      logger.info('没有待评分的预测记录。');
      return;
    }

    for (const p of pending) {
      try {
        // 检查预测时间是否已超过 12 小时（避免太早评分）
        // 这里为了演示方便，放宽到 10 秒
        const predictionTime = new Date(p.base_timestamp).getTime();
        if (Date.now() - predictionTime < 10000) {
          logger.debug(`预测 ${p.id} 时间过短，跳过评分。`);
          continue;
        }

        const currentData = await getMarketPrice(p.asset_symbol);
        const currentPrice = currentData.price;
        const basePrice = p.base_price;
        const changePercent = ((currentPrice - basePrice) / basePrice) * 100;
        
        let score = 50; // 基准分
        
        if (p.prediction_type === 'bullish') {
          if (changePercent > 0.5) score = 90 + Math.min(10, changePercent);
          else if (changePercent > 0) score = 70;
          else if (changePercent < -0.5) score = 10;
          else score = 40;
        } else if (p.prediction_type === 'bearish') {
          if (changePercent < -0.5) score = 90 + Math.min(10, Math.abs(changePercent));
          else if (changePercent < 0) score = 70;
          else if (changePercent > 0.5) score = 10;
          else score = 40;
        } else {
          // Neutral
          if (Math.abs(changePercent) < 0.2) score = 90;
          else if (Math.abs(changePercent) < 0.5) score = 60;
          else score = 20;
        }

        this.db.updatePredictionScore(p.id, score, currentPrice);
        logger.info(`✅ 预测已评分 [${p.id}]: ${p.asset_symbol} 类型:${p.prediction_type} 基准:${basePrice} 当前:${currentPrice} 变化:${changePercent.toFixed(2)}% 得分:${score}`);
      } catch (e: any) {
        logger.error(`[Scorer] 评分 ${p.id} 失败: ${e.message}`);
      }
    }
  }
}
