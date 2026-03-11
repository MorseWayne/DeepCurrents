import axios from 'axios';
import pLimit from 'p-limit';
import { z } from 'zod';
import { NewsRecord } from './db.service';
import { ClusteredEvent, generateClusterContext } from './clustering';
import { generateTrendingContext, TrendingSpike, detectSpikes } from './trending';
import { THREAT_LABELS } from './classifier';

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
  confidence: z.number().min(0).max(100).optional(),
});

const TrendingAlertSchema = z.object({
  term: z.string(),
  assessment: z.string(),
  significance: z.enum(['high', 'medium', 'low']),
});

const DailyReportSchema = z.object({
  date: z.string(),
  executiveSummary: z.string(),
  globalEvents: z.array(GlobalEventSchema),
  economicAnalysis: z.string(),
  investmentTrends: z.array(InvestmentTrendSchema),
  trendingAlerts: z.array(TrendingAlertSchema).optional(),
  riskAssessment: z.string().optional(),
  sourceAnalysis: z.string().optional(),
});

export type DailyReport = z.infer<typeof DailyReportSchema>;

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

  /**
   * 生成每日深度研报
   * 相比原版的改进（借鉴 WorldMonitor）：
   * 1. 引入聚类上下文 (从碎片到宏观事件)
   * 2. 引入趋势信号上下文 (异常飙升检测)
   * 3. 来源分级标注 (信源可信度透传给 AI)
   * 4. 严格 Zod 校验输出
   * 5. AI 回退链支持
   * 6. 增加研报维度 (威胁评估 + 趋势告警)
   */
  public async generateDailyReport(
    newsList: NewsRecord[],
    clusters?: ClusteredEvent[],
    trendingSpikes?: TrendingSpike[]
  ): Promise<DailyReport> {
    return this.limit(async () => {
      // ── 构建多维上下文 ──
      const contextParts: string[] = [];

      // 1. 新闻列表（附源分级和威胁标注）
      const newsContext = newsList
        .map((n, i) => {
          const tierLabel = n.tier ? `T${n.tier}` : 'T4';
          const threatLabel = n.threatLevel ? THREAT_LABELS[n.threatLevel as keyof typeof THREAT_LABELS] || '' : '';
          return `[${i+1}] ${threatLabel} ${n.title} (Source: ${n.category}, ${tierLabel})`;
        })
        .join('\n')
        .substring(0, 12000);
      contextParts.push(newsContext);

      // 2. 聚类上下文（如果有）
      if (clusters && clusters.length > 0) {
        contextParts.push('\n' + generateClusterContext(clusters));
      }

      // 3. 趋势关键词上下文
      const trendingCtx = generateTrendingContext();
      if (trendingCtx) {
        contextParts.push('\n' + trendingCtx);
      }

      // 4. 趋势飙升详情
      if (trendingSpikes && trendingSpikes.length > 0) {
        contextParts.push('\n[TRENDING SPIKES]');
        for (const spike of trendingSpikes.slice(0, 5)) {
          const multi = spike.baseline > 0 ? `${spike.multiplier.toFixed(1)}x baseline` : 'new surge';
          contextParts.push(`- "${spike.term}": ${spike.count} mentions, ${spike.uniqueSources} sources (${multi})`);
        }
      }

      const fullContext = contextParts.join('\n');

      // ── AI 回退链调用 ──
      for (const provider of AI_PROVIDERS) {
        const apiUrl = process.env[provider.envUrl];
        const apiKey = process.env[provider.envKey];
        if (!apiUrl || !apiKey) continue;

        try {
          const model = process.env[provider.envModel] || provider.defaultModel;
          const response = await axios.post(apiUrl, {
            model,
            messages: [
              { role: "system", content: this.buildSystemPrompt() },
              { role: "user", content: `以下是过去24小时的核心情报集：\n${fullContext}` }
            ],
            response_format: { type: "json_object" }
          }, {
            headers: { 'Authorization': `Bearer ${apiKey}` },
            timeout: 90000
          });

          const rawContent = response.data.choices[0].message.content;
          const parsed = JSON.parse(rawContent);
          
          // Zod 校验
          const validated = DailyReportSchema.parse(parsed);
          return validated;
        } catch (error: any) {
          console.error(`[AI] ${provider.name} 失败: ${error.message}`);
          continue; // 尝试下一个提供商
        }
      }

      throw new Error('所有 AI 提供商均失败');
    });
  }

  private buildSystemPrompt(): string {
    return `你是一位顶级的全球宏观经济学家和首席投资官(CIO)。
你需要根据用户提供的情报集合（包含新闻、聚类事件、趋势关键词信号），撰写一份结构化的高质量研报。

情报数据带有以下标注（请在分析中予以参考）：
- **威胁等级标记**: 🔴 CRIT = 极端/战争级，🟠 HIGH = 高威胁，🟡 MED = 中等，🟢 LOW = 低风险，🔵 INFO = 信息型
- **信源分级**: T1 = 通讯社(最权威)，T2 = 主流大媒，T3 = 专业智库，T4 = 聚合器（注意 T1/T2 的报道可信度远高于 T4）
- **[CLUSTERED EVENTS]**: 被多个独立源报道的聚类宏观事件，(N sources) 表示有 N 个独立源确认
- **[TRENDING KEYWORDS]**: 在 2 小时滚动窗口内异常飙升的关键词，对比 7 天基线

报告受众是具有专业知识的个人投资者，关注地缘政治如何影响资本市场。

请严格按照以下 JSON 格式输出：
{
  "date": "YYYY-MM-DD",
  "executiveSummary": "一两句话总结今天全球动态的核心主线及对市场的整体影响",
  "globalEvents": [
    { 
      "title": "事件分类（如：美联储货币政策/中东局势）", 
      "detail": "详细且专业的事件分析", 
      "category": "事件类型(conflict/economic/diplomatic/military/disaster/health/cyber)",
      "threatLevel": "critical/high/medium/low/info"
    }
  ],
  "economicAnalysis": "一段深度的宏观经济分析（至少300字）。结合这些情报，分析通胀、利率、供应链或全球增长预期的变化趋势。注意引用多个独立源确认的信息。",
  "investmentTrends": [
    { 
      "assetClass": "资产类别（如：美股/黄金/原油/美债/加密货币/人民币）", 
      "trend": "Bullish 或 Bearish 或 Neutral", 
      "rationale": "为什么这么判断的具体理由",
      "confidence": 0-100 的判断置信度
    }
  ],
  "trendingAlerts": [
    {
      "term": "趋势飙升关键词",
      "assessment": "该关键词飙升意味着什么，对市场的潜在影响",
      "significance": "high/medium/low"
    }
  ],
  "riskAssessment": "对当前全球风险格局的综合评估（200字以上），包括哪些地区的地缘风险正在升温或降温",
  "sourceAnalysis": "分析本次情报集中信源的质量特征和覆盖盲区（可选）"
}`;
  }
}
