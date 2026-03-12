import Parser from 'rss-parser';
import axios from 'axios';
import * as dotenv from 'dotenv';
import pino from 'pino';
import { SOURCES, getSourceTier, getSourcePropagandaRisk, resolveSourceUrl } from './config/sources';
import { classifyThreat, THREAT_LABELS } from './services/classifier';
import { RSSCircuitBreaker } from './services/circuit-breaker';
import { ingestHeadlines, detectSpikes, getTrackedTermCount, resetTrendingState } from './services/trending';
import { clusterNews, NewsItemForClustering, generateClusterContext } from './services/clustering';
import { getMarketPrice } from './utils/market-data';

import { DBService, NewsRecord } from './services/db.service';
import { AIService } from './services/ai.service';
import { PredictionScorer } from './services/scorer';

dotenv.config();

const logger = pino({ 
  name: 'DeepCurrents-Tester', 
  level: 'info', 
  transport: { target: 'pino-pretty' } 
});

export class TestSuite {
  private parser = new Parser({ timeout: 10000 });

  /**
   * 测试 RSS 源联通性（增强版：含分级和熔断器）
   */
  public async testRSS() {
    logger.info("--- 开始测试 RSS 信息源 ---");
    logger.info(`已配置 ${SOURCES.length} 个源 (T1:${SOURCES.filter(s=>s.tier===1).length} T2:${SOURCES.filter(s=>s.tier===2).length} T3:${SOURCES.filter(s=>s.tier===3).length} T4:${SOURCES.filter(s=>s.tier===4).length})`);

    const breaker = new RSSCircuitBreaker({ maxFailures: 2, cooldownMs: 60000 });
    const results = { passed: 0, failed: 0, cooldown: 0 };

    for (const source of SOURCES) {
      const url = resolveSourceUrl(source);
      const typeLabel = source.isRssHub ? '[RSSHub]' : '[RSS]';

      if (breaker.isOnCooldown(source.name)) {
        logger.warn(`⏸️ ${typeLabel} T${source.tier} ${source.name}: 已熔断，跳过`);
        results.cooldown++;
        continue;
      }
      try {
        const feed = await this.parser.parseURL(url);
        breaker.recordSuccess(source.name);
        const riskLabel = getSourcePropagandaRisk(source.name) !== 'low' 
          ? ` ⚠️ 风险:${getSourcePropagandaRisk(source.name)}` : '';
        logger.info(`✅ ${typeLabel} T${source.tier} ${source.name}: ${feed.items.length} 条新闻${riskLabel}`);
        results.passed++;
      } catch (e: any) {
        breaker.recordFailure(source.name);
        logger.error(`❌ ${typeLabel} T${source.tier} ${source.name} 失败: ${e.message}`);
        results.failed++;
      }
    }
    
    const summary = breaker.getSummary();
    logger.info(`--- RSS 测试报告 ---`);
    logger.info(`总计: ${SOURCES.length} | 通过: ${results.passed} | 失败: ${results.failed} | 熔断跳过: ${results.cooldown}`);
    logger.info(`[熔断器] 跟踪: ${summary.totalSources} | 冷却中: ${summary.onCooldown}`);
  }

  /**
   * 测试威胁分类器
   */
  public async testClassifier() {
    logger.info("--- 开始测试威胁分类器 ---");

    const testCases = [
      { title: "Russia declares war on neighboring country", expected: 'critical' },
      { title: "Nuclear meltdown fears at power plant in Japan", expected: 'critical' },
      { title: "US strikes on Iran military targets", expected: 'critical' },       // 复合升级规则
      { title: "Major earthquake hits Turkey, hundreds dead", expected: 'high' },
      { title: "NATO sanctions imposed on Russia over conflict", expected: 'high' },
      { title: "Massive protests erupt in major cities", expected: 'medium' },
      { title: "Federal Reserve signals interest rate hike", expected: 'medium' },
      { title: "US-China trade deal negotiations resume", expected: 'low' },
      { title: "Celebrity wedding makes headlines", expected: 'info' },               // 排除规则
      { title: "Tech startup launches new productivity app", expected: 'info' },
    ];

    let passed = 0;
    for (const tc of testCases) {
      const result = classifyThreat(tc.title);
      const status = result.level === tc.expected ? '✅' : '❌';
      if (result.level === tc.expected) passed++;
      logger.info(`${status} "${tc.title.substring(0, 50)}..." → ${THREAT_LABELS[result.level]} (${result.category}) [期望: ${tc.expected}]`);
    }
    logger.info(`分类器准确率: ${passed}/${testCases.length} (${((passed/testCases.length)*100).toFixed(0)}%)`);
  }

  /**
   * 测试新闻聚类
   */
  public async testClustering() {
    logger.info("--- 开始测试新闻聚类 ---");

    const mockItems: NewsItemForClustering[] = [
      { id: '1', title: 'Federal Reserve raises interest rates by 0.25%', url: 'http://a.com', content: '', source: 'Reuters', sourceTier: 1, timestamp: new Date().toISOString(), threat: classifyThreat('Federal Reserve raises interest rates by 0.25%') },
      { id: '2', title: 'Fed hikes rates by quarter point, signals more increases', url: 'http://b.com', content: '', source: 'Bloomberg', sourceTier: 1, timestamp: new Date().toISOString(), threat: classifyThreat('Fed hikes rates by quarter point, signals more increases') },
      { id: '3', title: 'Interest rate increase by Federal Reserve impacts markets', url: 'http://c.com', content: '', source: 'CNBC', sourceTier: 2, timestamp: new Date().toISOString(), threat: classifyThreat('Interest rate increase by Federal Reserve impacts markets') },
      { id: '4', title: 'Russia launches military operation in Ukraine border', url: 'http://d.com', content: '', source: 'AP News', sourceTier: 1, timestamp: new Date().toISOString(), threat: classifyThreat('Russia launches military operation in Ukraine border') },
      { id: '5', title: 'Military offensive by Russia near Ukraine escalates', url: 'http://e.com', content: '', source: 'BBC World', sourceTier: 2, timestamp: new Date().toISOString(), threat: classifyThreat('Military offensive by Russia near Ukraine escalates') },
      { id: '6', title: 'Apple announces new iPhone model at WWDC', url: 'http://f.com', content: '', source: 'The Verge', sourceTier: 4, timestamp: new Date().toISOString(), threat: classifyThreat('Apple announces new iPhone model at WWDC') },
    ];

    const clusters = clusterNews(mockItems);
    logger.info(`${mockItems.length} 条新闻 → ${clusters.length} 个聚类`);

    for (const cluster of clusters) {
      const threatTag = THREAT_LABELS[cluster.threat.level];
      logger.info(`  📦 ${threatTag} "${cluster.primaryTitle}" (${cluster.sourceCount} sources via ${cluster.primarySource})`);
    }

    const clusterCtx = generateClusterContext(clusters);
    if (clusterCtx) {
      logger.info(`聚类上下文:\n${clusterCtx}`);
    }
  }

  /**
   * 测试趋势关键词检测
   */
  public async testTrending() {
    logger.info("--- 开始测试趋势关键词检测 ---");

    resetTrendingState();

    // 模拟灌入标题数据
    const mockHeadlines = [
      // 模拟 "iran" 大量出现
      { title: 'US launches strike on Iran military targets', pubDate: new Date(), source: 'Reuters' },
      { title: 'Iran retaliates with missile launches', pubDate: new Date(), source: 'AP News' },
      { title: 'Iran diplomatic channels closed after attack', pubDate: new Date(), source: 'BBC World' },
      { title: 'Iran crisis escalates as forces mobilize', pubDate: new Date(), source: 'Al Jazeera' },
      { title: 'Iran announces full military mobilization', pubDate: new Date(), source: 'Bloomberg' },
      // 正常频率词
      { title: 'Markets react to new economic data', pubDate: new Date(), source: 'CNBC' },
      { title: 'Global GDP growth forecasts revised', pubDate: new Date(), source: 'Financial Times' },
    ];

    ingestHeadlines(mockHeadlines);
    const spikes = detectSpikes({ minSpikeCount: 3, spikeMultiplier: 2 });

    logger.info(`跟踪关键词总数: ${getTrackedTermCount()}`);
    logger.info(`检测到 ${spikes.length} 个飙升关键词`);
    for (const spike of spikes) {
      logger.info(`  📈 "${spike.term}": ${spike.count} mentions, ${spike.uniqueSources} sources`);
    }
  }

  /**
   * 测试 LLM (AI) 联通性与格式返回
   */
  public async testLLM() {
    logger.info("--- 开始测试 LLM (AI) 服务 ---");
    const apiUrl = process.env.AI_API_URL;
    const apiKey = process.env.AI_API_KEY;

    if (!apiUrl || !apiKey) {
      logger.error("❌ [AI] 未配置 AI_API_URL 或 AI_API_KEY");
      return;
    }

    try {
      const response = await axios.post(apiUrl, {
        model: process.env.AI_MODEL || "gpt-4o-mini",
        messages: [{ role: "user", content: "Say hello and return a JSON object with a 'status' field." }],
        response_format: { type: "json_object" }
      }, {
        headers: { 'Authorization': `Bearer ${apiKey}` },
        timeout: 15000
      });
      logger.info(`✅ [AI] Primary 响应成功: ${JSON.stringify(response.data.choices[0].message.content)}`);
    } catch (e: any) {
      logger.error(`❌ [AI] Primary 失败: ${e.message}`);
    }

    // 测试 fallback（如果配置了）
    const fallbackUrl = process.env.AI_FALLBACK_URL;
    const fallbackKey = process.env.AI_FALLBACK_KEY;
    if (fallbackUrl && fallbackKey) {
      try {
        const response = await axios.post(fallbackUrl, {
          model: process.env.AI_FALLBACK_MODEL || "gpt-4o-mini",
          messages: [{ role: "user", content: "Say hello." }],
        }, {
          headers: { 'Authorization': `Bearer ${fallbackKey}` },
          timeout: 15000
        });
        logger.info(`✅ [AI] Fallback 响应成功`);
      } catch (e: any) {
        logger.error(`❌ [AI] Fallback 失败: ${e.message}`);
      }
    } else {
      logger.warn("⚠️ [AI] 未配置 Fallback 提供商(AI_FALLBACK_URL / AI_FALLBACK_KEY)");
    }
  }

  /**
   * 测试飞书 Webhook
   */
  public async testFeishu() {
    logger.info("--- 开始测试飞书推送 ---");
    const webhookUrl = process.env.FEISHU_WEBHOOK;
    if (!webhookUrl) {
      logger.warn("⚠️ [Feishu] 未配置 FEISHU_WEBHOOK");
      return;
    }

    try {
      await axios.post(webhookUrl, {
        msg_type: "text",
        content: { text: "🌊 DeepCurrents v2.0 测试消息: 飞书推送联通性正常。\n含信源分级 | 威胁分类 | 聚类引擎 | 趋势检测" }
      });
      logger.info("✅ [Feishu] 测试消息已发送");
    } catch (e: any) {
      logger.error(`❌ [Feishu] 失败: ${e.message}`);
    }
  }

  /**
   * 测试 Telegram Bot
   */
  public async testTelegram() {
    logger.info("--- 开始测试 Telegram 推送 ---");
    const token = process.env.TELEGRAM_BOT_TOKEN;
    const chatId = process.env.TELEGRAM_CHAT_ID;

    if (!token || !chatId) {
      logger.warn("⚠️ [Telegram] 未配置 TELEGRAM_BOT_TOKEN 或 TELEGRAM_CHAT_ID");
      return;
    }

    try {
      const url = `https://api.telegram.org/bot${token}/sendMessage`;
      await axios.post(url, {
        chat_id: chatId,
        text: "🌊 *DeepCurrents v2.0* 测试消息\nTelegram 推送联通性正常。",
        parse_mode: "Markdown"
      });
      logger.info("✅ [Telegram] 测试消息已发送");
    } catch (e: any) {
      logger.error(`❌ [Telegram] 失败: ${e.message}`);
    }
  }

  /**
   * 测试市场数据获取功能
   */
  public async testMarketData() {
    logger.info("--- 开始测试市场数据获取功能 ---");
    const testSymbols = ['GC=F', 'CL=F', '^GSPC']; // 黄金, 原油, 标普500
    
    for (const symbol of testSymbols) {
      try {
        const data = await getMarketPrice(symbol);
        logger.info(`✅ [MarketData] ${symbol}: ${data.price} (${data.changePercent.toFixed(2)}%)`);
      } catch (e: any) {
        logger.error(`❌ [MarketData] ${symbol} 失败: ${e.message}`);
      }
    }
  }

  /**
   * 测试数据库预测记录与评分功能
   */
  public async testDatabasePredictions() {
    logger.info("--- 开始测试数据库预测与评分功能 ---");
    const db = new DBService('data/test-intel.db');
    
    const mockPrediction = {
      asset: 'GC=F',
      type: 'bullish' as const,
      reasoning: 'Inflation concerns rising.',
      price: 2500.50,
      timestamp: new Date().toISOString()
    };
    
    db.savePrediction(mockPrediction);
    logger.info("✅ 预测记录已保存");
    
    const pending = db.getPendingPredictions();
    if (pending.length > 0) {
      const p = pending[0];
      logger.info(`✅ 成功读取到待评分记录: ${p.asset_symbol} @ ${p.base_price}`);
      
      db.updatePredictionScore(p.id, 85, 2600.00);
      logger.info("✅ 评分已更新");
    } else {
      logger.error("❌ 未能读取到待评分记录");
    }
  }

  /**
   * 测试多智能体协作生成研报
   */
  public async testMultiAgentReport() {
    logger.info("--- 开始测试多智能体协作研报生成 ---");
    const ai = new AIService();
    const mockNews: NewsRecord[] = [
      { id: '1', url: 'http://a.com', title: 'Global gold prices surge as geopolitical tensions rise in Middle East', content: 'Gold futures jumped 2% today as investors seek safe haven assets amid escalating conflicts...', category: 'Reuters', tier: 1, threatLevel: 'high', timestamp: new Date().toISOString() },
      { id: '2', url: 'http://b.com', title: 'Oil prices fluctuate following OPEC meeting', content: 'Oil prices saw volatility today as OPEC members discussed production quotas for the next quarter...', category: 'Bloomberg', tier: 1, threatLevel: 'medium', timestamp: new Date().toISOString() }
    ];

    try {
      const report = await ai.generateDailyReport(mockNews);
      logger.info(`✅ 研报生成成功! 日期: ${report.date}`);
      logger.info(`执行摘要: ${report.executiveSummary.substring(0, 100)}...`);
      logger.info(`投资趋势: ${JSON.stringify(report.investmentTrends)}`);
    } catch (e: any) {
      logger.error(`❌ 研报生成失败: ${e.message}`);
    }
  }

  /**
   * 测试自动评分逻辑
   */
  public async testScoringLogic() {
    logger.info("--- 开始测试自动评分逻辑 ---");
    const scorer = new PredictionScorer();
    await scorer.runScoringTask();
    logger.info("✅ 评分逻辑测试运行完成");
  }

  public async runAll() {
    await this.testRSS();
    console.log("\n");
    await this.testClassifier();
    console.log("\n");
    await this.testClustering();
    console.log("\n");
    await this.testTrending();
    console.log("\n");
    await this.testLLM();
    console.log("\n");
    await this.testMarketData();
    console.log("\n");
    await this.testDatabasePredictions();
    console.log("\n");
    await this.testFeishu();
    console.log("\n");
    await this.testTelegram();
    logger.info("--- 全部集成测试完成 ---");
    process.exit(0);
  }
}

// 可用测试类别映射
const TEST_CATEGORIES: Record<string, (tester: TestSuite) => Promise<void>> = {
  rss: (t) => t.testRSS(),
  classifier: (t) => t.testClassifier(),
  clustering: (t) => t.testClustering(),
  trending: (t) => t.testTrending(),
  llm: (t) => t.testLLM(),
  'market-data': (t) => t.testMarketData(),
  'db-predictions': (t) => t.testDatabasePredictions(),
  'multi-agent-report': (t) => t.testMultiAgentReport(),
  'scoring-task': (t) => t.testScoringLogic(),
  feishu: (t) => t.testFeishu(),
  telegram: (t) => t.testTelegram(),
};

const AVAILABLE_CATEGORIES = Object.keys(TEST_CATEGORIES);

function printUsage() {
  console.log(`
用法: npx ts-node src/test-tools.ts [类别...]

可选类别: ${AVAILABLE_CATEGORIES.join(', ')}

示例:
  npx ts-node src/test-tools.ts              # 运行全部测试
  npx ts-node src/test-tools.ts rss          # 仅测试 RSS
  npx ts-node src/test-tools.ts classifier   # 仅测试威胁分类器
  npx ts-node src/test-tools.ts clustering   # 仅测试新闻聚类
  npx ts-node src/test-tools.ts trending     # 仅测试趋势检测
  npx ts-node src/test-tools.ts rss llm      # 测试 RSS 和 LLM
`);
}

// 脚本直接运行逻辑
if (require.main === module) {
  const args = process.argv.slice(2).map((a) => a.toLowerCase());

  if (args.includes('--help') || args.includes('-h')) {
    printUsage();
    process.exit(0);
  }

  const tester = new TestSuite();

  if (args.length === 0) {
    tester.runAll();
  } else {
    const invalid = args.filter((a) => !AVAILABLE_CATEGORIES.includes(a));
    if (invalid.length > 0) {
      logger.error(`未知的测试类别: ${invalid.join(', ')}`);
      printUsage();
      process.exit(1);
    }

    (async () => {
      for (const category of args) {
        await TEST_CATEGORIES[category]!(tester);
        console.log('\n');
      }
      logger.info('--- 指定测试完成 ---');
      process.exit(0);
    })();
  }
}
