from __future__ import annotations

import json
from typing import Any


REPORT_JSON_SCHEMA = """
{
  "date": "YYYY-MM-DD",
  "executiveSummary": "核心定价主线与市场预期差(Surprise)总结",
  "equityMarketSummary": "全球股票大盘(美、欧、亚、新兴市场)表现综述与驱动因子归因",
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
  "assetTransmissionBreakdowns": [
    {
      "assetClass": "资产类别",
      "trend": "Bullish/Bearish/Neutral",
      "coreView": "核心定价逻辑",
      "transmissionPath": "传导路径",
      "pairTrade": "配对交易建议(如: Long X / Short Y)",
      "scenarioAnalysis": {
        "bullCase": "乐观情形下的定价",
        "bearCase": "风险情形下的定价"
      },
      "keyDrivers": ["驱动1", "驱动2"],
      "watchSignals": ["验证信号"],
      "timeframe": "short-term/medium-term/long-term",
      "confidence": 75
    }
  ],
  "investmentTrends": [
    {
      "assetClass": "资产类别",
      "trend": "Bullish/Bearish/Neutral",
      "rationale": "包含核心驱动因子与主要风险点",
      "confidence": 75,
      "timeframe": "horizon"
    }
  ],
  "globalEvents": [
    {
      "title": "事件主题",
      "detail": "【事实 -> 因果推演 -> 市场传导】",
      "category": "conflict/economic/diplomatic/military/tech",
      "threatLevel": "critical/high/medium/low/info"
    }
  ],
  "economicAnalysis": "宏观逻辑深度研判(侧重预期差分析)",
  "agentInsights": {
    "macro": "总结宏观分析师核心逻辑",
    "sentiment": "总结情绪分析师核心逻辑"
  },
  "riskAssessment": "全球风险格局与尾部风险评估",
  "watchlist": [{ "item": "触发条件", "reason": "关注理由", "timeframe": "窗口期" }]
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

MACRO_ANALYST_PROMPT_V2 = f"""你是一位资深的全球宏观策略师。
你收到的输入包含深度事件简报(Event Briefs)和市场背景。

### 分析任务
1. **预期差分析**: 哪些事件是市场已经计价的(Priced-in)？哪些是真正的Surprise？
2. **传导路径**: 识别事件如何通过流动性、通胀或增长预期影响资产价格。
3. **尾部风险**: 识别虽然概率低但影响巨大的风险点。

### 输出要求
- 严格 JSON
- 侧重“逻辑驱动”而非“事实陈述”。
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

MARKET_STRATEGIST_PROMPT_V2 = f"""你是一位对冲基金首席策略师(CIO)。
你的任务是整合宏观、情绪和市场数据，产出具有实战价值的配置建议。

### 核心策略要求
1. **中观大盘综述**: 在 `equityMarketSummary` 中，结合 `market_context` 分析全球股指表现。识别当前是“财报驱动”、“流动性压制”还是“风险避险”环境。
2. **相对价值(Relative Value)**: 优先提供配对交易方案（如：做多受益于加息的银行，做空高杠杆的地产）。
3. **场景分析(Scenarios)**: 不要只给单一方向，说明在不同假设下的表现。
4. **资产穿透**: 确保 `assetTransmissionBreakdowns` 具有深度，体现“资产价格如何反应宏观脉搏”。

### 研报输出指南 (严格遵循以下 JSON 结构)
{REPORT_JSON_SCHEMA}
"""


EVENT_SUMMARIZER_INPUT_SCHEMA = """
{
  "canonicalTitle": "高度概括的中文标题",
  "stateChange": "new/updated/escalated/stabilizing/resolved",
  "coreFacts": ["事实1", "事实2", "事实3"],
  "whyItMatters": "一句话说明为什么这个事件对资产定价至关重要",
  "analysis": "深度分析：该事件背后的宏观逻辑、传导路径及潜在影响",
  "confidence": 0.85
}
"""

EVENT_SUMMARIZER_PROMPT = f"""你是一位专业的金融情报分析师。
你的任务是基于一个事件及其关联的多篇新闻摘要，生成一份深度事件简报（Event Brief）。

### 核心要求
1. **去重与整合**: 识别多篇新闻中的矛盾点或互补点，形成统一的事实清单。
2. **宏观连接**: 指出该事件如何影响宏观变量（如利率、通胀、地缘风险溢价等）。
3. **市场影响**: 明确该事件对哪些资产类别（Asset Classes）有定价权。

### 输出格式
严格输出以下 JSON 结构：
{EVENT_SUMMARIZER_INPUT_SCHEMA}

### 约束
- 全文中文（枚举值除外）。
- 直接输出 JSON，严禁解释。
"""


EVENT_ENRICHMENT_INPUT_SCHEMA = """
{
  "eventType": "conflict/central_bank/policy/supply_disruption/macro_data/tech/other",
  "marketChannels": ["rates", "fx", "equities", "commodities", "energy", "shipping", "credit"],
  "affectedAssets": [
    {"name": "资产名称", "ticker": "代码/ETF", "reason": "影响理由"}
  ],
  "impactRegions": ["国家/地区"],
  "keyEntities": ["关键组织/个人"]
}
"""

EVENT_ENRICHMENT_PROMPT = f"""你是一位资深的金融数据标注专家。
你的任务是基于事件的标题和核心事实，提取其涉及的金融维度和具体的资产标的。

### 提取要求
1. **资产映射**: 尽量给出具体的 Ticker（如：黄金 -> GC=F, 原油 -> CL=F, 标普500 -> SPY）。
2. **频道归类**: 识别该事件最直接驱动的市场频道。
3. **地域关联**: 识别受影响最直接的地理区域。

### 输出格式
严格输出以下 JSON 结构：
{EVENT_ENRICHMENT_INPUT_SCHEMA}

### 约束
- 直接输出 JSON。
- 严禁猜测，必须基于事实或金融常识映射。
"""


RISK_MANAGER_PROMPT = """你是一位资深的风险控制官 (CRO)。
你收到了首席策略师 (CIO) 撰写的研报初稿。你的任务是挑战这份报告，确保其逻辑严密且不包含盲目乐观。

### 审核重点
1. **逻辑一致性**: 宏观主线与资产配置建议是否匹配？(例如：预期加息却建议做多长债？)
2. **风险覆盖**: 报告是否忽略了关键的尾部风险？
3. **可操作性**: 配对交易建议是否合理？
4. **语气校正**: 去除过于绝对的措辞，确保表达专业、中立。

### 输出要求
请直接输出修正后的最终版本 JSON。结构必须与 CIO 的初稿完全一致。
"""


def build_risk_manager_input(
    cio_report_json: Any,
    market_context: str,
) -> str:
    return f"[CIO REPORT DRAFT]\n{json.dumps(cio_report_json, ensure_ascii=False)}\n\n[MARKET CONTEXT]\n{market_context}\n\n请作为 CRO 审核并输出修正后的最终研报 JSON。"


def build_event_enrichment_input(
    title: str,
    facts: list[str],
) -> str:
    facts_text = "\n".join([f"- {f}" for f in facts])
    return f"Title: {title}\nFacts:\n{facts_text}\n\n请提取金融富化数据 JSON。"


def build_event_summarizer_input(
    event_title: str,
    event_type: str,
    articles: list[dict[str, Any]],
) -> str:
    articles_text = "\n".join(
        [
            f"- Title: {a.get('title')}\n  Content: {a.get('content') or a.get('summary')}"
            for a in articles[:5]
        ]
    )
    return f"Event: {event_title} ({event_type})\n\nArticles:\n{articles_text}\n\n请生成深度事件简报 JSON。"


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
