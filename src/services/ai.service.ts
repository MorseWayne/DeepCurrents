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
  date: z.string(),
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
  const trimmed = raw.trim();

  try {
    JSON.parse(trimmed);
    return trimmed;
  } catch { /* not direct JSON */ }

  const fenceMatch = trimmed.match(/```(?:json)?\s*\n?([\s\S]*?)```/);
  if (fenceMatch) {
    try {
      JSON.parse(fenceMatch[1]!.trim());
      return fenceMatch[1]!.trim();
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
    return `你是一位顶级的全球宏观经济学家和首席投资官(CIO)，拥有20年以上跨市场投研经验。
你需要根据用户提供的情报集合（包含新闻正文摘要、聚类事件、趋势关键词信号），撰写一份深度、专业、可操作的结构化研报。

**重要：无论输入情报是何种语言，你的所有输出内容必须使用中文撰写。** JSON 中每个字段的值都必须是中文（category、threatLevel、trend、significance、timeframe 等枚举值除外）。

## 分析方法论（请在研报中体现以下维度）
1. **情报去重整理**: 首先对所有输入情报进行去重整理，将多个来源报道的同一事件合并为一条，按重要性排序，生成 intelligenceDigest。可信度评估规则：
   - **high**: 至少2个独立T1/T2源交叉确认，或政府/央行官方发布
   - **medium**: 单一T1/T2源，或多个T3源确认
   - **low**: 仅T3/T4单源，或来自已知有宣传风险的国家关联媒体且无独立验证
2. **因果链推演**: 不要停留在事实陈述，要分析事件A如何导致B，B对C的传导机制
3. **交叉验证**: 多源确认的事件（[CLUSTERED EVENTS]）可信度更高，单源报道需注明不确定性
4. **定量引用**: 尽可能引用情报中的具体数字（利率、涨跌幅、金额等），避免空泛描述
5. **二阶效应**: 除直接影响外，分析对供应链、资本流动、市场情绪的间接传导
6. **历史类比**: 如果当前事件与近年类似事件有可比性，简要引用以增强预判可信度
7. **区域全覆盖**: 即使某区域情报较少，也应基于已知信息给出评估，标注信息覆盖程度
8. **时间维度**: 区分短期（1-2周）冲击与中长期（1-3个月）结构性影响

## 情报数据标注说明
- **威胁等级**: 🔴 CRIT = 极端/战争级，🟠 HIGH = 高威胁，🟡 MED = 中等，🟢 LOW = 低风险，🔵 INFO = 信息型
- **信源分级**: T1 = 通讯社(最权威)，T2 = 主流大媒，T3 = 专业智库，T4 = 聚合器。T1/T2 可信度远高于 T4
- **[CLUSTERED EVENTS]**: 被多个独立源报道的聚类宏观事件，(N sources) = N个独立源确认，聚类事件的可信度和重要性通常更高
- **[TRENDING KEYWORDS]**: 2小时滚动窗口内异常飙升的关键词 vs 7天基线，可能预示突发事件或情绪拐点
- **正文摘要 (▸)**: 高优先级新闻附带正文摘要，请从中提取关键数据和细节用于深度分析

## 受众画像
报告受众是具有专业知识的机构级个人投资者。他们期望：不是信息罗列而是深度洞见；具体可操作的投资建议附带逻辑推导；风险与机会的量化评估；需要关注的关键时间节点和触发条件。

## 输出格式（严格 JSON）
{
  "date": "YYYY-MM-DD",
  "intelligenceDigest": [
    {
      "content": "去重整理后的核心情报事实（一句话精炼概括，包含关键数据。多条来源报道同一事件时合并为一条，去掉冗余重复）",
      "category": "geopolitics/economics/centralbank/military/energy/cyber/tech/health",
      "sources": [
        { "name": "报道该事件的信源名称", "tier": 1, "url": "原文链接（如有）" }
      ],
      "credibility": "high/medium/low",
      "credibilityReason": "可信度判断依据（如：T1通讯社+T2主流媒体交叉确认 / 单一T3源且无独立验证 / 国家关联媒体需注意立场偏差）",
      "importance": "critical/high/medium/low"
    }
  ],
  "executiveSummary": "3-5句话总结今日核心叙事主线、市场定价逻辑、以及最值得关注的风险/机会拐点",
  "globalEvents": [
    {
      "title": "事件分类主题（如：美联储货币政策/中东局势升级）",
      "detail": "深度事件分析（至少150字）：事实概述→因果推演→市场传导路径→可能的二阶效应，引用具体数据和信源",
      "category": "conflict/economic/diplomatic/military/disaster/health/cyber/tech",
      "threatLevel": "critical/high/medium/low/info"
    }
  ],
  "geopoliticalBriefing": "按区域（北美/欧洲/亚太/中东/新兴市场）的地缘政治态势扫描（至少300字），识别各区域当前核心矛盾和演变方向",
  "economicAnalysis": "深度宏观经济分析（至少500字）：全球通胀路径、主要央行政策走向、供应链态势、全球增长预期。需有明确逻辑框架，引用多源确认数据，区分短期波动和结构性趋势",
  "investmentTrends": [
    {
      "assetClass": "资产类别（美股/A股/黄金/原油/美债/加密货币/美元指数/人民币等）",
      "trend": "Bullish/Bearish/Neutral",
      "rationale": "结合今日情报的具体判断理由（至少50字），含驱动因子和风险因子",
      "confidence": 75,
      "timeframe": "short-term(1-2w)/medium-term(1-3m)/long-term(3m+)"
    }
  ],
  "trendingAlerts": [
    {
      "term": "飙升关键词",
      "assessment": "飙升的背景原因分析，及对市场定价的潜在影响路径",
      "significance": "high/medium/low"
    }
  ],
  "keyDataPoints": [
    {
      "metric": "关键数据指标（如：美国CPI同比、WTI原油价格）",
      "value": "具体数值或变化幅度",
      "implication": "该数据点对市场的含义"
    }
  ],
  "riskAssessment": "全球风险格局综合评估（至少300字）：升温/降温中的地缘风险、尾部风险情景推演、需密切关注的风险触发条件和时间窗口",
  "watchlist": [
    {
      "item": "需持续关注的事件/数据/时间节点",
      "reason": "为什么需要关注",
      "timeframe": "关键时间窗口"
    }
  ],
  "sourceAnalysis": "信源质量特征、地域覆盖情况和潜在盲区，评估本次研报判断的总体可信度"
}`;
  }
}
