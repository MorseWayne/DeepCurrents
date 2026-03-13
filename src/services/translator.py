"""翻译服务：使用 DeepL 或 LibreTranslate API，不依赖 LLM"""
from __future__ import annotations

import asyncio
import time
from typing import Any

import httpx

from ..config.settings import CONFIG
from ..utils.logger import get_logger

logger = get_logger("translator")

# LibreTranslate 公共实例限速约 10 次/分钟，请求间隔需 ≥6s
LIBRE_DELAY_SEC = 6.5


async def translate_text(text: str, *, source: str = "en", target: str = "zh") -> str:
    """将单段文本翻译为中文。若未配置翻译 API 或翻译失败，返回原文。"""
    if not text or not text.strip():
        return text

    # 已是中文则跳过（简单启发式）
    if _looks_chinese(text):
        return text

    if CONFIG.deepl_api_key:
        return await _translate_deepl(text, source=source, target=target)
    if CONFIG.libretranslate_url:
        return await _translate_libre(text, source=source, target=target)

    logger.debug("未配置 DEEPL_API_KEY 或 LIBRETRANSLATE_URL，跳过翻译")
    return text


async def _translate_deepl(text: str, *, source: str, target: str) -> str:
    url = (
        "https://api-free.deepl.com/v2/translate"
        if CONFIG.deepl_api_key.endswith(":fx")
        else "https://api.deepl.com/v2/translate"
    )

    payload = {
        "text": text,
        "source_lang": source.upper(),
        "target_lang": "ZH" if target == "zh" else target.upper(),
    }
    headers = {"Authorization": f"DeepL-Auth-Key {CONFIG.deepl_api_key}"}

    try:
        async with httpx.AsyncClient(proxy=CONFIG.https_proxy or None, timeout=15.0) as client:
            resp = await client.post(url, data=payload, headers=headers)
            if resp.status_code != 200:
                logger.warning(f"DeepL 翻译失败: {resp.status_code} - {resp.text[:200]}")
                return text
            data = resp.json()
            translations = data.get("translations", [])
            if translations:
                return translations[0].get("text", text)
    except Exception as e:
        logger.warning(f"DeepL 翻译异常: {e}")
    return text


_libre_lock = asyncio.Lock()
_last_libre_ts = 0.0


async def _translate_libre(text: str, *, source: str, target: str) -> str:
    global _last_libre_ts
    async with _libre_lock:
        now = time.monotonic()
        if now - _last_libre_ts < LIBRE_DELAY_SEC:
            await asyncio.sleep(LIBRE_DELAY_SEC - (now - _last_libre_ts))

    base = CONFIG.libretranslate_url.rstrip("/")
    url = f"{base}/translate"

    payload = {"q": text, "source": source, "target": target, "format": "text"}

    try:
        async with httpx.AsyncClient(proxy=CONFIG.https_proxy or None, timeout=15.0) as client:
            resp = await client.post(url, json=payload)
            _last_libre_ts = time.monotonic()
            if resp.status_code != 200:
                logger.warning(f"LibreTranslate 翻译失败: {resp.status_code} - {resp.text[:200]}")
                return text
            data = resp.json()
            return data.get("translatedText", text)
    except Exception as e:
        logger.warning(f"LibreTranslate 翻译异常: {e}")
    return text


def _looks_chinese(s: str) -> bool:
    """简单判断文本是否主要为中文"""
    if not s:
        return False
    chinese_chars = sum(1 for c in s if "\u4e00" <= c <= "\u9fff")
    return chinese_chars / max(len(s), 1) > 0.3


async def translate_event_briefs(briefs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """批量翻译事件 brief 的 title、why、facts 字段。未配置 API 时返回原文。"""
    if not CONFIG.deepl_api_key and not CONFIG.libretranslate_url:
        logger.debug("未配置 DEEPL_API_KEY 或 LIBRETRANSLATE_URL，跳过翻译")
        return briefs

    result: list[dict[str, Any]] = []
    for brief in briefs:
        if not isinstance(brief, dict):
            result.append(brief)
            continue

        bj = brief.get("brief_json")
        if not isinstance(bj, dict):
            result.append(brief)
            continue

        new_brief = dict(brief)
        new_bj = dict(bj)

        title = new_bj.get("canonicalTitle", "")
        if title and not _looks_chinese(title):
            new_bj["canonicalTitle"] = await translate_text(title)

        why = new_bj.get("whyItMatters", "")
        if why and not _looks_chinese(why):
            new_bj["whyItMatters"] = await translate_text(why)

        facts = new_bj.get("coreFacts", [])
        if isinstance(facts, list):
            translated_facts: list[str] = []
            for f in facts:
                ft = str(f).strip() if f else ""
                if ft and not _looks_chinese(ft):
                    translated_facts.append(await translate_text(ft))
                else:
                    translated_facts.append(ft)
            new_bj["coreFacts"] = translated_facts

        new_brief["brief_json"] = new_bj
        result.append(new_brief)

    logger.info(f"事件翻译完成：{len(result)} 条")
    return result


__all__ = ["translate_text", "translate_event_briefs"]
