import aiohttp
import asyncio
from typing import Dict, Any, List
from ..config.settings import CONFIG
from .ai_service import DailyReport
from .classifier import THREAT_LABELS
from ..utils.logger import get_logger

logger = get_logger("notifier")

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

        async with aiohttp.ClientSession() as session:
            async with session.post(self.feishu_url, json=card) as resp:
                if resp.status != 200:
                    text = await resp.text()
                    raise Exception(f"Feishu API error: {text}")

    async def send_to_telegram(self, report: DailyReport):
        text = f"🌊 *DeepCurrents Daily Intelligence*\n📅 {report.date}\n\n"
        text += f"*核心主线:* {report.executiveSummary}\n\n"
        
        text += "*📊 重大事件:*\n"
        for i, e in enumerate(report.globalEvents[:5]):
            # 对 MarkdownV2 进行简单的字符转义
            title = e.title.replace('.', '\\.').replace('-', '\\-')
            text += f"{i+1}\\. *{title}*\n"

        text += "\n*💼 资产研判:*\n"
        for t in report.investmentTrends:
            icon = '📈' if t.trend == 'Bullish' else ('📉' if t.trend == 'Bearish' else '➡️')
            text += f"{icon} *{t.assetClass}*: {t.trend}\n"

        url = f"https://api.telegram.org/bot{self.tg_token}/sendMessage"
        payload = {
            "chat_id": self.tg_chat_id,
            "text": text,
            "parse_mode": "Markdown"
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload) as resp:
                if resp.status != 200:
                    text = await resp.text()
                    raise Exception(f"Telegram API error: {text}")
