from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
import hashlib
import html
import re
from typing import Any, Mapping
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from bs4 import BeautifulSoup

from ..utils.tokenizer import contains_cjk, strip_source_attribution, tokenize_to_array
from .article_models import ArticleRecord


TRACKING_QUERY_PREFIXES = ("utm_",)
TRACKING_QUERY_KEYS = {
    "cmp",
    "cmpid",
    "fbclid",
    "gclid",
    "igshid",
    "mc_cid",
    "mc_eid",
    "ocid",
    "ref",
    "ref_src",
    "ref_url",
    "rss",
    "source",
    "spm",
    "taid",
}

WHITESPACE_RE = re.compile(r"\s+")
TITLE_NORMALIZE_RE = re.compile(r"[^\w\s]+", re.UNICODE)


def canonicalize_url(url: str) -> str:
    parsed = urlsplit(url.strip())
    scheme = (parsed.scheme or "https").lower()
    hostname = (parsed.hostname or "").lower()
    port = parsed.port

    if not hostname:
        return url.strip()

    if port and not (
        (scheme == "http" and port == 80) or (scheme == "https" and port == 443)
    ):
        netloc = f"{hostname}:{port}"
    else:
        netloc = hostname

    path = re.sub(r"/{2,}", "/", parsed.path or "")
    if path != "/":
        path = path.rstrip("/")

    kept_query = [
        (key, value)
        for key, value in parse_qsl(parsed.query, keep_blank_values=False)
        if not _is_tracking_query_key(key)
    ]
    query = urlencode(sorted(kept_query))

    canonical = urlunsplit((scheme, netloc, path, query, ""))
    return (
        canonical.rstrip("/") if canonical.endswith("/") and path != "/" else canonical
    )


def _is_tracking_query_key(key: str) -> bool:
    normalized = key.strip().lower()
    return (
        normalized.startswith(TRACKING_QUERY_PREFIXES)
        or normalized in TRACKING_QUERY_KEYS
    )


def _normalize_whitespace(text: str) -> str:
    return WHITESPACE_RE.sub(" ", text).strip()


def _clean_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, list):
        pieces = [
            _clean_text(item.get("value") if isinstance(item, Mapping) else item)
            for item in value
        ]
        return _normalize_whitespace(" ".join(piece for piece in pieces if piece))
    if isinstance(value, Mapping):
        return _clean_text(
            value.get("value") or value.get("content") or value.get("text")
        )

    text = html.unescape(str(value))
    if "<" in text and ">" in text:
        soup = BeautifulSoup(text, "html.parser")
        text = soup.get_text(" ", strip=True)
    return _normalize_whitespace(text)


def _normalize_title(title: str) -> str:
    cleaned = strip_source_attribution(_clean_text(title))
    normalized = TITLE_NORMALIZE_RE.sub(" ", cleaned.casefold())
    return _normalize_whitespace(normalized)


def _parse_datetime(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        dt = value
    else:
        text = _clean_text(value)
        if not text:
            return None
        iso_candidate = text.replace("Z", "+00:00")
        try:
            dt = datetime.fromisoformat(iso_candidate)
        except ValueError:
            try:
                dt = parsedate_to_datetime(text)
            except (TypeError, ValueError, IndexError, OverflowError):
                return None

    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def _coerce_source_id(raw: Mapping[str, Any], metadata: Mapping[str, Any]) -> str:
    candidate = (
        raw.get("source_id")
        or raw.get("sourceId")
        or raw.get("source")
        or metadata.get("source_id")
        or metadata.get("sourceId")
        or metadata.get("source")
        or "unknown"
    )
    slug = re.sub(r"[^a-z0-9]+", "-", _clean_text(candidate).casefold()).strip("-")
    return slug or "unknown"


def _coerce_source_type(raw: Mapping[str, Any], metadata: Mapping[str, Any]) -> str:
    candidate = raw.get("source_type") or raw.get("sourceType") or raw.get("type")
    if candidate is None:
        candidate = (
            metadata.get("source_type")
            or metadata.get("sourceType")
            or metadata.get("type")
        )
    normalized = _clean_text(candidate or "other").casefold()
    return normalized or "other"


def _coerce_tier(raw: Mapping[str, Any], metadata: Mapping[str, Any]) -> int:
    candidate = raw.get("tier", metadata.get("tier", 4))
    try:
        tier = int(candidate)
    except (TypeError, ValueError):
        return 4
    return tier if 1 <= tier <= 4 else 4


def _detect_language(*parts: str) -> str:
    text = " ".join(part for part in parts if part)
    if not text:
        return ""
    if contains_cjk(text):
        return "zh"
    if re.search(r"[a-zA-Z]", text):
        return "en"
    return ""


def _build_exact_hash(title: str, content: str) -> str:
    payload = f"{_normalize_title(title)}\n{_normalize_whitespace(content.casefold())}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _build_simhash(title: str, content: str) -> str:
    tokens = tokenize_to_array(f"{title} {content}", min_length=2)
    if not tokens:
        tokens = [token for token in _normalize_title(title).split(" ") if token]
    if not tokens:
        return "0" * 16

    vector = [0] * 64
    for token in tokens:
        digest = hashlib.md5(token.encode("utf-8")).digest()
        fingerprint = int.from_bytes(digest[:8], "big")
        for bit in range(64):
            mask = 1 << bit
            vector[bit] += 1 if fingerprint & mask else -1

    result = 0
    for bit, weight in enumerate(vector):
        if weight >= 0:
            result |= 1 << bit
    return f"{result:016x}"


def _build_article_id(canonical_url: str) -> str:
    digest = hashlib.sha1(canonical_url.encode("utf-8")).hexdigest()
    return f"art_{digest[:16]}"


def _content_quality_tier(content_length: int) -> str:
    if content_length < 200:
        return "low"
    if content_length < 800:
        return "medium"
    return "high"


def _quality_score(
    title: str, clean_content: str, published_at: datetime | None
) -> float:
    score = min(len(clean_content) / 1200.0, 1.0)
    if title:
        score += 0.1
    if published_at is not None:
        score += 0.05
    return round(min(score, 1.0), 3)


@dataclass(slots=True)
class ArticleNormalizer:
    default_source_type: str = "other"
    default_tier: int = 4

    def normalize(self, raw: Mapping[str, Any]) -> ArticleRecord:
        metadata = dict(raw.get("metadata") or raw.get("meta") or {})

        raw_url = raw.get("canonical_url") or raw.get("url") or raw.get("link") or ""
        canonical_url = canonicalize_url(_clean_text(raw_url))

        title = strip_source_attribution(
            _clean_text(raw.get("title") or raw.get("headline"))
        )
        normalized_title = _normalize_title(title)

        raw_content = (
            raw.get("content")
            or raw.get("summary")
            or raw.get("description")
            or raw.get("body")
            or ""
        )
        content = _clean_text(raw_content)
        clean_content = content

        published_at = _parse_datetime(
            raw.get("published_at")
            or raw.get("published")
            or raw.get("updated")
            or metadata.get("published_at")
        )
        ingested_at = _parse_datetime(
            raw.get("ingested_at") or metadata.get("ingested_at")
        ) or datetime.now(UTC)

        source_id = _coerce_source_id(raw, metadata)
        source_type = _coerce_source_type(raw, metadata) or self.default_source_type
        tier = _coerce_tier(raw, metadata) or self.default_tier
        language = _detect_language(title, clean_content)
        exact_hash = _build_exact_hash(title, clean_content)
        simhash = _build_simhash(normalized_title, clean_content)

        content_len = len(clean_content or content)
        content_quality = _content_quality_tier(content_len)

        record_metadata = dict(metadata)
        if raw.get("source") and "source" not in record_metadata:
            record_metadata["source"] = raw.get("source")
        record_metadata["content_quality"] = content_quality

        return ArticleRecord(
            article_id=_build_article_id(canonical_url),
            source_id=source_id,
            canonical_url=canonical_url,
            title=title,
            normalized_title=normalized_title,
            content=content,
            clean_content=clean_content,
            language=language,
            published_at=published_at,
            ingested_at=ingested_at,
            tier=tier,
            source_type=source_type,
            exact_hash=exact_hash,
            simhash=simhash,
            content_length=content_len,
            quality_score=_quality_score(title, clean_content, published_at),
            metadata=record_metadata,
        )


__all__ = ["ArticleNormalizer", "canonicalize_url"]
