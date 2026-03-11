import axios from 'axios';
import pLimit from 'p-limit';
import { NewsRecord } from './db.service';

export interface DailyReport {
  date: string;
  executiveSummary: string; // 一句话总结今天的主基调
  globalEvents: { title: string; detail: string }[]; // 重大事件列表
  economicAnalysis: string; // 宏观经济形势深度分析
  investmentTrends: { assetClass: string; trend: 'Bullish' | 'Bearish' | 'Neutral'; rationale: string }[]; // 投资方向与资产研判
}

export class AIService {
  private limit = pLimit(1); // 生成大报告很耗资源，串行执行

  public async generateDailyReport(newsList: NewsRecord[]): Promise<DailyReport> {
    return this.limit(async () => {
      // 构建给 AI 的 Context (限制长度，防止超出 Token 限制)
      const context = newsList.map((n, i) => `[${i+1}] ${n.title} (Source: ${n.category})`).join('\n').substring(0, 15000);

      try {
        const response = await axios.post(process.env.AI_API_URL!, {
          model: process.env.AI_MODEL || "gpt-4o", // 推荐使用 GPT-4o 或 Claude 3.5 Sonnet 以获得最佳深度
          messages: [
            {
              role: "system",
              content: `你是一位顶级的全球宏观经济学家和首席投资官(CIO)。
              你需要根据用户提供的一系列过去24小时的全球新闻标题，撰写一份结构化的高质量研报。
              
              报告受众是具有一定专业知识的个人投资者，关注地缘政治如何影响资本市场。
              
              请严格按照以下 JSON 格式输出：
              {
                "date": "YYYY-MM-DD",
                "executiveSummary": "一两句话总结今天全球动态的核心主线及对市场的整体影响",
                "globalEvents": [
                  { "title": "事件分类（如：美联储货币政策/中东局势）", "detail": "详细且专业的事件分析" }
                ],
                "economicAnalysis": "一段深度的宏观经济分析（至少300字）。结合这些新闻，分析通胀、利率、供应链或全球增长预期的变化趋势。",
                "investmentTrends": [
                  { 
                    "assetClass": "资产类别（如：美股/黄金/原油/美债/加密货币）", 
                    "trend": "Bullish 或 Bearish 或 Neutral", 
                    "rationale": "为什么这么判断的具体理由"
                  }
                ]
              }`
            },
            { role: "user", content: `以下是过去24小时的核心新闻集：\n${context}` }
          ],
          response_format: { type: "json_object" }
        }, {
          headers: { 'Authorization': `Bearer ${process.env.AI_API_KEY}` },
          timeout: 60000 // 生成长文需要较长超时
        });
        
        return JSON.parse(response.data.choices[0].message.content) as DailyReport;
      } catch (error) {
        throw new Error(`AI 报告生成失败: ${error.message}`);
      }
    });
  }
}
