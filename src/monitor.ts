import Parser from 'rss-parser';
import pLimit from 'p-limit';
import pino from 'pino';
import cron from 'node-cron';
import axios from 'axios';
import * as dotenv from 'dotenv';
import { AIService, DailyReport } from './services/ai.service';
import { DBService } from './services/db.service';
import { SOURCES } from './config/sources';

dotenv.config();

// 品牌化日志记录
const logger = pino({ 
  name: 'DeepCurrents', 
  level: 'info', 
  transport: { target: 'pino-pretty', options: { colorize: true } } 
});

export class DeepCurrentsEngine {
  private parser = new Parser({ timeout: 15000 });
  private ai = new AIService();
  private db = new DBService();
  private rssLimit = pLimit(10); 

  public start() {
    logger.info("DeepCurrents Engine (v1.0.0) 已就绪。宏观监测任务已调度。");

    // 1. 数据收集：每小时
    cron.schedule('0 * * * *', async () => {
      logger.info("[Collector] 正在扫描全球动态...");
      await this.collectData();
    });

    // 2. 深度报告：每天 08:00
    cron.schedule('0 8 * * *', async () => {
      logger.info("[Reporter] 正在合成每日深流研报...");
      await this.generateAndSendReport();
    });

    this.collectData();
    // 调试：立即生成一份报告请解除下行注释
    // this.generateAndSendReport();
  }

  private async collectData() {
    const tasks = SOURCES.map(source => this.rssLimit(async () => {
      try {
        const feed = await this.parser.parseURL(source.url);
        let newCount = 0;
        for (const item of feed.items) {
          if (!item.link || !item.title) continue;
          if (!this.db.hasNews(item.link)) {
            this.db.saveNews(item.link, item.title, item.contentSnippet || item.content || "", source.name);
            newCount++;
          }
        }
        logger.info(`[+${newCount}] 源: ${source.name}`);
      } catch (e) {
        logger.error(`[ERR] ${source.name}: ${e.message}`);
      }
    }));
    await Promise.all(tasks);
  }

  private async generateAndSendReport() {
    const unreportedNews = this.db.getUnreportedNews();
    if (unreportedNews.length === 0) return;

    try {
      const report = await this.ai.generateDailyReport(unreportedNews);
      await this.sendToFeishu(report, unreportedNews.length);
      const ids = unreportedNews.map(n => n.id);
      this.db.markAsReported(ids);
      logger.info("DeepCurrents 每日研报投递成功。");
    } catch (e) {
      logger.error(`研报投递失败: ${e.message}`);
    }
  }

  private async sendToFeishu(report: DailyReport, newsCount: number) {
    const webhookUrl = process.env.FEISHU_WEBHOOK;
    if (!webhookUrl) return;

    let mdContent = `**🌊 核心主线 | Executive Summary**\n${report.executiveSummary}\n\n`;
    
    mdContent += `**🌍 地缘与宏观重大事件 | Key Events**\n`;
    report.globalEvents.forEach((e, i) => {
      mdContent += `${i+1}. **${e.title}**: ${e.detail}\n`;
    });
    mdContent += `\n`;

    mdContent += `**📈 宏观趋势深度研判 | Deep Insights**\n${report.economicAnalysis}\n\n`;

    mdContent += `**💼 资产配置与投资风向 | Investment Strategy**\n`;
    report.investmentTrends.forEach(t => {
      const icon = t.trend === 'Bullish' ? '🟢 看涨' : t.trend === 'Bearish' ? '🔴 看跌' : '⚪ 中性';
      mdContent += `- **${t.assetClass}** (${icon}): ${t.rationale}\n`;
    });
    
    mdContent += `\n--- \n*DeepCurrents Intelligence (v1.0.0) | 样本源: ${newsCount} | 发布日期: ${report.date}*`;

    const card = {
      msg_type: "interactive",
      card: {
        config: { wide_screen_mode: true },
        header: { 
          title: { content: `🌊 DeepCurrents: 每日全球情报与宏观策略`, tag: "plain_text" }, 
          template: "indigo" // 深蓝色系，符合 DeepCurrents 品牌
        },
        elements: [{ tag: "markdown", content: mdContent }]
      }
    };

    await axios.post(webhookUrl, card);
  }
}

new DeepCurrentsEngine().start();
