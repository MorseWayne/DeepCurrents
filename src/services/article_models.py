from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Mapping


def _require_non_empty_text(value: Any, field_name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string")
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} must be a non-empty string")
    return normalized


def _optional_text(value: Any, field_name: str, *, default: str = "") -> str:
    if value is None:
        return default
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string")
    return value


def _optional_datetime(value: Any, field_name: str) -> datetime | None:
    if value is None:
        return None
    if not isinstance(value, datetime):
        raise TypeError(f"{field_name} must be a datetime")
    return value


def _metadata_dict(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise TypeError("metadata must be a mapping")
    return dict(value)


@dataclass(slots=True)
class ArticleRecord:
    article_id: str
    source_id: str
    canonical_url: str
    title: str
    normalized_title: str | None = None
    content: str = ""
    clean_content: str | None = None
    language: str = ""
    published_at: datetime | None = None
    ingested_at: datetime | None = None
    tier: int = 4
    source_type: str = "other"
    exact_hash: str = ""
    simhash: str = ""
    content_length: int | None = None
    quality_score: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.article_id = _require_non_empty_text(self.article_id, "article_id")
        self.source_id = _require_non_empty_text(self.source_id, "source_id")
        self.canonical_url = _require_non_empty_text(
            self.canonical_url, "canonical_url"
        )
        self.title = _require_non_empty_text(self.title, "title")

        if self.normalized_title is None:
            self.normalized_title = self.title
        else:
            self.normalized_title = _require_non_empty_text(
                self.normalized_title, "normalized_title"
            )

        self.content = _optional_text(self.content, "content")

        if self.clean_content is None:
            self.clean_content = self.content
        else:
            self.clean_content = _optional_text(self.clean_content, "clean_content")

        self.language = _optional_text(self.language, "language")
        self.published_at = _optional_datetime(self.published_at, "published_at")
        self.ingested_at = _optional_datetime(self.ingested_at, "ingested_at")

        if isinstance(self.tier, bool) or not isinstance(self.tier, int):
            raise TypeError("tier must be an integer")
        if self.tier < 1 or self.tier > 4:
            raise ValueError("tier must be between 1 and 4")

        self.source_type = _optional_text(
            self.source_type, "source_type", default="other"
        )
        self.exact_hash = _optional_text(self.exact_hash, "exact_hash")
        self.simhash = _optional_text(self.simhash, "simhash")

        if self.content_length is None:
            self.content_length = len(self.clean_content or self.content)
        elif not isinstance(self.content_length, int):
            raise TypeError("content_length must be an integer")
        elif self.content_length < 0:
            raise ValueError("content_length must be non-negative")

        self.quality_score = float(self.quality_score)
        self.metadata = _metadata_dict(self.metadata)

    @classmethod
    def from_mapping(cls, article: Mapping[str, Any]) -> ArticleRecord:
        return cls(
            article_id=article["article_id"],
            source_id=article["source_id"],
            canonical_url=article["canonical_url"],
            title=article["title"],
            normalized_title=article.get("normalized_title"),
            content=article.get("content", ""),
            clean_content=article.get("clean_content"),
            language=article.get("language", ""),
            published_at=article.get("published_at"),
            ingested_at=article.get("ingested_at"),
            tier=article.get("tier", 4),
            source_type=article.get("source_type", article.get("sourceType", "other")),
            exact_hash=article.get("exact_hash", ""),
            simhash=article.get("simhash", ""),
            content_length=article.get("content_length"),
            quality_score=article.get("quality_score", 0.0),
            metadata=article.get("metadata", {}),
        )

    @classmethod
    def from_repository_row(cls, row: Mapping[str, Any]) -> ArticleRecord:
        return cls.from_mapping(row)

    def to_article_payload(self) -> dict[str, Any]:
        return {
            "article_id": self.article_id,
            "source_id": self.source_id,
            "canonical_url": self.canonical_url,
            "title": self.title,
            "normalized_title": self.normalized_title,
            "content": self.content,
            "clean_content": self.clean_content,
            "language": self.language,
            "published_at": self.published_at,
            "ingested_at": self.ingested_at,
            "tier": self.tier,
            "source_type": self.source_type,
            "exact_hash": self.exact_hash,
            "simhash": self.simhash,
            "content_length": self.content_length,
            "quality_score": self.quality_score,
            "metadata": dict(self.metadata),
        }

    def to_feature_seed(self) -> dict[str, Any]:
        return {
            "article_id": self.article_id,
            "source_id": self.source_id,
            "canonical_url": self.canonical_url,
            "title": self.title,
            "normalized_title": self.normalized_title,
            "content": self.content,
            "clean_content": self.clean_content,
            "language": self.language,
            "published_at": self.published_at,
            "ingested_at": self.ingested_at,
            "tier": self.tier,
            "source_type": self.source_type,
            "exact_hash": self.exact_hash,
            "simhash": self.simhash,
            "content_length": self.content_length,
            "quality_score": self.quality_score,
            "metadata": dict(self.metadata),
        }


__all__ = ["ArticleRecord"]
