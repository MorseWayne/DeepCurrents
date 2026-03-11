import Parser from 'rss-parser';
import pLimit from 'p-limit';
import pino from 'pino';
import cron from 'node-cron';
import axios from 'axios';
import * as dotenv from 'dotenv';
import { AIService, DailyReport } from './services/ai.service';
import { DBService } from './services/db.service';
import { SOURCES, Source } from './config/sources';
import { classifyThreat, THREAT_LABELS, ThreatClassification } from './services/classifier';
import { RSSCircuitBreaker } from './services/circuit-breaker';
import { clusterNews, ClusteredEvent, NewsItemForClustering } from './services/clustering';
import { ingestHeadlines, detectSpikes, generateTrendingContext, getTrackedTermCount } from './services/trending';

dotenv.config();

const logger = pino({ 
  name: 'DeepCurrents', 
  level: 'info', 
  transport: { target: 'pino-pretty', options: { colorize: true } } 
});

/**
 * DeepCurrents Engine v2.0
 * 
 * 借鉴 WorldMonitor 的如下核心技术：
 * 1. 信息源分级 & 熔断容错
 * 2. 威胁分类管线
 * 3. 新闻聚类（碎片→宏观事件）
 * 4. 趋势关键词检测
 * 5. 多维 AI 上下文注入
 * 6. AI 回退链
 */
export class DeepCurrentsEngine {
  private parser = new Parser({ timeout: 15000 });
  private ai = new AIService();
  private db = new DBService();
  private breaker = new RSSCircuitBreaker({ maxFailures: 3, cooldownMs: 5 * 60 * 1000 });
  private rssLimit = pLimit(10);

  public start() {
    logger.info("╔══════════════════════════════════════════════════════════╗");
    logger.info("║     🌊 DeepCurrents Engine v2.0 — 宏观情报引擎         ║");
    logger.info("║     Source Tier System | Threat Classification          ║");
    logger.info("║     News Clustering | Trending Detection                ║");
    logger.info("╚══════════════════════════════════════════════════════════╝");
    logger.info(`已加载 ${SOURCES.length} 个信息源（T1:${SOURCES.filter(s=>s.tier===1).length} T2:${SOURCES.filter(s=>s.tier===2).length} T3:${SOURCES.filter(s=>s.tier===3).length} T4:${SOURCES.filter(s=>s.tier===4).length}）`);

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

    // 3. 数据清理：每天 03:00
    cron.schedule('0 3 * * *', () => {
      const cleaned = this.db.cleanup(30);
      if (cleaned > 0) logger.info(`[Cleanup] 清理了 ${cleaned} 条过期数据`);
    });

    // 首次启动立即执行
    this.collectData();
  }

  /**
   * 数据采集管线（增强版）
   * 
   * 改进点：
   * 1. 熔断器：失败源自动冷却，返回缓存
   * 2. 威胁分类：每条新闻入库前分类
   * 3. 趋势检测：注入标题到趋势引擎
   * 4. 统计报告：每轮采集后打印摘要
   */
  private async collectData() {
    let totalNew = 0;
    let totalSkipped = 0;
    let totalErrors = 0;
    const allHeadlines: Array<{ title: string; pubDate: Date; source: string; link?: string }> = [];

    // 按 tier 分优先级批次处理
    const sortedSources = [...SOURCES].sort((a, b) => a.tier - b.tier);

    const tasks = sortedSources.map(source => this.rssLimit(async () => {
      // 熔断器检查
      if (this.breaker.isOnCooldown(source.name)) {
        totalSkipped++;
        return;
      }

      try {
        const feed = await this.parser.parseURL(source.url);
        let newCount = 0;

        for (const item of feed.items) {
          if (!item.link || !item.title) continue;

          // URL 去重 + 标题去重双重检查
          if (this.db.hasNews(item.link)) continue;
          if (this.db.hasSimilarTitle(item.title)) continue;

          // 威胁分类
          const threat = classifyThreat(item.title);

          // 入库（附带分级和威胁元数据）
          this.db.saveNews(
            item.link,
            item.title,
            item.contentSnippet || item.content || "",
            source.name,
            {
              tier: source.tier,
              sourceType: source.type,
              threatLevel: threat.level,
              threatCategory: threat.category,
              threatConfidence: threat.confidence,
            }
          );

          // 收集标题用于趋势检测
          allHeadlines.push({
            title: item.title,
            pubDate: item.pubDate ? new Date(item.pubDate) : new Date(),
            source: source.name,
            link: item.link,
          });

          newCount++;
        }

        totalNew += newCount;
        this.breaker.recordSuccess(source.name);

        // 缓存最新数据（用于熔断回退）
        this.breaker.setCache(source.name, feed.items);

        if (newCount > 0) {
          const tierTag = `T${source.tier}`;
          logger.info(`[+${newCount}] ${tierTag} ${source.name}`);
        }
      } catch (e: any) {
        totalErrors++;
        this.breaker.recordFailure(source.name);
        logger.error(`[ERR] T${source.tier} ${source.name}: ${e.message}`);
      }
    }));

    await Promise.all(tasks);

    // 注入趋势检测引擎
    if (allHeadlines.length > 0) {
      ingestHeadlines(allHeadlines);
    }

    // 检测飙升关键词
    const spikes = detectSpikes();
    if (spikes.length > 0) {
      logger.info(`[Trending] 检测到 ${spikes.length} 个飙升关键词`);
      for (const spike of spikes.slice(0, 3)) {
        logger.info(`  📈 "${spike.term}" — ${spike.count} mentions, ${spike.uniqueSources} sources`);
      }
    }

    // 采集摘要
    const breakerSummary = this.breaker.getSummary();
    const dbStats = this.db.getStats();
    logger.info(`[采集完成] 新增 ${totalNew} | 跳过 ${totalSkipped} | 错误 ${totalErrors} | 熔断 ${breakerSummary.onCooldown} | 趋势词 ${getTrackedTermCount()}`);
    logger.info(`[数据库] 总量 ${dbStats.total} | 待报告 ${dbStats.unreported} | 威胁分布: ${JSON.stringify(dbStats.byThreat)}`);
  }

  /**
   * 生成并发送研报（增强版）
   * 
   * 改进点：
   * 1. 新闻聚类：碎片 → 宏观事件
   * 2. 趋势信号注入
   * 3. 增强研报格式（含趋势告警、风险评估）
   */
  private async generateAndSendReport() {
    const unreportedNews = this.db.getUnreportedNews();
    if (unreportedNews.length === 0) {
      logger.info("[Reporter] 无新数据，跳过报告生成。");
      return;
    }

    try {
      // 1. 新闻聚类
      const itemsForClustering: NewsItemForClustering[] = unreportedNews.map(n => ({
        id: n.id,
        title: n.title,
        url: n.url,
        content: n.content,
        source: n.category,
        sourceTier: n.tier || 4,
        timestamp: n.timestamp,
        threat: classifyThreat(n.title),
      }));

      const clusters = clusterNews(itemsForClustering);
      logger.info(`[聚类] ${unreportedNews.length} 条新闻 → ${clusters.length} 个聚类事件`);

      // 2. 趋势检测
      const spikes = detectSpikes();

      // 3. 生成报告（多维上下文注入）
      const report = await this.ai.generateDailyReport(unreportedNews, clusters, spikes);

      // 4. 分发
      await this.sendToFeishu(report, unreportedNews.length, clusters.length);
      await this.sendToTelegram(report);

      // 5. 标记
      const ids = unreportedNews.map(n => n.id);
      this.db.markAsReported(ids);
      logger.info("✅ DeepCurrents 每日研报投递成功。");
    } catch (e: any) {
      logger.error(`研报投递失败: ${e.message}`);
    }
  }

  /**
   * 飞书投递（增强版：含趋势告警和风险评估）
   */
  private async sendToFeishu(report: DailyReport, newsCount: number, clusterCount: number) {
    const webhookUrl = process.env.FEISHU_WEBHOOK;
    if (!webhookUrl) return;

    let mdContent = `**🌊 核心主线 | Executive Summary**\n${report.executiveSummary}\n\n`;
    
    mdContent += `**🌍 重大事件 | Key Events** *(${clusterCount} 个聚类事件)*\n`;
    report.globalEvents.forEach((e, i) => {
      const threatIcon = e.threatLevel ? (THREAT_LABELS[e.threatLevel as keyof typeof THREAT_LABELS] || '') + ' ' : '';
      mdContent += `${i+1}. ${threatIcon}**${e.title}**: ${e.detail}\n`;
    });
    mdContent += `\n`;

    // 趋势告警（新增）
    if (report.trendingAlerts && report.trendingAlerts.length > 0) {
      mdContent += `**📈 趋势告警 | Trending Alerts**\n`;
      for (const alert of report.trendingAlerts) {
        const sigIcon = alert.significance === 'high' ? '🔴' : alert.significance === 'medium' ? '🟡' : '🟢';
        mdContent += `- ${sigIcon} **${alert.term}**: ${alert.assessment}\n`;
      }
      mdContent += `\n`;
    }

    mdContent += `**📈 宏观趋势深度研判 | Deep Insights**\n${report.economicAnalysis}\n\n`;

    mdContent += `**💼 资产配置与投资风向 | Investment Strategy**\n`;
    report.investmentTrends.forEach(t => {
      const icon = t.trend === 'Bullish' ? '🟢 看涨' : t.trend === 'Bearish' ? '🔴 看跌' : '⚪ 中性';
      const conf = t.confidence ? ` (${t.confidence}%)` : '';
      mdContent += `- **${t.assetClass}** (${icon}${conf}): ${t.rationale}\n`;
    });

    // 风险评估（新增）
    if (report.riskAssessment) {
      mdContent += `\n**⚠️ 风险评估 | Risk Assessment**\n${report.riskAssessment}\n`;
    }
    
    mdContent += `\n--- \n*DeepCurrents Intelligence (v2.0) | 样本源: ${newsCount} 条 → ${clusterCount} 事件 | ${report.date}*`;

    const card = {
      msg_type: "interactive",
      card: {
        config: { wide_screen_mode: true },
        header: { 
          title: { content: `🌊 DeepCurrents: 每日全球情报与宏观策略`, tag: "plain_text" }, 
          template: "indigo"
        },
        elements: [{ tag: "markdown", content: mdContent }]
      }
    };

    await axios.post(webhookUrl, card);
  }

  /**
   * Telegram 投递
   */
  private async sendToTelegram(report: DailyReport) {
    const token = process.env.TELEGRAM_BOT_TOKEN;
    const chatId = process.env.TELEGRAM_CHAT_ID;
    if (!token || !chatId) return;

    let text = `🌊 *DeepCurrents Daily Intelligence*\n📅 ${report.date}\n\n`;
    text += `*核心主线:* ${report.executiveSummary}\n\n`;

    text += `*📊 重大事件:*\n`;
    report.globalEvents.slice(0, 5).forEach((e, i) => {
      text += `${i+1}. *${e.title}*: ${e.detail.substring(0, 100)}...\n`;
    });
    text += `\n`;

    text += `*💼 资产研判:*\n`;
    report.investmentTrends.forEach(t => {
      const icon = t.trend === 'Bullish' ? '📈' : t.trend === 'Bearish' ? '📉' : '➡️';
      text += `${icon} *${t.assetClass}* (${t.trend}): ${t.rationale.substring(0, 80)}...\n`;
    });

    const url = `https://api.telegram.org/bot${token}/sendMessage`;
    await axios.post(url, {
      chat_id: chatId,
      text,
      parse_mode: "Markdown"
    });
  }
}

new DeepCurrentsEngine().start();
