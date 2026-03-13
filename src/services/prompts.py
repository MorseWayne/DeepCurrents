from __future__ import annotations

import json
from typing import Any


REPORT_JSON_SCHEMA = """
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
  "macroTransmissionChain": {
    "headline": "一句话总主线",
    "shockSource": "主冲击源",
    "macroVariables": ["宏观变量1", "宏观变量2"],
    "marketPricing": "跨资产定价影响",
    "allocationImplication": "配置含义",
    "steps": [
      {"stage": "冲击源", "driver": "事件如何成为主线"},
      {"stage": "宏观变量", "driver": "哪些变量被重定价"},
      {"stage": "市场定价", "driver": "市场如何反应"},
      {"stage": "配置含义", "driver": "当前更适合的配置方向"}
    ],
    "timeframe": "short-term/medium-term/long-term",
    "confidence": 78
  },
  "globalEvents": [
    {
      "title": "事件主题",
      "detail": "【事实概要 -> 因果推演 -> 市场传导路径】",
      "category": "conflict/economic/diplomatic/military/disaster/health/cyber/tech",
      "threatLevel": "critical/high/medium/low/info"
    }
  ],
  "economicAnalysis": "宏观逻辑深度研判",
  "assetTransmissionBreakdowns": [
    {
      "assetClass": "资产类别",
      "trend": "Bullish/Bearish/Neutral",
      "coreView": "该资产最核心的一句话判断",
      "transmissionPath": "事件 -> 宏观变量 -> 定价 -> 方向",
      "keyDrivers": ["驱动1", "驱动2"],
      "watchSignals": ["验证信号1", "验证信号2"],
      "timeframe": "short-term/medium-term/long-term",
      "confidence": 75
    }
  ],
  "investmentTrends": [
    {
      "assetClass": "资产类别",
      "trend": "Bullish/Bearish/Neutral",
      "rationale": "含核心驱动因子(Drivers)和主要下行风险(Risks)",
      "confidence": 75,
      "timeframe": "short-term/medium-term/long-term"
    }
  ],
  "agentInsights": {
    "macro": "总结宏观分析师的核心观点",
    "sentiment": "总结情绪分析师的核心观点"
  },
  "trendingAlerts": [{ "term": "关键词", "assessment": "影响分析", "significance": "high/medium/low" }],
  "keyDataPoints": [{ "metric": "指标", "value": "数值", "implication": "含义" }],
  "riskAssessment": "全球风险格局评估",
  "watchlist": [{ "item": "触发条件", "reason": "关注理由", "timeframe": "窗口期" }],
  "sourceAnalysis": "信源质量与盲区评估"
}
"""

MACRO_ANALYST_OUTPUT_SCHEMA = """
{
  "coreThesis": "一句话说明当前最关键的宏观主线",
  "keyDrivers": ["驱动 1", "驱动 2"],
  "riskScenarios": ["尾部风险 1", "尾部风险 2"],
  "watchpoints": ["未来需要跟踪的触发点 1"],
  "confidence": 75
}
"""

SENTIMENT_ANALYST_OUTPUT_SCHEMA = """
{
  "marketRegime": "Risk-on/Risk-off/Mixed",
  "sentimentDrivers": ["情绪驱动 1", "情绪驱动 2"],
  "crossAssetSignals": ["跨资产线索 1", "跨资产线索 2"],
  "positioningRisks": ["仓位与拥挤风险 1"],
  "confidence": 70
}
"""

MACRO_ANALYST_PROMPT = """你是一位资深的全球宏观经济学家和地缘政治分析师。
你的任务是分析过去24小时的情报，识别出最核心的宏观主线和地缘风险。

### 分析重点
1. **因果推演**: 解释事件 A 如何通过宏观机制影响全球市场。
2. **风险评估**: 识别潜在的尾部风险和冲突升级点。
3. **政策解读**: 分析各国央行和政府的政策动向及其意图。

请以 JSON 格式输出。
"""

SENTIMENT_ANALYST_PROMPT = """你是一位顶级的市场情绪分析师，擅长从海量新闻和社交媒体摘要中捕捉市场“底色”。
你的任务是评估当前全球市场的情绪状态。

### 分析重点
1. **贪婪与恐惧**: 市场目前是处于风险偏好（Risk-on）还是避险模式（Risk-off）？
2. **共识与分歧**: 哪些观点是市场共识？哪些地方存在严重分歧？

请以 JSON 格式输出。
"""

MARKET_STRATEGIST_PROMPT = f"""你是一位首席投资官 (CIO)，负责汇总多方分析并给出最终的资产配置策略。
你收到了来自【宏观分析师】和【情绪分析师】的报告，以及【实时行情数据】。

### 核心任务
1. **交叉验证**: 将宏观逻辑、市场情绪与真实价格走势进行比对。如果价格走势与逻辑背离，请分析是否存在“预期差”或“定价错误”。
2. **投资研判**: 对大类资产给出明确的看涨/看跌建议。
3. **合成研报**: 撰写最终的机构级结构化研报。

### 研报输出指南 (严格遵循以下 JSON 结构)
{REPORT_JSON_SCHEMA}

### 输出约束
- **语言**: 全文中文（枚举值除外）。
- **格式**: 严格 JSON，严禁在 JSON 块之外添加任何解释文字。直接以 {{ 开头。
"""

MACRO_ANALYST_PROMPT_V2 = f"""你是一位资深的全球宏观经济学家和地缘政治分析师。
你收到的输入已经不再是原始新闻列表，而是经过压缩后的：
1. event briefs
2. theme briefs
3. market context

你的任务是从这些结构化输入中提炼最关键的宏观主线、政策传导路径和尾部风险。

### 输入使用原则
1. 优先围绕事件卡中的 `stateChange / whyItMatters / coreFacts` 建立主线。
2. 使用主题卡识别跨事件共振，不要重复逐条复述事件。
3. 结合市场上下文判断哪些宏观风险已经被价格验证，哪些仍是预期差。

### 输出要求
- 严格 JSON
- 正文中文，枚举值可用英文
- 只输出以下 schema：
{MACRO_ANALYST_OUTPUT_SCHEMA}
"""

SENTIMENT_ANALYST_PROMPT_V2 = f"""你是一位顶级的市场情绪分析师。
你收到的输入已经压缩为：
1. event briefs
2. theme briefs
3. market context

你的任务是识别当前全球市场处于 risk-on、risk-off 还是 mixed，并指出情绪驱动、跨资产线索和仓位风险。

### 输入使用原则
1. 用事件卡判断风险是否在扩散、反转或被证伪。
2. 用主题卡识别市场正在围绕哪些共识主线交易。
3. 用市场上下文识别价格是否出现追涨、滞后或背离。

### 输出要求
- 严格 JSON
- 正文中文，枚举值可用英文
- 只输出以下 schema：
{SENTIMENT_ANALYST_OUTPUT_SCHEMA}
"""

MARKET_STRATEGIST_PROMPT_V2 = f"""你是一位首席投资官 (CIO)。
你将读取：
1. event/theme/market context 组成的压缩背景
2. Macro Analyst 的结构化 JSON 输出
3. Sentiment Analyst 的结构化 JSON 输出

你的任务是把宏观逻辑、市场情绪和价格线索整合成最终机构级结构化日报。

### 核心任务
1. 交叉验证 macro thesis、sentiment regime 与 market context 是否一致。
2. 提炼对资产配置真正重要的事件与主题，不重复展开低增量内容。
3. 严格输出一条 `macroTransmissionChain`，体现 `冲击源 -> 宏观变量 -> 市场定价 -> 配置含义`。
4. 输出两到四条 `assetTransmissionBreakdowns`，每条都必须写清楚 `transmissionPath`。
5. 给出结构化的 global events、economic analysis 与 investment trends。

### 研报输出指南 (严格遵循以下 JSON 结构)
{REPORT_JSON_SCHEMA}

### 输出约束
- 输入已是 event/theme/market context，禁止假设自己看过原始新闻列表。
- `macroTransmissionChain` 必须偏宏观，不要把事件摘要直接改写成传导链。
- `assetTransmissionBreakdowns` 必须偏资产配置/交易表达，不要重复宏观总论。
- 全文中文（枚举值除外）。
- 严格 JSON，严禁在 JSON 块之外添加任何解释文字。直接以 {{ 开头。
"""


def build_macro_analyst_input(context_text: str) -> str:
    return "\n".join(
        [
            "[EVENT/THEME/MARKET CONTEXT]",
            _text(context_text),
            "",
            "请基于以上 event briefs、theme briefs 和 market context，输出宏观分析 JSON。",
        ]
    ).strip()


def build_sentiment_analyst_input(
    context_text: str,
    market_context_text: str,
) -> str:
    return "\n".join(
        [
            "[EVENT/THEME CONTEXT]",
            _text(context_text),
            "",
            "[MARKET CONTEXT]",
            _text(market_context_text),
            "",
            "请基于以上 event briefs、theme briefs 和 market context，输出情绪分析 JSON。",
        ]
    ).strip()


def build_market_strategist_input(
    context_text: str,
    macro_json: Any,
    sentiment_json: Any,
    market_context_text: str,
) -> str:
    return "\n".join(
        [
            "[EVENT/THEME/MARKET CONTEXT]",
            _text(context_text),
            "",
            "[MACRO ANALYST OUTPUT]",
            _to_json_block(macro_json),
            "",
            "[SENTIMENT ANALYST OUTPUT]",
            _to_json_block(sentiment_json),
            "",
            "[MARKET CONTEXT]",
            _text(market_context_text),
            "",
            "请据此输出最终机构级结构化日报 JSON。",
        ]
    ).strip()


def _to_json_block(value: Any) -> str:
    if isinstance(value, str):
        return value.strip()
    return json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2)


def _text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    return str(value).strip()


__all__ = [
    "REPORT_JSON_SCHEMA",
    "MACRO_ANALYST_OUTPUT_SCHEMA",
    "SENTIMENT_ANALYST_OUTPUT_SCHEMA",
    "MACRO_ANALYST_PROMPT",
    "SENTIMENT_ANALYST_PROMPT",
    "MARKET_STRATEGIST_PROMPT",
    "MACRO_ANALYST_PROMPT_V2",
    "SENTIMENT_ANALYST_PROMPT_V2",
    "MARKET_STRATEGIST_PROMPT_V2",
    "build_macro_analyst_input",
    "build_sentiment_analyst_input",
    "build_market_strategist_input",
]
