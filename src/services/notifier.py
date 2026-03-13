import aiohttp
import httpx
import asyncio
from collections.abc import Mapping, Sequence
from html import escape
from typing import Any
from ..config.settings import CONFIG
from .report_models import DailyReport
from .threat_labels import THREAT_LABELS
from ..utils.logger import get_logger

logger = get_logger("notifier")

STATE_CHANGE_ICONS = {
    "new": "🆕",
    "updated": "🔄",
    "escalated": "⚡",
    "resolved": "✅",
}

EVENT_TYPE_ICONS = {
    "conflict": "⚔️",
    "supply_disruption": "🚢",
    "central_bank": "🏦",
    "macro_data": "📊",
    "cyber": "🔒",
    "policy": "📜",
}

async def retry_with_backoff(fn, label: str, max_retries: int = 3, base_delay: int = 1):
    last_error = None
    for attempt in range(max_retries + 1):
        try:
            return await fn()
        except Exception as e:
            last_error = e
            if attempt < max_retries:
                delay = base_delay * (2 ** attempt)
                logger.warning(f"[Retry] {label} 第 {attempt + 1}/{max_retries} 次失败，{delay}s 后重试: {e}")
                await asyncio.sleep(delay)
    raise last_error

class Notifier:
    def __init__(self):
        self.feishu_url = CONFIG.feishu_webhook
        self.tg_token = CONFIG.telegram_bot_token
        self.tg_chat_id = CONFIG.telegram_chat_id
        self.proxy = CONFIG.https_proxy if CONFIG.https_proxy else None

    async def deliver_all(self, report: DailyReport, news_count: int, cluster_count: int):
        tasks = []
        if self.feishu_url:
            tasks.append(retry_with_backoff(
                lambda: self.send_to_feishu(report, news_count, cluster_count), 
                "Feishu"
            ))
        if self.tg_token and self.tg_chat_id:
            tasks.append(retry_with_backoff(
                lambda: self.send_to_telegram(report), 
                "Telegram"
            ))
        
        if not tasks:
            logger.warning("未配置通知渠道，跳过推送。")
            return

        results = await asyncio.gather(*tasks, return_exceptions=True)
        for i, res in enumerate(results):
            if isinstance(res, Exception):
                logger.error(f"通知渠道 {i} 推送失败: {res}")

    async def send_to_feishu(self, report: DailyReport, news_count: int, cluster_count: int):
        md = f"**🌊 核心主线 | Executive Summary**\n{report.executiveSummary}\n\n"
        macro_chain = self._report_mapping(getattr(report, "macroTransmissionChain", None))
        asset_breakdowns = self._report_mapping_list(
            getattr(report, "assetTransmissionBreakdowns", None)
        )

        if macro_chain:
            md += "**🔗 总主线传导链 | Macro Transmission**\n"
            headline = self._text(macro_chain.get("headline"))
            shock_source = self._text(macro_chain.get("shockSource"))
            macro_variables = self._text_list(macro_chain.get("macroVariables"))
            market_pricing = self._text(macro_chain.get("marketPricing"))
            allocation = self._text(macro_chain.get("allocationImplication"))
            steps = self._report_mapping_list(macro_chain.get("steps"))
            if headline:
                md += f"**主线**: {headline}\n"
            if shock_source:
                md += f"**冲击源**: {shock_source}\n"
            if macro_variables:
                md += f"**宏观变量**: {'、'.join(macro_variables[:4])}\n"
            if market_pricing:
                md += f"**市场定价**: {market_pricing}\n"
            if allocation:
                md += f"**配置含义**: {allocation}\n"
            for idx, step in enumerate(steps[:4], start=1):
                stage = self._text(step.get("stage")) or "链路节点"
                driver = self._text(step.get("driver"))
                if driver:
                    md += f"{idx}. **{stage}**: {driver}\n"
            md += "\n"
        
        if report.intelligenceDigest:
            md += "**📋 情报摘要 | Intelligence Digest**\n"
            imp_icon = {'critical': '🔴', 'high': '🟠', 'medium': '🟡', 'low': '🟢'}
            cred_label = {'high': '✅高', 'medium': '⚠️中', 'low': '❓低'}
            for i, item in enumerate(report.intelligenceDigest[:8]):
                imp = imp_icon.get(item.importance, '⚪')
                cred = cred_label.get(item.credibility, '❓')
                srcs = "、".join([f"{s.name}(T{s.tier})" for s in item.sources])
                md += f"**{i+1}. {imp} {item.content}**\n  来源: {srcs} | 可信度: {cred}\n  {item.credibilityReason}\n\n"

        md += f"**🌍 重大事件 | Key Events** *({cluster_count} 个聚类事件)*\n"
        for i, e in enumerate(report.globalEvents[:10]):
            icon = THREAT_LABELS.get(e.threatLevel, '') + ' ' if e.threatLevel else ''
            md += f"**{i+1}. {icon}{e.title}**\n{e.detail}\n\n"

        md += f"**📈 宏观趋势深度研判 | Deep Insights**\n{report.economicAnalysis}\n\n"

        if asset_breakdowns:
            md += "**🎯 关键资产拆解 | Asset Breakdown**\n"
            for item in asset_breakdowns[:4]:
                asset_class = self._text(item.get("assetClass")) or "Macro Basket"
                trend = self._text(item.get("trend")) or "Neutral"
                icon = '🟢 看涨' if trend == 'Bullish' else ('🔴 看跌' if trend == 'Bearish' else '⚪ 中性')
                confidence = self._text(item.get("confidence"))
                timeframe = self._text(item.get("timeframe"))
                suffix = f" ({confidence}%)" if confidence else ""
                if timeframe:
                    suffix += f" [{timeframe}]"
                md += f"- **{asset_class}** ({icon}{suffix})\n"
                core_view = self._text(item.get("coreView"))
                transmission_path = self._text(item.get("transmissionPath"))
                pair_trade = self._text(item.get("pairTrade"))
                scenario = self._report_mapping(item.get("scenarioAnalysis"))
                key_drivers = self._text_list(item.get("keyDrivers"))
                watch_signals = self._text_list(item.get("watchSignals"))
                if core_view:
                    md += f"  > 核心观点: {core_view}\n"
                if transmission_path:
                    md += f"  传导路径: {transmission_path}\n"
                if pair_trade:
                    md += f"  💡 **配对建议**: `{pair_trade}`\n"
                if scenario:
                    bull = self._text(scenario.get("bullCase"))
                    bear = self._text(scenario.get("bearCase"))
                    if bull or bear:
                        md += "  🔭 **场景推演**:\n"
                        if bull: md += f"    - 🟢 Bull: {bull}\n"
                        if bear: md += f"    - 🔴 Bear: {bear}\n"
                if key_drivers:
                    md += f"  驱动: {'、'.join(key_drivers[:4])}\n"
                if watch_signals:
                    md += f"  观察点: {'、'.join(watch_signals[:3])}\n"
            md += "\n"

        md += "**💼 资产配置与投资风向 | Investment Strategy**\n"
        for t in report.investmentTrends:
            icon = '🟢 看涨' if t.trend == 'Bullish' else ('🔴 看跌' if t.trend == 'Bearish' else '⚪ 中性')
            conf = f" ({t.confidence}%)" if t.confidence else ""
            tf = f" [{t.timeframe}]" if t.timeframe else ""
            md += f"- **{t.assetClass}** ({icon}{conf}{tf}): {t.rationale}\n"

        if report.riskAssessment:
            md += f"\n**⚠️ 风险评估 | Risk Assessment**\n{report.riskAssessment}\n"

        md += f"\n---\n*DeepCurrents Python (v2.2) | 样本源: {news_count} 条 → {cluster_count} 事件 | {report.date}*"

        card = {
            "msg_type": "interactive",
            "card": {
                "config": {"wide_screen_mode": True},
                "header": {
                    "title": {"content": "🌊 DeepCurrents: 每日全球情报与宏观策略", "tag": "plain_text"},
                    "template": "indigo"
                },
                "elements": [{"tag": "markdown", "content": md}]
            }
        }

        # Feishu 通常不需要海外代理，直接发送
        async with aiohttp.ClientSession() as session:
            async with session.post(self.feishu_url, json=card) as resp:
                if resp.status != 200:
                    text = await resp.text()
                    raise Exception(f"Feishu API error: {text}")

    async def deliver_events(
        self,
        event_briefs: Sequence[Mapping[str, Any]],
        *,
        report_date: str = "",
    ):
        tasks = []
        if self.feishu_url:
            tasks.append(retry_with_backoff(
                lambda: self.send_events_to_feishu(event_briefs, report_date=report_date),
                "Feishu-Events",
            ))
        if not tasks:
            logger.warning("未配置通知渠道，跳过事件推送。")
            return

        results = await asyncio.gather(*tasks, return_exceptions=True)
        for i, res in enumerate(results):
            if isinstance(res, Exception):
                logger.error(f"事件推送渠道 {i} 失败: {res}")

    async def send_events_to_feishu(
        self,
        event_briefs: Sequence[Mapping[str, Any]],
        *,
        report_date: str = "",
    ):
        md = ""
        for i, brief_row in enumerate(event_briefs):
            brief_json = self._brief_json(brief_row)
            title = self._text(brief_json.get("canonicalTitle"))
            if not title:
                continue

            state_change = self._text(brief_json.get("stateChange"))
            event_type = self._text(brief_json.get("eventType"))
            why = self._text(brief_json.get("whyItMatters"))
            total_score = self._safe_float(brief_json.get("totalScore"))
            confidence = self._safe_float(brief_json.get("confidence"))
            channels = self._text_list(brief_json.get("marketChannels"))
            regions = self._text_list(brief_json.get("regions"))
            assets = self._text_list(brief_json.get("assets"))
            novelty = self._text(brief_json.get("novelty"))
            corroboration = self._text(brief_json.get("corroboration"))
            contradictions = brief_json.get("contradictions") or []
            status = self._text(brief_json.get("status"))

            state_icon = STATE_CHANGE_ICONS.get(state_change, "🔹")
            type_icon = EVENT_TYPE_ICONS.get(event_type, "📌")

            md += f"**{i+1}. {state_icon} {type_icon} {title}**\n"
            if status:
                md += f"  状态: {status}"
                if state_change:
                    md += f" → {state_change}"
                md += "\n"
            md += f"  📊 综合评分: {total_score:.3f} | 置信度: {confidence:.2f}"
            if novelty:
                md += f" | 新颖性: {novelty}"
            if corroboration:
                md += f" | 佐证: {corroboration}"
            md += "\n"
            if why:
                md += f"  💡 {why}\n"
            scope_parts = []
            if channels:
                scope_parts.append(f"渠道: {', '.join(channels[:3])}")
            if regions:
                scope_parts.append(f"区域: {', '.join(regions[:3])}")
            if assets:
                scope_parts.append(f"资产: {', '.join(assets[:3])}")
            if scope_parts:
                md += f"  🌍 {' | '.join(scope_parts)}\n"
            if contradictions:
                md += f"  ⚠️ 存在 {len(contradictions)} 条矛盾信息\n"
            md += "\n"

        if not md:
            logger.warning("事件速报内容为空，跳过飞书推送。")
            return

        date_text = report_date or "latest"
        footer = f"\n---\n*DeepCurrents 事件速报 | 共 {len(event_briefs)} 个核心事件 | {date_text}*"

        card = {
            "msg_type": "interactive",
            "card": {
                "config": {"wide_screen_mode": True},
                "header": {
                    "title": {"content": "🔥 DeepCurrents: 核心事件速报", "tag": "plain_text"},
                    "template": "red",
                },
                "elements": [{"tag": "markdown", "content": md + footer}],
            },
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(self.feishu_url, json=card) as resp:
                if resp.status != 200:
                    text = await resp.text()
                    raise Exception(f"Feishu Events API error: {text}")

    @staticmethod
    def _brief_json(row: Any) -> dict[str, Any]:
        if isinstance(row, Mapping):
            bj = row.get("brief_json")
            if isinstance(bj, Mapping):
                return dict(bj)
            return dict(row)
        return {}

    @staticmethod
    def _text(value: Any) -> str:
        if value is None:
            return ""
        if isinstance(value, str):
            return value.strip()
        return str(value).strip()

    @staticmethod
    def _safe_float(value: Any) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return 0.0

    @staticmethod
    def _text_list(value: Any) -> list[str]:
        if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
            return []
        return [str(item).strip() for item in value if str(item).strip()]

    @staticmethod
    def _report_mapping(value: Any) -> dict[str, Any]:
        if isinstance(value, Mapping):
            return dict(value)
        if hasattr(value, "model_dump"):
            dumped = value.model_dump()
            if isinstance(dumped, Mapping):
                return dict(dumped)
        return {}

    @classmethod
    def _report_mapping_list(cls, value: Any) -> list[dict[str, Any]]:
        if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
            return []
        result: list[dict[str, Any]] = []
        for item in value:
            mapping = cls._report_mapping(item)
            if mapping:
                result.append(mapping)
        return result

    async def send_to_telegram(self, report: DailyReport):
        text = f"🌊 <b>DeepCurrents Daily Intelligence</b>\n📅 {escape(report.date)}\n\n"
        text += f"<b>核心主线:</b> {escape(report.executiveSummary)}\n\n"
        macro_chain = self._report_mapping(getattr(report, "macroTransmissionChain", None))
        asset_breakdowns = self._report_mapping_list(
            getattr(report, "assetTransmissionBreakdowns", None)
        )
        if macro_chain.get("headline"):
            text += f"<b>总主线传导链:</b> {escape(self._text(macro_chain.get('headline')))}\n"
            market_pricing = self._text(macro_chain.get("marketPricing"))
            if market_pricing:
                text += f"{escape(market_pricing)}\n\n"
        
        text += "<b>📊 重大事件:</b>\n"
        for i, e in enumerate(report.globalEvents[:5]):
            text += f"{i + 1}. <b>{escape(e.title)}</b>\n"

        if asset_breakdowns:
            text += "\n<b>🎯 关键资产拆解:</b>\n"
            for item in asset_breakdowns[:2]:
                asset_class = self._text(item.get("assetClass")) or "Macro Basket"
                core_view = self._text(item.get("coreView"))
                text += f"• <b>{escape(asset_class)}</b>: {escape(core_view)}\n"

        text += "\n<b>💼 资产研判:</b>\n"
        for t in report.investmentTrends:
            icon = '📈' if t.trend == 'Bullish' else ('📉' if t.trend == 'Bearish' else '➡️')
            text += f"{icon} <b>{escape(t.assetClass)}</b>: {escape(t.trend)}\n"

        url = f"https://api.telegram.org/bot{self.tg_token}/sendMessage"
        payload = {
            "chat_id": self.tg_chat_id,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": True
        }

        # Telegram 使用 httpx 以支持 SOCKS/HTTP 代理
        async with httpx.AsyncClient(proxy=self.proxy) as client:
            resp = await client.post(url, json=payload, timeout=20.0)
            if resp.status_code != 200:
                raise Exception(f"Telegram API error: {resp.status_code} - {resp.text}")
