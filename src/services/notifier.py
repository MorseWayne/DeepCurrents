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

    async def send_to_telegram(self, report: DailyReport):
        text = f"🌊 <b>DeepCurrents Daily Intelligence</b>\n📅 {escape(report.date)}\n\n"
        text += f"<b>核心主线:</b> {escape(report.executiveSummary)}\n\n"
        
        text += "<b>📊 重大事件:</b>\n"
        for i, e in enumerate(report.globalEvents[:5]):
            text += f"{i + 1}. <b>{escape(e.title)}</b>\n"

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
