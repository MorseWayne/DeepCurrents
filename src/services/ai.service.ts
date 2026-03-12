import axios from 'axios';
import pLimit from 'p-limit';
import { z } from 'zod';
import { NewsRecord, DBService } from './db.service';
import { ClusteredEvent, generateClusterContext } from './clustering';
import { generateTrendingContext, TrendingSpike } from './trending';
import { THREAT_LABELS } from './classifier';
import { CONFIG } from '../config/settings';
import { getLogger } from '../utils/logger';
import { getMarketPrice, MarketPrice } from '../utils/market-data';
import { 
  MACRO_ANALYST_PROMPT, 
  SENTIMENT_ANALYST_PROMPT, 
  MARKET_STRATEGIST_PROMPT 
} from './prompts';

const logger = getLogger('ai-service');

// ── 研报输出结构定义 (Zod Schema) ──

const GlobalEventSchema = z.object({
  title: z.string(),
  detail: z.string(),
  category: z.string().optional(),
  threatLevel: z.enum(['critical', 'high', 'medium', 'low', 'info']).optional(),
});

const InvestmentTrendSchema = z.object({
  assetClass: z.string(),
  trend: z.enum(['Bullish', 'Bearish', 'Neutral']),
  rationale: z.string(),
  confidence: z.preprocess(v => (typeof v === 'string' ? Number(v) : v), z.number().min(0).max(100)).optional(),
  timeframe: z.string().optional(),
});

const TrendingAlertSchema = z.object({
  term: z.string(),
  assessment: z.string(),
  significance: z.enum(['high', 'medium', 'low']),
});

const KeyDataPointSchema = z.object({
  metric: z.string(),
  value: z.string(),
  implication: z.string(),
});

const WatchlistItemSchema = z.object({
  item: z.string(),
  reason: z.string(),
  timeframe: z.string().optional(),
});

const IntelSourceSchema = z.object({
  name: z.string(),
  tier: z.number().min(1).max(4),
  url: z.string().optional(),
});

const IntelligenceItemSchema = z.object({
  content: z.string(),
  category: z.string(),
  sources: z.array(IntelSourceSchema),
  credibility: z.enum(['high', 'medium', 'low']),
  credibilityReason: z.string(),
  importance: z.enum(['critical', 'high', 'medium', 'low']),
});

const DailyReportSchema = z.object({
  date: z.preprocess(v => (typeof v === 'number' ? String(v) : v), z.string()),
  intelligenceDigest: z.array(IntelligenceItemSchema),
  executiveSummary: z.string(),
  globalEvents: z.array(GlobalEventSchema),
  geopoliticalBriefing: z.string().optional(),
  economicAnalysis: z.string(),
  investmentTrends: z.array(InvestmentTrendSchema),
  trendingAlerts: z.array(TrendingAlertSchema).optional(),
  keyDataPoints: z.array(KeyDataPointSchema).optional(),
  riskAssessment: z.string().optional(),
  watchlist: z.array(WatchlistItemSchema).optional(),
  sourceAnalysis: z.string().optional(),
});

export type DailyReport = z.infer<typeof DailyReportSchema>;

// ── Token 预算管理 ──

function estimateTokens(text: string): number {
  return Math.ceil(text.length / 3.5);
}

function truncateToTokenBudget(text: string, maxTokens: number): string {
  const maxChars = Math.floor(maxTokens * 3.5);
  if (text.length <= maxChars) return text;
  const truncated = text.substring(0, maxChars);
  const lastNewline = truncated.lastIndexOf('\n');
  if (lastNewline > maxChars * 0.8) return truncated.substring(0, lastNewline);
  return truncated;
}

// ── JSON 提取 (容错) ──

function extractJSON(raw: string): string {
  let trimmed = raw.replace(/[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]/g, '').trim();
  try { JSON.parse(trimmed); return trimmed; } catch { /* not direct JSON */ }
  const fenceMatch = trimmed.match(/```(?:json)?\s*\n?([\s\S]*?)```/);
  if (fenceMatch) {
    const candidate = fenceMatch[1]!.trim();
    try { JSON.parse(candidate); return candidate; } catch { /* fence content not valid */ }
  }
  const first = trimmed.indexOf('{');
  const last = trimmed.lastIndexOf('}');
  if (first !== -1 && last > first) {
    const candidate = trimmed.substring(first, last + 1);
    try { JSON.parse(candidate); return candidate; } catch { /* brace extraction failed */ }
  }
  return trimmed;
}

// ── AI 提供商配置 ──

interface AIProvider {
  name: string;
  envUrl: string;
  envKey: string;
  envModel: string;
  defaultModel: string;
}

const AI_PROVIDERS: AIProvider[] = [
  { name: 'Primary', envUrl: 'AI_API_URL', envKey: 'AI_API_KEY', envModel: 'AI_MODEL', defaultModel: 'gpt-4o' },
  { name: 'Fallback', envUrl: 'AI_FALLBACK_URL', envKey: 'AI_FALLBACK_KEY', envModel: 'AI_FALLBACK_MODEL', defaultModel: 'gpt-4o-mini' },
];

export class AIService {
  private limit = pLimit(1);
  private db = new DBService(); // 默认实例化以保存预测

  public async generateDailyReport(
    newsList: NewsRecord[],
    clusters?: ClusteredEvent[],
    trendingSpikes?: TrendingSpike[]
  ): Promise<DailyReport> {
    return this.limit(async () => {
      const totalBudget = CONFIG.AI_MAX_CONTEXT_TOKENS;
      const newsBudget = Math.floor(totalBudget * 0.50);
      const clusterBudget = Math.floor(totalBudget * 0.15);
      const trendingBudget = Math.floor(totalBudget * 0.10);

      const rawContextParts: string[] = [];
      rawContextParts.push(this.buildNewsContext(newsList, newsBudget));
      if (clusters && clusters.length > 0) {
        const clusterCtx = generateClusterContext(clusters);
        if (clusterCtx) rawContextParts.push('\n' + truncateToTokenBudget(clusterCtx, clusterBudget));
      }
      const trendingCtx = generateTrendingContext();
      if (trendingCtx) rawContextParts.push('\n' + truncateToTokenBudget(trendingCtx, trendingBudget));

      const rawContext = rawContextParts.join('\n');

      // ── 多智能体并行流程 ──
      logger.info('[AIService] 启动多智能体并发推理...');
      
      const [macroOutput, sentimentOutput, marketPrices] = await Promise.all([
        this.callAgent('MacroAnalyst', MACRO_ANALYST_PROMPT, rawContext),
        this.callAgent('SentimentAnalyst', SENTIMENT_ANALYST_PROMPT, rawContext),
        this.fetchMarketPrices(['GC=F', 'CL=F', '^GSPC'])
      ]);

      // ── 资产行情数据上下文 ──
      const priceLines = ['[REAL-TIME MARKET DATA]'];
      for (const p of marketPrices) {
        priceLines.push(`- ${p.symbol}: ${p.price} (Change: ${p.changePercent.toFixed(2)}%)`);
      }
      const marketPriceContext = priceLines.join('\n');

      // ── 首席战略官 (Market Strategist) 整合 ──
      logger.info('[AIService] 启动首席战略官整合研报...');
      const finalStrategistInput = `
[RAW INTEL CONTEXT]
${rawContext}

[MACRO ANALYST OUTPUT]
\`\`\`json
${macroOutput}
\`\`\`

[SENTIMENT ANALYST OUTPUT]
\`\`\`json
${sentimentOutput}
\`\`\`

[MARKET DATA]
${marketPriceContext}

请根据以上宏观背景、情绪分析及真实行情，撰写最终机构级研报。请特别注意行情走势与逻辑的匹配度。
`;

      const finalReportRaw = await this.callAgent('MarketStrategist', MARKET_STRATEGIST_PROMPT, finalStrategistInput);
      logger.info(`[AIService] MarketStrategist 原始输出长度: ${finalReportRaw.length}`);
      logger.info(`[AIService] MarketStrategist 原始输出预览: ${finalReportRaw.substring(0, 500)}`);
      const extractedJSON = extractJSON(finalReportRaw);
      const parsed = JSON.parse(extractedJSON);
      
      try {
        const parsedReport = DailyReportSchema.parse(parsed);
        // ── 自动保存 AI 的预测以便后续评分 ──
        this.persistPredictions(parsedReport, marketPrices);
        return parsedReport;
      } catch (e: any) {
        logger.error(`[AIService] Zod 验证失败: ${e.message}`);
        logger.error(`[AIService] 原始解析内容: ${JSON.stringify(parsed)}`);
        throw e;
      }
    });
  }

  /**
   * 调用智能体（含回退逻辑）
   */
  private async callAgent(agentName: string, systemPrompt: string, userContent: string): Promise<string> {
    for (const provider of AI_PROVIDERS) {
      const apiUrl = process.env[provider.envUrl];
      const apiKey = process.env[provider.envKey];
      if (!apiUrl || !apiKey) continue;

      try {
        const model = process.env[provider.envModel] || provider.defaultModel;
        const response = await axios.post(apiUrl, {
          model,
          messages: [
            { role: "system", content: systemPrompt },
            { role: "user", content: userContent }
          ],
          response_format: { type: "json_object" }
        }, {
          headers: { 'Authorization': `Bearer ${apiKey}` },
          timeout: CONFIG.AI_TIMEOUT_MS,
        });

        const raw = response.data.choices[0].message.content;
        logger.info(`[AIService] ${agentName} 调用 (${provider.name}) 成功`);
        return raw;
      } catch (error: any) {
        logger.warn(`[AIService] ${agentName} 调用 (${provider.name}) 失败: ${error.message}`);
        continue;
      }
    }
    throw new Error(`${agentName} 任务失败`);
  }

  /**
   * 获取市场行情
   */
  private async fetchMarketPrices(symbols: string[]): Promise<MarketPrice[]> {
    const results: MarketPrice[] = [];
    for (const s of symbols) {
      try {
        const p = await getMarketPrice(s);
        results.push(p);
      } catch (e: any) {
        logger.warn(`[AIService] 无法获取行情数据 ${s}: ${e.message}`);
      }
    }
    return results;
  }

  /**
   * 将研报中的预测信息持久化到数据库
   */
  private persistPredictions(report: DailyReport, prices: MarketPrice[]) {
    if (!report.investmentTrends) return;
    
    for (const trend of report.investmentTrends) {
      // 简单资产映射（模糊匹配，生产环境应通过更严谨的映射表）
      const priceData = prices.find(p => 
        trend.assetClass.toLowerCase().includes(p.symbol.replace('=F', '').toLowerCase()) ||
        (p.symbol === '^GSPC' && trend.assetClass.toLowerCase().includes('stock'))
      );

      if (priceData) {
        this.db.savePrediction({
          asset: priceData.symbol,
          type: trend.trend.toLowerCase() as any,
          reasoning: trend.rationale,
          price: priceData.price,
          timestamp: new Date().toISOString()
        });
      }
    }
  }

  private buildNewsContext(newsList: NewsRecord[], tokenBudget: number): string {
    const lines: string[] = [];
    let usedTokens = 0;
    const EXCERPT_LEN_HIGH = 400;
    const EXCERPT_LEN_STD = 200;

    for (const n of newsList) {
      const threatLabel = n.threatLevel ? (THREAT_LABELS[n.threatLevel as keyof typeof THREAT_LABELS] || '') : '';
      const idx = lines.length + 1;
      const header = `[${idx}] ${threatLabel} ${n.title} (${n.category}, T${n.tier})`;
      
      const isHighPriority = (n.tier != null && n.tier <= 2) || ['critical', 'high'].includes(n.threatLevel || '');
      const hasContent = n.content && n.content.length > 80;

      let entry = header;
      if (hasContent) {
        const maxLen = isHighPriority ? EXCERPT_LEN_HIGH : EXCERPT_LEN_STD;
        const excerpt = n.content!.substring(0, maxLen).replace(/\s+/g, ' ').trim();
        entry += `\n  ▸ ${excerpt}`;
      }

      const entryTokens = estimateTokens(entry);
      if (usedTokens + entryTokens > tokenBudget) {
        const hTokens = estimateTokens(header);
        if (usedTokens + hTokens > tokenBudget) break;
        lines.push(header);
        usedTokens += hTokens;
      } else {
        lines.push(entry);
        usedTokens += entryTokens;
      }
    }
    return lines.join('\n');
  }
}
