import Parser from 'rss-parser';
import pLimit from 'p-limit';
import pino from 'pino';
import cron, { ScheduledTask } from 'node-cron';
import axios from 'axios';
import { CONFIG } from './config/settings';
import { AIService, DailyReport } from './services/ai.service';
import { DBService } from './services/db.service';
import { SOURCES, Source } from './config/sources';
import { classifyThreat, THREAT_LABELS, ThreatClassification } from './services/classifier';
import { RSSCircuitBreaker } from './services/circuit-breaker';
import { clusterNews, ClusteredEvent, NewsItemForClustering } from './services/clustering';
import { ingestHeadlines, detectSpikes, generateTrendingContext, getTrackedTermCount } from './services/trending';

const logger = pino({ 
  name: 'DeepCurrents', 
  level: 'info', 
  transport: { target: 'pino-pretty', options: { colorize: true, destination: 2 } } 
});

// ── 通用重试工具（指数退避）──

async function retryWithBackoff<T>(
  fn: () => Promise<T>,
  label: string,
  maxRetries: number = CONFIG.NOTIFY_MAX_RETRIES,
  baseDelayMs: number = CONFIG.NOTIFY_BASE_DELAY_MS,
): Promise<T> {
  let lastError: Error | undefined;
  for (let attempt = 0; attempt <= maxRetries; attempt++) {
    try {
      return await fn();
    } catch (e: any) {
      lastError = e;
      if (attempt < maxRetries) {
        const delay = baseDelayMs * Math.pow(2, attempt);
        logger.warn(`[Retry] ${label} 第 ${attempt + 1}/${maxRetries} 次失败，${delay}ms 后重试: ${e.message}`);
        await new Promise(resolve => setTimeout(resolve, delay));
      }
    }
  }
  throw lastError;
}

export interface CollectResult {
  newItems: number;
  skippedSources: number;
  errors: number;
  spikeCount: number;
}

export interface ReportResult {
  report: DailyReport;
  newsIds: string[];
  newsCount: number;
  clusterCount: number;
}

/**
 * DeepCurrents Engine v2.1
 * 
 * v2.0 基础上的增强：
 * - 配置外部化（所有阈值可通过 .env 调整）
 * - 通知推送指数退避重试
 * - 优雅退出（SIGTERM/SIGINT 安全关停）
 */
export class DeepCurrentsEngine {
  private parser = new Parser({ timeout: CONFIG.RSS_TIMEOUT_MS });
  private ai = new AIService();
  private db = new DBService();
  private breaker = new RSSCircuitBreaker({
    maxFailures: CONFIG.CB_MAX_FAILURES,
    cooldownMs: CONFIG.CB_COOLDOWN_MS,
  });
  private rssLimit = pLimit(CONFIG.RSS_CONCURRENCY);
  private cronTasks: ScheduledTask[] = [];

  public start() {
    logger.info("╔══════════════════════════════════════════════════════════╗");
    logger.info("║     🌊 DeepCurrents Engine v2.1 — 宏观情报引擎         ║");
    logger.info("║     Source Tier System | Threat Classification          ║");
    logger.info("║     News Clustering | Trending Detection                ║");
    logger.info("╚══════════════════════════════════════════════════════════╝");
    logger.info(`已加载 ${SOURCES.length} 个信息源（T1:${SOURCES.filter(s=>s.tier===1).length} T2:${SOURCES.filter(s=>s.tier===2).length} T3:${SOURCES.filter(s=>s.tier===3).length} T4:${SOURCES.filter(s=>s.tier===4).length}）`);

    this.cronTasks.push(
      cron.schedule(CONFIG.CRON_COLLECT, async () => {
        logger.info("[Collector] 正在扫描全球动态...");
        await this.collectData();
      }),

      cron.schedule(CONFIG.CRON_REPORT, async () => {
        logger.info("[Reporter] 正在合成每日深流研报...");
        await this.generateAndSendReport();
      }),

      cron.schedule(CONFIG.CRON_CLEANUP, () => {
        const cleaned = this.db.cleanup();
        if (cleaned > 0) logger.info(`[Cleanup] 清理了 ${cleaned} 条过期数据`);
      }),
    );

    // 优雅退出
    const shutdown = () => this.shutdown();
    process.on('SIGTERM', shutdown);
    process.on('SIGINT', shutdown);

    // 首次启动立即执行
    this.collectData();
  }

  private shutdown() {
    logger.info('收到退出信号，正在优雅关闭...');
    for (const task of this.cronTasks) task.stop();
    logger.info('所有定时任务已停止，再见。');
    process.exit(0);
  }

  public async collectData(): Promise<CollectResult> {
    let totalNew = 0;
    let totalSkipped = 0;
    let totalErrors = 0;
    const allHeadlines: Array<{ title: string; pubDate: Date; source: string; link?: string }> = [];

    const sortedSources = [...SOURCES].sort((a, b) => a.tier - b.tier);

    const tasks = sortedSources.map(source => this.rssLimit(async () => {
      if (this.breaker.isOnCooldown(source.name)) {
        totalSkipped++;
        return;
      }

      try {
        const feed = await this.parser.parseURL(source.url);
        let newCount = 0;

        for (const item of feed.items) {
          if (!item.link || !item.title) continue;

          if (this.db.hasNews(item.link)) continue;
          if (this.db.hasSimilarTitle(item.title)) continue;

          const threat = classifyThreat(item.title);

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

    if (allHeadlines.length > 0) {
      ingestHeadlines(allHeadlines);
    }

    const spikes = detectSpikes();
    if (spikes.length > 0) {
      logger.info(`[Trending] 检测到 ${spikes.length} 个飙升关键词`);
      for (const spike of spikes.slice(0, 3)) {
        logger.info(`  📈 "${spike.term}" — ${spike.count} mentions, ${spike.uniqueSources} sources`);
      }
    }

    const breakerSummary = this.breaker.getSummary();
    const dbStats = this.db.getStats();
    logger.info(`[采集完成] 新增 ${totalNew} | 跳过 ${totalSkipped} | 错误 ${totalErrors} | 熔断 ${breakerSummary.onCooldown} | 趋势词 ${getTrackedTermCount()}`);
    logger.info(`[数据库] 总量 ${dbStats.total} | 待报告 ${dbStats.unreported} | 威胁分布: ${JSON.stringify(dbStats.byThreat)}`);

    return { newItems: totalNew, skippedSources: totalSkipped, errors: totalErrors, spikeCount: spikes.length };
  }

  /**
   * 纯研报生成（不推送、不标记），返回研报及元数据。
   * 供 CLI 和 cron 共同使用。AI 调用失败时抛出异常。
   */
  public async generateReport(): Promise<ReportResult | null> {
    const unreportedNews = this.db.getUnreportedNews();
    if (unreportedNews.length === 0) {
      logger.info("[Reporter] 无新数据，跳过报告生成。");
      return null;
    }

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

    const spikes = detectSpikes();
    const report = await this.ai.generateDailyReport(unreportedNews, clusters, spikes);

    return {
      report,
      newsIds: unreportedNews.map(n => n.id),
      newsCount: unreportedNews.length,
      clusterCount: clusters.length,
    };
  }

  /** 推送研报到已配置的通知渠道（飞书/Telegram），各自带指数退避重试。 */
  public async deliverReport(report: DailyReport, newsCount: number, clusterCount: number): Promise<void> {
    await Promise.allSettled([
      retryWithBackoff(() => this.sendToFeishu(report, newsCount, clusterCount), 'Feishu'),
      retryWithBackoff(() => this.sendToTelegram(report), 'Telegram'),
    ]);
  }

  /** 标记新闻为已报告。 */
  public markNewsAsReported(ids: string[]): void {
    this.db.markAsReported(ids);
  }

  /**
   * 生成 + 投递 + 标记（供 cron 调度直接使用的便捷方法）。
   * 内部做 try/catch，保证不会让定时任务崩溃。
   */
  public async generateAndSendReport(): Promise<DailyReport | null> {
    try {
      const result = await this.generateReport();
      if (!result) return null;

      await this.deliverReport(result.report, result.newsCount, result.clusterCount);
      this.markNewsAsReported(result.newsIds);
      logger.info("✅ DeepCurrents 每日研报投递成功。");
      return result.report;
    } catch (e: any) {
      logger.error(`研报生成/投递失败: ${e.message}`);
      return null;
    }
  }

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

    if (report.riskAssessment) {
      mdContent += `\n**⚠️ 风险评估 | Risk Assessment**\n${report.riskAssessment}\n`;
    }
    
    mdContent += `\n--- \n*DeepCurrents Intelligence (v2.1) | 样本源: ${newsCount} 条 → ${clusterCount} 事件 | ${report.date}*`;

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

// 仅在被直接运行时启动常驻引擎，被 import 时（如 run-report）不启动
if (require.main === module) {
  new DeepCurrentsEngine().start();
}
