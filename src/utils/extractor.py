"""Full-text extraction: trafilatura -> readability-lxml -> BeautifulSoup cascade."""

from __future__ import annotations

import asyncio
from typing import Any, Dict, Optional

import aiohttp
from bs4 import BeautifulSoup

from ..utils.logger import get_logger
from ..utils.network import resolve_request_proxy

logger = get_logger("extractor")

_trafilatura: Any = None
_readability_Document: Any = None


def _ensure_trafilatura() -> Any:
    global _trafilatura
    if _trafilatura is None:
        try:
            import trafilatura

            _trafilatura = trafilatura
        except ImportError:
            _trafilatura = False
    return _trafilatura if _trafilatura is not False else None


def _ensure_readability() -> Any:
    global _readability_Document
    if _readability_Document is None:
        try:
            from readability import Document

            _readability_Document = Document
        except ImportError:
            _readability_Document = False
    return _readability_Document if _readability_Document is not False else None


class ExtractionResult:
    __slots__ = ("title", "content", "method", "content_length")

    def __init__(self, title: str, content: str, method: str) -> None:
        self.title = title
        self.content = content
        self.method = method
        self.content_length = len(content)

    def to_dict(self) -> Dict[str, str]:
        return {
            "title": self.title,
            "content": self.content,
            "extraction_method": self.method,
        }


def _extract_trafilatura(html: str) -> Optional[ExtractionResult]:
    traf = _ensure_trafilatura()
    if traf is None:
        return None
    try:
        text = traf.extract(
            html,
            include_comments=False,
            include_tables=True,
            no_fallback=False,
            favor_precision=False,
            favor_recall=True,
            deduplicate=True,
        )
        if not text or len(text.strip()) < 50:
            return None

        metadata = traf.extract_metadata(html)
        title = ""
        if metadata:
            title = getattr(metadata, "title", "") or ""

        return ExtractionResult(
            title=title,
            content=text.strip(),
            method="trafilatura",
        )
    except Exception as exc:
        logger.debug(f"trafilatura extraction failed: {exc}")
        return None


def _extract_readability(html: str) -> Optional[ExtractionResult]:
    Document = _ensure_readability()
    if Document is None:
        return None
    try:
        doc = Document(html)
        title = doc.short_title() or ""
        summary_html = doc.summary()

        soup = BeautifulSoup(summary_html, "lxml")
        text = soup.get_text(separator="\n", strip=True)

        if not text or len(text) < 50:
            return None

        return ExtractionResult(
            title=title,
            content=text,
            method="readability",
        )
    except Exception as exc:
        logger.debug(f"readability extraction failed: {exc}")
        return None


def _extract_bs4_fallback(html: str) -> Optional[ExtractionResult]:
    try:
        parser = "xml" if html.lstrip().startswith("<?xml") else "lxml"
        soup = BeautifulSoup(html, parser)

        title = soup.title.string if soup.title else ""

        for tag in soup(["script", "style", "nav", "header", "footer", "aside"]):
            tag.decompose()

        paragraphs = soup.find_all("p")
        content = "\n".join(
            p.get_text().strip() for p in paragraphs if len(p.get_text().strip()) > 20
        )

        if len(content) < 100:
            content = soup.get_text(separator="\n", strip=True)

        lines = (line.strip() for line in content.splitlines())
        chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
        text = "\n".join(chunk for chunk in chunks if chunk)

        if not text or len(text) < 30:
            return None

        return ExtractionResult(
            title=title or "",
            content=text,
            method="bs4_fallback",
        )
    except Exception as exc:
        logger.debug(f"bs4 fallback extraction failed: {exc}")
        return None


def extract_from_html(html: str, max_length: int = 5000) -> Optional[Dict[str, str]]:
    result: Optional[ExtractionResult] = None

    result = _extract_trafilatura(html)
    if result and result.content_length >= 100:
        logger.debug(f"Extraction via {result.method}: {result.content_length} chars")
        result.content = result.content[:max_length]
        return result.to_dict()

    result = _extract_readability(html)
    if result and result.content_length >= 50:
        logger.debug(f"Extraction via {result.method}: {result.content_length} chars")
        result.content = result.content[:max_length]
        return result.to_dict()

    result = _extract_bs4_fallback(html)
    if result:
        logger.debug(f"Extraction via {result.method}: {result.content_length} chars")
        result.content = result.content[:max_length]
        return result.to_dict()

    return None


class Extractor:
    @staticmethod
    async def extract(
        url: str,
        max_length: int = 5000,
        session: Optional[aiohttp.ClientSession] = None,
        proxy: Optional[str] = None,
    ) -> Optional[Dict[str, str]]:
        try:
            managed_session = session is None
            active_session = session or aiohttp.ClientSession()
            request_proxy = resolve_request_proxy(url, proxy)
            try:
                async with active_session.get(
                    url,
                    timeout=aiohttp.ClientTimeout(total=15),
                    proxy=request_proxy,
                ) as response:
                    if response.status != 200:
                        return None
                    html = await response.text()
            finally:
                if managed_session:
                    await active_session.close()

            # CPU-intensive parsing runs in thread pool to avoid blocking event loop
            loop = asyncio.get_running_loop()
            result = await loop.run_in_executor(
                None, extract_from_html, html, max_length
            )
            return result

        except Exception as e:
            logger.debug(f"Failed to extract {url}: {e}")
            return None
