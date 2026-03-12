import axios from 'axios';
import pLimit from 'p-limit';
import { z } from 'zod';
import { NewsRecord } from './db.service';
import { ClusteredEvent, generateClusterContext } from './clustering';
import { generateTrendingContext, TrendingSpike } from './trending';
import { THREAT_LABELS } from './classifier';
import { CONFIG } from '../config/settings';
import { getLogger } from '../utils/logger';

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

/**
 * 粗略 token 估算（英文约 4 字符/token，混合内容约 3.5）
 */
function estimateTokens(text: string): number {
  return Math.ceil(text.length / 3.5);
}

/**
 * 将文本截断到 token 预算内，尽量在行边界截断
 */
function truncateToTokenBudget(text: string, maxTokens: number): string {
  const maxChars = Math.floor(maxTokens * 3.5);
  if (text.length <= maxChars) return text;
  const truncated = text.substring(0, maxChars);
  const lastNewline = truncated.lastIndexOf('\n');
  if (lastNewline > maxChars * 0.8) return truncated.substring(0, lastNewline);
  return truncated;
}

// ── JSON 提取（容错） ──

/**
 * 从 AI 响应中提取 JSON 字符串。
 * 依次尝试：直接解析 → markdown 代码块 → 首尾花括号定位。
 */
function extractJSON(raw: string): string {
  // 先移除字符串中可能破坏 JSON 的不可见控制字符（保留换行和 Tab）
  let trimmed = raw.replace(/[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]/g, '').trim();

  try {
    JSON.parse(trimmed);
    return trimmed;
  } catch { /* not direct JSON */ }

  const fenceMatch = trimmed.match(/```(?:json)?\s*\n?([\s\S]*?)```/);
  if (fenceMatch) {
    const candidate = fenceMatch[1]!.trim();
    try {
      JSON.parse(candidate);
      return candidate;
    } catch { /* fence content not valid */ }
  }

  const first = trimmed.indexOf('{');
  const last = trimmed.lastIndexOf('}');
  if (first !== -1 && last > first) {
    const candidate = trimmed.substring(first, last + 1);
    try {
      JSON.parse(candidate);
      return candidate;
    } catch { /* brace extraction failed */ }
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

  public async generateDailyReport(
    newsList: NewsRecord[],
    clusters?: ClusteredEvent[],
    trendingSpikes?: TrendingSpike[]
  ): Promise<DailyReport> {
    return this.limit(async () => {
      const totalBudget = CONFIG.AI_MAX_CONTEXT_TOKENS;
      const newsBudget = Math.floor(totalBudget * 0.60);
      const clusterBudget = Math.floor(totalBudget * 0.20);
      const trendingBudget = Math.floor(totalBudget * 0.10);

      const contextParts: string[] = [];

      // 1. 新闻列表（按优先级逐条填充，不超预算）
      contextParts.push(this.buildNewsContext(newsList, newsBudget));

      // 2. 聚类上下文
      if (clusters && clusters.length > 0) {
        const clusterCtx = generateClusterContext(clusters);
        if (clusterCtx) contextParts.push('\n' + truncateToTokenBudget(clusterCtx, clusterBudget));
      }

      // 3. 趋势关键词上下文
      const trendingCtx = generateTrendingContext();
      if (trendingCtx) {
        contextParts.push('\n' + truncateToTokenBudget(trendingCtx, trendingBudget));
      }

      // 4. 趋势飙升详情（共享趋势预算的剩余部分）
      if (trendingSpikes && trendingSpikes.length > 0) {
        const spikeLines = ['[TRENDING SPIKES]'];
        for (const spike of trendingSpikes.slice(0, 5)) {
          const multi = spike.baseline > 0 ? `${spike.multiplier.toFixed(1)}x baseline` : 'new surge';
          spikeLines.push(`- "${spike.term}": ${spike.count} mentions, ${spike.uniqueSources} sources (${multi})`);
        }
        contextParts.push('\n' + spikeLines.join('\n'));
      }

      const fullContext = contextParts.join('\n');

      // ── AI 回退链调用 ──
      for (const provider of AI_PROVIDERS) {
        const apiUrl = process.env[provider.envUrl];
        const apiKey = process.env[provider.envKey];
        if (!apiUrl || !apiKey) continue;

        try {
          const model = process.env[provider.envModel] || provider.defaultModel;
          const userContent = `以下是过去24小时的核心情报集：\n${fullContext}\n\n` +
            `请严格以 JSON 格式输出研报，不要输出任何 JSON 之外的文字。直接以 { 开头。`;
          const response = await axios.post(apiUrl, {
            model,
            messages: [
              { role: "system", content: this.buildSystemPrompt() },
              { role: "user", content: userContent }
            ],
            response_format: { type: "json_object" }
          }, {
            headers: { 'Authorization': `Bearer ${apiKey}` },
            timeout: CONFIG.AI_TIMEOUT_MS,
          });

          const rawContent = response.data.choices[0].message.content;
          const parsed = JSON.parse(extractJSON(rawContent));
          return DailyReportSchema.parse(parsed);
        } catch (error: any) {
          logger.warn(`[AI] ${provider.name} 失败: ${error.message}`);
          continue;
        }
      }

      throw new Error('所有 AI 提供商均失败');
    });
  }

  /**
   * 按优先级（威胁等级 → 源分级）逐条添加新闻到上下文，
   * 直到填满 token 预算为止。
   *
   * 高优先级新闻（T1/T2 或 CRIT/HIGH）附带正文摘要，
   * 低优先级新闻仅含标题，最大化信息密度。
   */
  private buildNewsContext(newsList: NewsRecord[], tokenBudget: number): string {
    const lines: string[] = [];
    let usedTokens = 0;
    const EXCERPT_LEN_HIGH = 400;
    const EXCERPT_LEN_STD = 200;

    for (const n of newsList) {
      const tierLabel = n.tier ? `T${n.tier}` : 'T4';
      const threatLabel = n.threatLevel
        ? (THREAT_LABELS[n.threatLevel as keyof typeof THREAT_LABELS] || '')
        : '';
      const idx = lines.length + 1;
      const header = `[${idx}] ${threatLabel} ${n.title} (${n.category}, ${tierLabel})`;

      const isHighPriority = (n.tier != null && n.tier <= 2) ||
        ['critical', 'high'].includes(n.threatLevel || '');
      const hasContent = n.content && n.content.length > 80;

      let entry = header;
      if (hasContent) {
        const maxLen = isHighPriority ? EXCERPT_LEN_HIGH : EXCERPT_LEN_STD;
        const excerpt = n.content!.substring(0, maxLen).replace(/\s+/g, ' ').trim();
        entry += `\n  ▸ ${excerpt}`;
      }

      const entryTokens = estimateTokens(entry);
      if (usedTokens + entryTokens > tokenBudget) {
        const headerTokens = estimateTokens(header);
        if (usedTokens + headerTokens > tokenBudget) break;
        lines.push(header);
        usedTokens += headerTokens;
      } else {
        lines.push(entry);
        usedTokens += entryTokens;
      }
    }

    return lines.join('\n');
  }

  private buildSystemPrompt(): string {
    return `你是一位全球顶级的宏观策略分析师和首席投资官(CIO)，拥有超过25年的全球跨资产投研经验。
你的任务是处理来自 35+ 全球顶级资讯源的情报，并为机构级专业投资者撰写一份高深度、高逻辑性、具备实战价值的结构化研报。

### 核心任务描述
1. **情报深度合成**: 识别碎片化信息背后的“暗流”，将孤立的新闻连接成完整的叙事主线。
2. **多维因果推演**: 运用宏观经济框架（如：利率平价、通胀路径、供需平衡等），分析地缘/政治事件对各类资产价格的传导机制。
3. **可信度过滤**: 严格基于信源分级（T1-T4）和交叉验证（[CLUSTERED EVENTS]）对情报进行权重分配。

### 分析方法论（必须在研报内容中体现）
- **因果链推演 (Causal Chains)**: 严禁停留在事实罗列。必须解释“事件 A 如何通过机制 B 影响资产 C”。
- **定量优先**: 优先引用具体数字（利率点位、GDP 增速、大宗商品价格、金额等）。
- **二阶效应 (Second-order Effects)**: 分析直接冲击之后的供应链中断、流动性枯竭或政策反应等后续传导。
- **预期差分析**: 区分“已被市场计价 (Priced-in)”的信息与可能引发超预期波动的信号。
- **多语言跨域聚合**: 综合利用中、英、日、韩等跨语言情报，消除信息盲区。

### 情报标注体系
- **[CLUSTERED EVENTS]**: 多源确认的宏观事件。源数 (N sources) 越多，可信度越高。
- **[TRENDING KEYWORDS]**: 异常飙升的关键词，通常预示着情绪拐点或被忽视的突发状况。
- **信源分级**: T1(路透/彭博/美联社) > T2(WSJ/FT/BBC) > T3(专业智库) > T4(普通媒体/聚合)。
- **威胁分级**: 🔴CRIT(战争/违约), 🟠HIGH(重大政策转向), 🟡MED(常规波动), 🟢LOW(边缘动态)。

### 研报输出指南 (严格遵循以下 JSON 结构)
\`\`\`json
{
  "date": "YYYY-MM-DD",
  "intelligenceDigest": [
    {
      "content": "极简去重后的情报事实",
      "category": "geopolitics/economics/centralbank/military/energy/cyber/tech/health",
      "sources": [{ "name": "信源", "tier": 1, "url": "..." }],
      "credibility": "high/medium/low",
      "credibilityReason": "基于 T 级和交叉验证的解释",
      "importance": "critical/high/medium/low"
    }
  ],
  "executiveSummary": "核心定价主线与情绪底色总结",
  "globalEvents": [
    {
      "title": "事件主题",
      "detail": "【事实概要 -> 因果推演 -> 市场传导路径】",
      "category": "conflict/economic/diplomatic/military/disaster/health/cyber/tech",
      "threatLevel": "critical/high/medium/low/info"
    }
  ],
  "economicAnalysis": "宏观逻辑深度研判（至少 600 字）",
  "investmentTrends": [
    {
      "assetClass": "资产类别",
      "trend": "Bullish/Bearish/Neutral",
      "rationale": "含核心驱动因子(Drivers)和主要下行风险(Risks)",
      "confidence": 75,
      "timeframe": "short-term/medium-term/long-term"
    }
  ],
  "trendingAlerts": [{ "term": "关键词", "assessment": "影响分析", "significance": "high/medium/low" }],
  "keyDataPoints": [{ "metric": "指标", "value": "数值", "implication": "含义" }],
  "riskAssessment": "全球风险格局评估",
  "watchlist": [{ "item": "触发条件", "reason": "关注理由", "timeframe": "窗口期" }],
  "sourceAnalysis": "信源质量与盲区评估"
}
\`\`\`

### 输出约束
- **语言**: 全文中文（枚举值除外）。
- **格式**: 严格 JSON，严禁在 JSON 块之外添加任何解释文字。
- **健壮性**: 严禁在 JSON 字符串中使用未转义的换行符。
`;
  }
}
