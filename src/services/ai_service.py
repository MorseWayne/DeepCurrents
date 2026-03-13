import asyncio
import json
import re
import time
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional, Literal, Tuple
from pydantic import BaseModel, Field
from openai import AsyncOpenAI
from ..config.settings import CONFIG
from ..config.asset_symbols import resolve_asset_symbol, get_default_market_symbols
from .db_service import DBService, NewsRecord
from .clustering import ClusteredEvent, generate_cluster_context
from .classifier import THREAT_LABELS
from .metrics import build_report_metrics
from ..utils.market_data import get_market_price, search_market_symbol
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

DEFAULT_CONTEXT_WINDOW = 16000
OUTPUT_RESERVE_RATIO = 0.08
OUTPUT_RESERVE_MIN = 2048
OUTPUT_RESERVE_MAX = 16384
SAFETY_MARGIN = 4000
PROMPT_OVERHEAD = 2000
MIN_WORKING_INPUT = 2000
WINDOW_CACHE_TTL_SEC = 900
FINAL_STRATEGIST_PROMPT = """
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
MODEL_CONTEXT_WINDOW_FALLBACKS: Dict[str, int] = {
    "gpt-4o": 128000,
    "gpt-4o-mini": 128000,
    "gpt-4.1": 1047576,
    "gpt-4.1-mini": 1047576,
    "gpt-4.1-nano": 1047576,
    "gpt-5": 400000,
    "gpt-5-mini": 400000,
    "gpt-5-nano": 400000,
}
WINDOW_FIELD_CANDIDATES = (
    "context_window",
    "max_context_tokens",
    "max_input_tokens",
    "input_tokens",
)
VALID_TRENDS = {"Bullish", "Bearish", "Neutral"}
VALID_CREDIBILITY = {"high", "medium", "low"}
VALID_IMPORTANCE = {"critical", "high", "medium", "low"}
VALID_THREAT_LEVELS = {"critical", "high", "medium", "low", "info"}

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
        self._asset_symbol_cache: Dict[str, Optional[str]] = {}
        self._window_cache: Dict[str, Dict[str, Any]] = {}
        self.last_report_guard_stats: Dict[str, Any] = {}
        self.last_report_metrics: Dict[str, Any] = {}

    @staticmethod
    def _to_text(value: Any) -> str:
        if value is None:
            return ""
        if isinstance(value, str):
            return value.strip()
        if isinstance(value, (int, float, bool)):
            return str(value)
        if isinstance(value, list):
            parts = []
            for item in value:
                text = AIService._to_text(item)
                if text:
                    parts.append(text)
            return "；".join(parts).strip()
        if isinstance(value, dict):
            for key in ("content", "detail", "description", "summary", "title", "topic", "name", "reason", "analysis", "text"):
                text = AIService._to_text(value.get(key))
                if text:
                    return text
            return json.dumps(value, ensure_ascii=False)
        return str(value).strip()

    @staticmethod
    def _normalize_confidence(value: Any) -> Optional[float]:
        try:
            confidence = float(value)
            if confidence <= 1:
                confidence *= 100
            return max(0.0, min(100.0, confidence))
        except Exception:
            return None

    @staticmethod
    def _confidence_to_credibility(confidence: Optional[float]) -> str:
        if confidence is None:
            return "medium"
        if confidence >= 75:
            return "high"
        if confidence >= 45:
            return "medium"
        return "low"

    @staticmethod
    def _confidence_to_importance(confidence: Optional[float]) -> str:
        if confidence is None:
            return "medium"
        if confidence >= 85:
            return "critical"
        if confidence >= 65:
            return "high"
        if confidence >= 40:
            return "medium"
        return "low"

    @staticmethod
    def _normalize_trend(value: Any) -> str:
        raw = AIService._to_text(value)
        if not raw:
            return "Neutral"

        canonical = raw.strip()
        if canonical in VALID_TRENDS:
            return canonical

        lowered = canonical.lower()
        bullish_keywords = ("bullish", "看涨", "做多", "偏多", "上行", "增配", "买入", "risk-on")
        bearish_keywords = ("bearish", "看跌", "做空", "偏空", "下行", "减配", "卖出", "risk-off")
        neutral_keywords = ("neutral", "中性", "观望", "震荡", "平衡")

        if any(keyword in lowered for keyword in bullish_keywords):
            return "Bullish"
        if any(keyword in lowered for keyword in bearish_keywords):
            return "Bearish"
        if any(keyword in lowered for keyword in neutral_keywords):
            return "Neutral"
        return "Neutral"

    @staticmethod
    def _normalize_threat_level(value: Any) -> Optional[str]:
        threat = AIService._to_text(value).lower()
        if not threat:
            return None
        if threat in VALID_THREAT_LEVELS:
            return threat

        high_keywords = ("critical", "高", "严重", "紧急")
        medium_keywords = ("medium", "中", "关注")
        low_keywords = ("low", "低", "轻微")
        info_keywords = ("info", "信息", "一般")

        if any(k in threat for k in high_keywords):
            return "high"
        if any(k in threat for k in medium_keywords):
            return "medium"
        if any(k in threat for k in low_keywords):
            return "low"
        if any(k in threat for k in info_keywords):
            return "info"
        return "info"

    def _normalize_sources(self, value: Any) -> List[Dict[str, Any]]:
        normalized: List[Dict[str, Any]] = []

        def _append_source(name_val: Any, tier_val: Any = None, url_val: Any = None):
            name = self._to_text(name_val)
            if not name:
                return
            try:
                tier = int(tier_val)
            except Exception:
                tier = 3
            tier = max(1, min(4, tier))
            url = self._to_text(url_val) or None
            source: Dict[str, Any] = {"name": name, "tier": tier}
            if url:
                source["url"] = url
            normalized.append(source)

        if isinstance(value, list):
            for item in value:
                if isinstance(item, dict):
                    _append_source(
                        item.get("name") or item.get("source") or item.get("title"),
                        item.get("tier"),
                        item.get("url") or item.get("link")
                    )
                else:
                    _append_source(item)
        elif isinstance(value, dict):
            _append_source(
                value.get("name") or value.get("source") or value.get("title"),
                value.get("tier"),
                value.get("url") or value.get("link")
            )
        elif value is not None:
            _append_source(value)

        if not normalized:
            normalized.append({"name": "Unknown Source", "tier": 3})
        return normalized

    def _normalize_intelligence_digest(self, value: Any) -> List[Dict[str, Any]]:
        digest = value if isinstance(value, list) else []
        normalized: List[Dict[str, Any]] = []

        for raw_item in digest:
            item = raw_item if isinstance(raw_item, dict) else {"content": self._to_text(raw_item)}
            confidence = self._normalize_confidence(item.get("confidence"))
            content = (
                self._to_text(item.get("content"))
                or self._to_text(item.get("topic"))
                or self._to_text(item.get("summary"))
                or self._to_text(item.get("description"))
            )
            if not content:
                continue

            category = self._to_text(item.get("category") or item.get("topicCategory") or item.get("type") or "general").lower()
            credibility = self._to_text(item.get("credibility")).lower()
            if credibility not in VALID_CREDIBILITY:
                credibility = self._confidence_to_credibility(confidence)
            importance = self._to_text(item.get("importance")).lower()
            if importance not in VALID_IMPORTANCE:
                importance = self._confidence_to_importance(confidence)

            normalized.append({
                "content": content,
                "category": category or "general",
                "sources": self._normalize_sources(item.get("sources") or item.get("source") or item.get("evidenceSources")),
                "credibility": credibility,
                "credibilityReason": (
                    self._to_text(item.get("credibilityReason"))
                    or self._to_text(item.get("evidence"))
                    or "基于信源交叉验证与历史可信度评估。"
                ),
                "importance": importance,
            })

        if not normalized:
            normalized.append({
                "content": "暂无可用的结构化情报摘要，建议复核原始新闻上下文。",
                "category": "general",
                "sources": [{"name": "System", "tier": 3}],
                "credibility": "low",
                "credibilityReason": "自动兜底生成，待人工复核。",
                "importance": "low",
            })
        return normalized

    def _normalize_global_events(self, value: Any) -> List[Dict[str, Any]]:
        events = value if isinstance(value, list) else []
        normalized: List[Dict[str, Any]] = []

        for raw_item in events:
            item = raw_item if isinstance(raw_item, dict) else {"detail": self._to_text(raw_item)}
            title = (
                self._to_text(item.get("title"))
                or self._to_text(item.get("event"))
                or self._to_text(item.get("theme"))
                or self._to_text(item.get("topic"))
                or self._to_text(item.get("region"))
            )
            detail = (
                self._to_text(item.get("detail"))
                or self._to_text(item.get("description"))
                or self._to_text(item.get("analysis"))
                or self._to_text(item.get("impact"))
                or self._to_text(item.get("content"))
            )
            if not title and detail:
                title = detail[:36]
            if not title and not detail:
                continue

            event: Dict[str, Any] = {
                "title": title or "未命名事件",
                "detail": detail or "暂无详细描述。",
            }
            category = self._to_text(item.get("category") or item.get("type"))
            if category:
                event["category"] = category
            threat_level = self._normalize_threat_level(item.get("threatLevel") or item.get("severity"))
            if threat_level:
                event["threatLevel"] = threat_level
            normalized.append(event)

        return normalized

    def _normalize_investment_trends(self, value: Any) -> List[Dict[str, Any]]:
        trends = value if isinstance(value, list) else []
        normalized: List[Dict[str, Any]] = []

        for raw_item in trends:
            item = raw_item if isinstance(raw_item, dict) else {"rationale": self._to_text(raw_item)}
            asset_class = (
                self._to_text(item.get("assetClass"))
                or self._to_text(item.get("asset"))
                or self._to_text(item.get("theme"))
                or self._to_text(item.get("sector"))
                or "Macro Basket"
            )
            trend = self._normalize_trend(item.get("trend"))
            rationale = (
                self._to_text(item.get("rationale"))
                or self._to_text(item.get("reason"))
                or self._to_text(item.get("description"))
                or self._to_text(item.get("trend"))
                or "基于当前事件链与市场定价关系的保守研判。"
            )
            confidence = self._normalize_confidence(item.get("confidence"))
            timeframe = self._to_text(item.get("timeframe") or item.get("horizon")) or None

            trend_item: Dict[str, Any] = {
                "assetClass": asset_class,
                "trend": trend,
                "rationale": rationale,
            }
            if confidence is not None:
                trend_item["confidence"] = confidence
            if timeframe:
                trend_item["timeframe"] = timeframe
            normalized.append(trend_item)

        return normalized

    def normalize_daily_report_payload(self, payload: Any) -> Dict[str, Any]:
        data = payload if isinstance(payload, dict) else {}
        date_text = self._to_text(data.get("date")) or datetime.now().strftime("%Y-%m-%d")

        executive_summary = (
            self._to_text(data.get("executiveSummary"))
            or self._to_text(data.get("summary"))
            or self._to_text(data.get("executive_summary"))
        )
        economic_analysis = (
            self._to_text(data.get("economicAnalysis"))
            or self._to_text(data.get("macroAnalysis"))
            or self._to_text(data.get("macro"))
        )
        if not executive_summary:
            executive_summary = economic_analysis[:160] if economic_analysis else "暂无明确主线，建议关注后续数据更新。"
        if not economic_analysis:
            economic_analysis = executive_summary

        agent_insights_raw = data.get("agentInsights")
        agent_insights = None
        if isinstance(agent_insights_raw, dict):
            macro = self._to_text(agent_insights_raw.get("macro")) or None
            sentiment = self._to_text(agent_insights_raw.get("sentiment")) or None
            if macro or sentiment:
                agent_insights = {"macro": macro, "sentiment": sentiment}

        normalized: Dict[str, Any] = {
            "date": date_text,
            "intelligenceDigest": self._normalize_intelligence_digest(data.get("intelligenceDigest")),
            "executiveSummary": executive_summary,
            "globalEvents": self._normalize_global_events(data.get("globalEvents") or data.get("majorEvents")),
            "economicAnalysis": economic_analysis,
            "investmentTrends": self._normalize_investment_trends(data.get("investmentTrends")),
        }
        if agent_insights:
            normalized["agentInsights"] = agent_insights

        risk_assessment = self._to_text(data.get("riskAssessment") or data.get("risk")) or None
        source_analysis = self._to_text(data.get("sourceAnalysis")) or None
        if risk_assessment:
            normalized["riskAssessment"] = risk_assessment
        if source_analysis:
            normalized["sourceAnalysis"] = source_analysis

        return normalized

    def _active_providers(self) -> List[Dict[str, str]]:
        providers = [
            {"name": "Primary", "url": CONFIG.ai_api_url, "key": CONFIG.ai_api_key, "model": CONFIG.ai_model},
            {"name": "Fallback", "url": CONFIG.ai_fallback_url, "key": CONFIG.ai_fallback_key, "model": CONFIG.ai_fallback_model},
        ]
        return [p for p in providers if p["url"] and p["key"]]

    def _provider_base_url(self, url: str) -> str:
        return re.sub(r"/chat/completions/?$", "", url.strip())

    def _window_cache_key(self, base_url: str, model: str) -> str:
        return f"{base_url}::{model}"

    def _extract_context_window(self, payload: Any) -> Optional[int]:
        queue: List[Any] = [payload]
        visited = 0
        while queue and visited < 1000:
            current = queue.pop(0)
            visited += 1
            if isinstance(current, dict):
                for k, v in current.items():
                    key = str(k).lower()
                    if key in WINDOW_FIELD_CANDIDATES:
                        try:
                            n = int(v)
                            if n > 0:
                                return n
                        except Exception:
                            pass
                    if isinstance(v, (dict, list)):
                        queue.append(v)
            elif isinstance(current, list):
                queue.extend(current)
        return None

    async def _fetch_provider_model_window(self, provider: Dict[str, str]) -> Optional[int]:
        base_url = self._provider_base_url(provider["url"])
        cache_key = self._window_cache_key(base_url, provider["model"])
        now = time.time()
        cached = self._window_cache.get(cache_key)
        if cached and cached["expires_at"] > now:
            return cached["window"]

        window = None
        try:
            client = AsyncOpenAI(api_key=provider["key"], base_url=base_url)
            meta = await client.models.retrieve(provider["model"])
            payload = meta.model_dump() if hasattr(meta, "model_dump") else dict(meta)
            window = self._extract_context_window(payload)
        except Exception as e:
            logger.warning(f"{provider['name']} 模型窗口元数据获取失败 ({provider['model']}): {e}")

        if window is None:
            window = MODEL_CONTEXT_WINDOW_FALLBACKS.get(provider["model"])
            if window:
                logger.warning(f"{provider['name']} 使用模型窗口映射回退: model={provider['model']}, window={window}")

        if window is None:
            window = DEFAULT_CONTEXT_WINDOW
            logger.warning(f"{provider['name']} 使用默认模型窗口回退: model={provider['model']}, window={window}")

        self._window_cache[cache_key] = {
            "window": window,
            "expires_at": now + WINDOW_CACHE_TTL_SEC,
        }
        return window

    async def _resolve_shared_context_window(self) -> Tuple[int, Dict[str, int]]:
        providers = self._active_providers()
        if not providers:
            return DEFAULT_CONTEXT_WINDOW, {}

        windows: Dict[str, int] = {}
        for provider in providers:
            window = await self._fetch_provider_model_window(provider)
            windows[f"{provider['name']}:{provider['model']}"] = window
        return min(windows.values()), windows

    def _compute_input_budget(self, context_window: int) -> Dict[str, int]:
        reserve = int(context_window * OUTPUT_RESERVE_RATIO)
        reserve = max(OUTPUT_RESERVE_MIN, min(reserve, OUTPUT_RESERVE_MAX))
        raw_usable = context_window - reserve - SAFETY_MARGIN - PROMPT_OVERHEAD
        max_possible = max(512, context_window - OUTPUT_RESERVE_MIN)
        usable_input = max(512, min(raw_usable, max_possible))
        if usable_input < MIN_WORKING_INPUT and max_possible >= MIN_WORKING_INPUT:
            usable_input = MIN_WORKING_INPUT
        return {
            "context_window": context_window,
            "output_reserve": reserve,
            "safety_margin": SAFETY_MARGIN,
            "prompt_overhead": PROMPT_OVERHEAD,
            "usable_input": usable_input,
        }

    def _compose_raw_context(self, news_context: str, cluster_context: str) -> str:
        return "\n".join([p for p in [news_context, cluster_context] if p])

    def _build_cluster_context(self, clusters: Optional[List[ClusteredEvent]], budget: int) -> Tuple[str, int]:
        if not clusters or budget <= 0:
            return "", 0
        cluster_ctx = generate_cluster_context(clusters)
        if not cluster_ctx:
            return "", 0
        trimmed = truncate_to_token_budget(cluster_ctx, budget)
        return trimmed, estimate_tokens(trimmed)

    def _build_final_strategist_input(
        self,
        raw_context: str,
        macro_out: str,
        sentiment_out: str,
        market_price_context: str
    ) -> str:
        return FINAL_STRATEGIST_PROMPT.format(
            raw_context=raw_context,
            macro_out=macro_out,
            sentiment_out=sentiment_out,
            market_price_context=market_price_context,
        )

    def _guard_final_strategist_input(
        self,
        news_list: List[NewsRecord],
        clusters: Optional[List[ClusteredEvent]],
        macro_out: str,
        sentiment_out: str,
        market_price_context: str,
        usable_budget: int,
        news_context: str,
        cluster_context: str,
    ) -> Tuple[str, Dict[str, Any]]:
        initial_input = self._build_final_strategist_input(
            self._compose_raw_context(news_context, cluster_context),
            macro_out,
            sentiment_out,
            market_price_context,
        )
        pre_tokens = estimate_tokens(initial_input)
        news_tokens = estimate_tokens(news_context)
        cluster_tokens = estimate_tokens(cluster_context) if cluster_context else 0
        context_tokens = news_tokens + cluster_tokens
        fixed_tokens = estimate_tokens(self._build_final_strategist_input("", macro_out, sentiment_out, market_price_context))
        max_context_tokens = max(0, usable_budget - fixed_tokens)
        trimmed_sections: List[str] = []

        if context_tokens > max_context_tokens:
            # 优先压缩新闻尾部（低优先级内容通常在后部）
            target_news = max(0, max_context_tokens - cluster_tokens)
            if target_news < news_tokens:
                news_context, news_tokens = self.build_news_context(news_list, target_news)
                trimmed_sections.append("news-low-priority")
                context_tokens = news_tokens + cluster_tokens

        if context_tokens > max_context_tokens and cluster_tokens > 0:
            # 再压缩聚类上下文
            target_cluster = max(0, max_context_tokens - news_tokens)
            if target_cluster < cluster_tokens:
                cluster_context, cluster_tokens = self._build_cluster_context(clusters, target_cluster)
                trimmed_sections.append("cluster")
                context_tokens = news_tokens + cluster_tokens

        if context_tokens > max_context_tokens:
            # 最后继续压缩新闻（可能影响高优先级内容）
            target_news = max(0, max_context_tokens - cluster_tokens)
            if target_news < news_tokens:
                news_context, news_tokens = self.build_news_context(news_list, target_news)
                trimmed_sections.append("news-high-priority")

        guarded_raw_context = self._compose_raw_context(news_context, cluster_context)
        final_input = self._build_final_strategist_input(guarded_raw_context, macro_out, sentiment_out, market_price_context)
        post_tokens = estimate_tokens(final_input)

        if post_tokens > usable_budget:
            final_input = truncate_to_token_budget(final_input, usable_budget)
            trimmed_sections.append("final-hard-cap")
            post_tokens = estimate_tokens(final_input)

        return final_input, {
            "pre_guard_tokens": pre_tokens,
            "post_guard_tokens": post_tokens,
            "trimmed_sections": trimmed_sections,
        }

    async def generate_daily_report(
        self,
        news_list: List[NewsRecord],
        clusters: List[ClusteredEvent] = None
    ) -> DailyReport:
        """多智能体研报生成流"""
        self.last_report_guard_stats = {}
        self.last_report_metrics = {}
        shared_window, provider_windows = await self._resolve_shared_context_window()
        budget = self._compute_input_budget(shared_window)
        usable_input = budget["usable_input"]

        has_cluster = bool(clusters)
        news_alloc = int(usable_input * 0.65)
        cluster_alloc = int(usable_input * 0.20) if has_cluster else 0

        news_context, news_used = self.build_news_context(news_list, news_alloc)
        cluster_context, cluster_used = self._build_cluster_context(clusters, cluster_alloc)

        # 剩余预算回流：news > cluster
        remaining = max(0, usable_input - (news_used + cluster_used))
        if remaining > 0:
            boosted_news_context, boosted_news_used = self.build_news_context(news_list, news_used + remaining)
            gained_news = max(0, boosted_news_used - news_used)
            news_context, news_used = boosted_news_context, boosted_news_used
            remaining = max(0, remaining - gained_news)
        if remaining > 0 and has_cluster:
            boosted_cluster_context, boosted_cluster_used = self._build_cluster_context(clusters, cluster_used + remaining)
            cluster_context, cluster_used = boosted_cluster_context, boosted_cluster_used

        raw_context = self._compose_raw_context(news_context, cluster_context)
        logger.info(
            f"AI预算摘要: windows={provider_windows}, baseline={shared_window}, "
            f"reserve={budget['output_reserve']}, safety={budget['safety_margin']}, usable={usable_input}"
        )
        logger.info(
            f"上下文分配: news_alloc={news_alloc}/used={news_used}, "
            f"cluster_alloc={cluster_alloc}/used={cluster_used}"
        )

        # ── 多智能体并行流程 ──
        logger.info("启动多智能体并发推理...")
        market_price_context = await self.build_market_price_context()

        tasks = [
            self.call_agent("MacroAnalyst", MACRO_ANALYST_PROMPT, raw_context),
            self.call_agent("SentimentAnalyst", SENTIMENT_ANALYST_PROMPT, raw_context)
        ]
        
        macro_out, sentiment_out = await asyncio.gather(*tasks)

        # ── 首席战略官 (Market Strategist) 整合 ──
        logger.info("启动首席战略官整合研报...")
        final_strategist_input, guard_stats = self._guard_final_strategist_input(
            news_list=news_list,
            clusters=clusters,
            macro_out=macro_out,
            sentiment_out=sentiment_out,
            market_price_context=market_price_context,
            usable_budget=usable_input,
            news_context=news_context,
            cluster_context=cluster_context,
        )
        logger.info(
            f"Strategist guard: pre={guard_stats['pre_guard_tokens']}, "
            f"post={guard_stats['post_guard_tokens']}, trimmed={guard_stats['trimmed_sections']}"
        )
        final_raw = await self.call_agent("MarketStrategist", MARKET_STRATEGIST_PROMPT, final_strategist_input, use_json=True)
        parsed_json = await self.parse_daily_report_json(final_raw)
        report = DailyReport(**parsed_json)
        self.last_report_guard_stats = dict(guard_stats)
        self.last_report_metrics = build_report_metrics(
            raw_news_input_count=len(news_list),
            cluster_count=len(clusters or []),
            report_generated=True,
            investment_trend_count=len(report.investmentTrends),
            guard_stats=guard_stats,
        )
        
        # 写入预测闭环（失败不影响主流程）
        await self._persist_predictions(report)

        return report

    async def build_market_price_context(self) -> str:
        """构建实时市场上下文，失败时自动回退到占位文本。"""
        symbols = get_default_market_symbols(limit=CONFIG.ai_market_context_symbols_limit)
        if not symbols:
            symbols = ["GC=F", "CL=F"]

        fallback_symbols = symbols[: min(3, len(symbols))]
        fallback = "[REAL-TIME MARKET DATA]\n" + "\n".join(
            f"- {symbol}: unavailable" for symbol in fallback_symbols
        )

        if not CONFIG.ai_use_realtime_market_context:
            return fallback

        tasks = [asyncio.wait_for(get_market_price(sym), timeout=8) for sym in symbols]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        lines = ["[REAL-TIME MARKET DATA]"]
        has_data = False
        for symbol, result in zip(symbols, results):
            if isinstance(result, Exception):
                logger.debug(f"市场数据获取失败 {symbol}: {result}")
                continue

            price = result.get("price")
            change = result.get("changePercent")
            if price is None:
                continue

            has_data = True
            if change is not None:
                lines.append(f"- {symbol}: {price} ({change:+.2f}%)")
            else:
                lines.append(f"- {symbol}: {price}")

        return "\n".join(lines) if has_data else fallback

    async def _persist_predictions(self, report: DailyReport):
        if not CONFIG.report_auto_save_predictions:
            return

        saved = 0
        skipped = 0
        for trend in report.investmentTrends:
            try:
                symbol = await self.resolve_asset_symbol_auto(trend.assetClass)
                if not symbol:
                    skipped += 1
                    continue

                market = await asyncio.wait_for(get_market_price(symbol), timeout=10)
                await self.db.save_prediction({
                    "asset": symbol,
                    "type": trend.trend.lower(),
                    "reasoning": trend.rationale,
                    "price": market["price"],
                    "timestamp": datetime.now(timezone.utc).isoformat()
                })
                saved += 1
            except Exception as e:
                skipped += 1
                logger.warning(f"预测持久化失败 {trend.assetClass}/{symbol}: {e}")

        if saved > 0 or skipped > 0:
            logger.info(f"预测持久化完成: saved={saved}, skipped={skipped}")

    async def resolve_asset_symbol_auto(self, asset_class: str) -> Optional[str]:
        normalized = (asset_class or "").strip().lower()
        if not normalized:
            return None

        if normalized in self._asset_symbol_cache:
            return self._asset_symbol_cache[normalized]

        symbol = resolve_asset_symbol(asset_class)
        if symbol:
            self._asset_symbol_cache[normalized] = symbol
            return symbol

        if not CONFIG.ai_symbol_search_enabled:
            self._asset_symbol_cache[normalized] = None
            return None

        timeout_sec = max(CONFIG.ai_symbol_search_timeout_ms, 1000) / 1000
        try:
            symbol = await asyncio.wait_for(search_market_symbol(asset_class), timeout=timeout_sec)
        except Exception as e:
            logger.debug(f"自动解析 symbol 失败 '{asset_class}': {e}")
            symbol = None
        self._asset_symbol_cache[normalized] = symbol
        return symbol

    async def parse_daily_report_json(self, raw_text: str) -> Dict[str, Any]:
        """解析日报 JSON；若失败，自动触发一次修复重试。"""
        try:
            parsed = json.loads(extract_json(raw_text))
            return self.normalize_daily_report_payload(parsed)
        except json.JSONDecodeError as e:
            logger.warning(f"MarketStrategist JSON 解析失败，尝试修复: {e}")

        repaired_raw = await self.repair_daily_report_json(raw_text)
        try:
            parsed = json.loads(extract_json(repaired_raw))
            return self.normalize_daily_report_payload(parsed)
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
        providers = self._active_providers()

        for p in providers:
            try:
                # 重新初始化 client 以支持不同 provider 的 base_url
                client = AsyncOpenAI(api_key=p["key"], base_url=self._provider_base_url(p["url"]))
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
                logger.warning(f"{name} 调用失败 ({p['name']}/{p['model']}): {e}")
                continue
        
        raise Exception(f"{name} 所有提供商调用均失败")

    def build_news_context(self, news_list: List[NewsRecord], budget: int) -> Tuple[str, int]:
        if budget <= 0:
            return "", 0
        lines = []
        used = 0
        for i, n in enumerate(news_list):
            label = THREAT_LABELS.get(n.threatLevel, '')
            header = f"[{i+1}] {label} {n.title} ({n.category}, T{n.tier})"
            
            entry = header
            if n.content and len(n.content) > 80:
                is_high_priority = (n.tier is not None and n.tier <= 2) or (n.threatLevel in {"critical", "high"})
                excerpt_len = 360 if is_high_priority else 220
                excerpt = re.sub(r'\s+', ' ', n.content[:excerpt_len]).strip()
                entry += f"\n  ▸ {excerpt}"
            
            entry_tokens = estimate_tokens(entry)
            if used + entry_tokens <= budget:
                lines.append(entry)
                used += entry_tokens
                continue

            header_tokens = estimate_tokens(header)
            if used + header_tokens > budget:
                break

            # 预算不足时回退为仅标题，提升保留事件数量
            lines.append(header)
            used += header_tokens
        return "\n".join(lines), used
