import asyncio
import json
import re
from typing import List, Dict, Any, Optional, Literal
from pydantic import BaseModel, Field, validator
from openai import AsyncOpenAI
from ..config.settings import CONFIG
from .db_service import DBService, NewsRecord
from .clustering import ClusteredEvent, generate_cluster_context
from .classifier import THREAT_LABELS, ThreatClassification
from ..utils.logger import get_logger
from .prompts import MACRO_ANALYST_PROMPT, SENTIMENT_ANALYST_PROMPT, MARKET_STRATEGIST_PROMPT

logger = get_logger("ai-service")

# ── 研报输出结构定义 (Pydantic Models) ──

class GlobalEvent(BaseModel):
    title: str
    detail: str
    category: Optional[str] = None
    threatLevel: Optional[str] = None

class InvestmentTrend(BaseModel):
    assetClass: str
    trend: Literal['Bullish', 'Bearish', 'Neutral']
    rationale: str
    confidence: Optional[float] = Field(None, ge=0, le=100)
    timeframe: Optional[str] = None

class IntelSource(BaseModel):
    name: str
    tier: int
    url: Optional[str] = None

class IntelligenceItem(BaseModel):
    content: str
    category: str
    sources: List[IntelSource]
    credibility: str
    credibilityReason: str
    importance: str

class AgentInsights(BaseModel):
    macro: Optional[str] = None
    sentiment: Optional[str] = None

class DailyReport(BaseModel):
    date: str
    intelligenceDigest: List[IntelligenceItem]
    executiveSummary: str
    globalEvents: List[GlobalEvent]
    economicAnalysis: str
    investmentTrends: List[InvestmentTrend]
    agentInsights: Optional[AgentInsights] = None
    riskAssessment: Optional[str] = None
    sourceAnalysis: Optional[str] = None

# ── Token 预算管理 ──

def estimate_tokens(text: str) -> int:
    return int(len(text) / 3.5)

def truncate_to_token_budget(text: str, max_tokens: int) -> str:
    max_chars = int(max_tokens * 3.5)
    if len(text) <= max_chars: return text
    truncated = text[:max_chars]
    last_newline = truncated.rfind('\n')
    if last_newline > max_chars * 0.8:
        return truncated[:last_newline]
    return truncated

# ── JSON 提取 (容错) ──

def extract_json(raw: str) -> str:
    trimmed = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]', '', raw).strip()
    try:
        json.loads(trimmed)
        return trimmed
    except:
        pass
    
    fence_match = re.search(r'```(?:json)?\s*\n?([\s\S]*?)```', trimmed)
    if fence_match:
        candidate = fence_match.group(1).strip()
        try:
            json.loads(candidate)
            return candidate
        except:
            pass
            
    first = trimmed.find('{')
    last = trimmed.rfind('}')
    if first != -1 and last > first:
        candidate = trimmed[first:last+1]
        try:
            json.loads(candidate)
            return candidate
        except:
            pass
    return trimmed

class AIService:
    def __init__(self, db: Optional[DBService] = None):
        self.db = db or DBService()
        self.client = AsyncOpenAI(api_key=CONFIG.ai_api_key, base_url=CONFIG.ai_api_url.replace('/chat/completions', ''))

    async def generate_daily_report(
        self,
        news_list: List[NewsRecord],
        clusters: List[ClusteredEvent] = None
    ) -> DailyReport:
        """多智能体研报生成流"""
        total_budget = CONFIG.ai_max_context_tokens
        news_budget = int(total_budget * 0.50)
        cluster_budget = int(total_budget * 0.20)

        context_parts = []
        context_parts.append(self.build_news_context(news_list, news_budget))
        
        if clusters:
            cluster_ctx = generate_cluster_context(clusters)
            if cluster_ctx:
                context_parts.append("\n" + truncate_to_token_budget(cluster_ctx, cluster_budget))
        
        raw_context = "\n".join(context_parts)

        # ── 多智能体并行流程 ──
        logger.info("启动多智能体并发推理...")
        
        # 为了兼容 yfinance，此处预留占位逻辑（实际逻辑在 Phase 5 任务 2 中完善）
        # 暂时模拟价格数据
        market_price_context = "[REAL-TIME MARKET DATA]\n- GC=F: 2500.5\n- CL=F: 80.2"

        tasks = [
            self.call_agent("MacroAnalyst", MACRO_ANALYST_PROMPT, raw_context),
            self.call_agent("SentimentAnalyst", SENTIMENT_ANALYST_PROMPT, raw_context)
        ]
        
        macro_out, sentiment_out = await asyncio.gather(*tasks)

        # ── 首席战略官 (Market Strategist) 整合 ──
        logger.info("启动首席战略官整合研报...")
        final_strategist_input = f"""
[RAW INTEL CONTEXT]
{raw_context}

[MACRO ANALYST OUTPUT]
```json
{macro_out}
```

[SENTIMENT ANALYST OUTPUT]
```json
{sentiment_out}
```

[MARKET DATA]
{market_price_context}

请根据以上背景，撰写最终机构级研报。
"""
        final_raw = await self.call_agent("MarketStrategist", MARKET_STRATEGIST_PROMPT, final_strategist_input, use_json=True)
        parsed_json = await self.parse_daily_report_json(final_raw)
        report = DailyReport(**parsed_json)
        
        # ── 预测持久化逻辑预留 ──
        # await self._persist_predictions(report)

        return report

    async def parse_daily_report_json(self, raw_text: str) -> Dict[str, Any]:
        """解析日报 JSON；若失败，自动触发一次修复重试。"""
        try:
            return json.loads(extract_json(raw_text))
        except json.JSONDecodeError as e:
            logger.warning(f"MarketStrategist JSON 解析失败，尝试修复: {e}")

        repaired_raw = await self.repair_daily_report_json(raw_text)
        try:
            return json.loads(extract_json(repaired_raw))
        except json.JSONDecodeError as e:
            snippet = extract_json(repaired_raw)[:400].replace('\n', ' ')
            raise ValueError(f"MarketStrategist JSON 修复后仍非法: {e}. snippet={snippet}") from e

    async def repair_daily_report_json(self, broken_raw: str) -> str:
        """调用 LLM 将无效输出修复为合法 JSON 对象。"""
        repair_system_prompt = (
            "你是一个严格的 JSON 修复器。"
            "你只能输出一个合法 JSON 对象，不得输出 Markdown、注释、解释文字。"
        )
        schema_hint = (
            "必须保留/补全字段: "
            "date(string), intelligenceDigest(array), executiveSummary(string), "
            "globalEvents(array), economicAnalysis(string), investmentTrends(array)。"
            "可选字段: agentInsights(object), riskAssessment(string), sourceAnalysis(string)。"
        )
        safe_raw = truncate_to_token_budget(broken_raw, max_tokens=4000)
        repair_user_content = f"""
原始输出不是合法 JSON，请修复。

{schema_hint}

[BROKEN_OUTPUT]
```text
{safe_raw}
```
"""
        return await self.call_agent(
            "MarketStrategistRepair",
            repair_system_prompt,
            repair_user_content,
            use_json=True
        )

    async def call_agent(self, name: str, system_prompt: str, user_content: str, use_json: bool = True) -> str:
        """调用 AI 模型（含回退逻辑）"""
        providers = [
            {"url": CONFIG.ai_api_url, "key": CONFIG.ai_api_key, "model": CONFIG.ai_model},
            {"url": CONFIG.ai_fallback_url, "key": CONFIG.ai_fallback_key, "model": CONFIG.ai_fallback_model}
        ]

        for p in providers:
            if not p["url"] or not p["key"]: continue
            try:
                # 重新初始化 client 以支持不同 provider 的 base_url
                client = AsyncOpenAI(api_key=p["key"], base_url=p["url"].split('/chat/completions')[0])
                response = await client.chat.completions.create(
                    model=p["model"],
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_content}
                    ],
                    response_format={"type": "json_object"} if use_json else None,
                    timeout=CONFIG.ai_timeout_ms / 1000
                )
                logger.info(f"{name} 调用成功 (Model: {p['model']})")
                return response.choices[0].message.content or ""
            except Exception as e:
                logger.warning(f"{name} 调用失败 ({p['model']}): {e}")
                continue
        
        raise Exception(f"{name} 所有提供商调用均失败")

    def build_news_context(self, news_list: List[NewsRecord], budget: int) -> str:
        lines = []
        used = 0
        for i, n in enumerate(news_list):
            label = THREAT_LABELS.get(n.threatLevel, '')
            header = f"[{i+1}] {label} {n.title} ({n.category}, T{n.tier})"
            
            entry = header
            if n.content and len(n.content) > 80:
                excerpt = re.sub(r'\s+', ' ', n.content[:300]).strip()
                entry += f"\n  ▸ {excerpt}"
            
            tokens = estimate_tokens(entry)
            if used + tokens > budget: break
            lines.append(entry)
            used += tokens
        return "\n".join(lines)
