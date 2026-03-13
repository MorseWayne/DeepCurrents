from __future__ import annotations

from collections import Counter
from datetime import datetime
import re
from typing import Any, Mapping, Protocol, Sequence

from ..utils.tokenizer import contains_cjk, tokenize_to_array
from .article_models import ArticleRecord

ENTITY_TEXT_RE = re.compile(r"[A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,3}")
ENTITY_TICKER_RE = re.compile(r"\b[A-Z]{2,6}\b")
METADATA_ENTITY_KEYS = (
    "entities",
    "entity",
    "symbols",
    "tickers",
    "companies",
    "countries",
    "regions",
    "locations",
    "people",
    "organizations",
    "orgs",
    "assets",
    "topics",
    "tags",
)


def _compute_quality_score(
    title: str,
    clean_content: str,
    published_at: datetime | None,
) -> float:
    score = min(len(clean_content) / 1200.0, 1.0)
    if title:
        score += 0.1
    if published_at is not None:
        score += 0.05
    return round(min(score, 1.0), 3)


class ArticleRepositoryLike(Protocol):
    async def upsert_article_features(
        self, features: Mapping[str, Any]
    ) -> dict[str, Any]: ...


class VectorStoreLike(Protocol):
    async def ensure_collection(
        self,
        collection_name: str,
        *,
        vector_size: int,
        distance: str = "cosine",
    ) -> None: ...

    async def upsert_point(
        self,
        collection_name: str,
        *,
        point_id: str | int,
        vector: Sequence[float],
        payload: Mapping[str, Any] | None = None,
        wait: bool = True,
    ) -> Mapping[str, Any]: ...


class EmbeddingClient(Protocol):
    async def embed(self, text: str) -> list[float]: ...


class OpenAIEmbeddingClient:
    def __init__(
        self,
        *,
        api_key: str,
        base_url: str,
        model: str,
        timeout_ms: int,
    ):
        self.model = model
        self.timeout_ms = timeout_ms
        try:
            from openai import AsyncOpenAI
        except ImportError as exc:
            raise ImportError(
                "ArticleFeatureExtractor requires `openai` for default embeddings."
            ) from exc
        self._client = AsyncOpenAI(api_key=api_key, base_url=base_url)

    async def embed(self, text: str) -> list[float]:
        response = await self._client.embeddings.create(
            model=self.model,
            input=text,
            timeout=self.timeout_ms / 1000,
        )
        return [float(item) for item in response.data[0].embedding]


class ArticleFeatureExtractor:
    def __init__(
        self,
        article_repository: ArticleRepositoryLike,
        vector_store: VectorStoreLike,
        *,
        embedding_model: str,
        embedding_client: EmbeddingClient | None = None,
        feature_version: str = "v1",
        vector_collection: str = "article_features",
        vector_distance: str = "cosine",
        max_keywords: int = 8,
        max_entities: int = 12,
    ):
        self.article_repository = article_repository
        self.vector_store = vector_store
        self.embedding_model = embedding_model
        if embedding_client is None:
            from ..config.settings import CONFIG

            embedding_client = OpenAIEmbeddingClient(
                api_key=CONFIG.ai_api_key,
                base_url=self._embedding_base_url(CONFIG.ai_api_url),
                model=embedding_model,
                timeout_ms=CONFIG.ai_timeout_ms,
            )
        self.embedding_client = embedding_client
        self.feature_version = feature_version
        self.vector_collection = vector_collection
        self.vector_distance = vector_distance
        self.max_keywords = max_keywords
        self.max_entities = max_entities

    async def extract(
        self, article: ArticleRecord | Mapping[str, Any]
    ) -> dict[str, Any]:
        seed = self._coerce_seed(article)
        embedding_input = self._build_embedding_input(seed)
        embedding = await self.embedding_client.embed(embedding_input)
        vector_id = seed["article_id"]
        keywords = self._extract_keywords(seed)
        entities = self._extract_entities(seed)
        quality_score = self._resolve_quality_score(seed)
        vector_payload = self._build_vector_payload(
            seed, keywords, entities, quality_score
        )

        return {
            "article_id": seed["article_id"],
            "embedding_model": self.embedding_model,
            "embedding_vector_id": vector_id,
            "language": seed.get("language", ""),
            "simhash": seed.get("simhash", ""),
            "entities": entities,
            "keywords": keywords,
            "quality_score": quality_score,
            "feature_version": self.feature_version,
            "embedding": embedding,
            "vector_collection": self.vector_collection,
            "vector_payload": vector_payload,
        }

    async def extract_and_persist(
        self,
        article: ArticleRecord | Mapping[str, Any],
    ) -> dict[str, Any]:
        extracted = await self.extract(article)
        await self.vector_store.ensure_collection(
            extracted["vector_collection"],
            vector_size=len(extracted["embedding"]),
            distance=self.vector_distance,
        )
        await self.vector_store.upsert_point(
            extracted["vector_collection"],
            point_id=extracted["embedding_vector_id"],
            vector=extracted["embedding"],
            payload=extracted["vector_payload"],
        )
        stored = await self.article_repository.upsert_article_features(
            self._repository_payload(extracted)
        )
        return {
            **stored,
            "embedding": extracted["embedding"],
            "vector_collection": extracted["vector_collection"],
            "vector_payload": extracted["vector_payload"],
        }

    @staticmethod
    def _embedding_base_url(url: str) -> str:
        return url.replace("/chat/completions", "")

    def _coerce_seed(
        self, article: ArticleRecord | Mapping[str, Any]
    ) -> dict[str, Any]:
        if isinstance(article, ArticleRecord):
            return article.to_feature_seed()
        if not isinstance(article, Mapping):
            raise TypeError("article must be an ArticleRecord or mapping")
        return dict(article)

    def _build_embedding_input(self, seed: Mapping[str, Any]) -> str:
        title = self._text(seed.get("title"))
        normalized_title = self._text(seed.get("normalized_title"))
        clean_content = self._text(seed.get("clean_content") or seed.get("content"))
        source_id = self._text(seed.get("source_id"))
        language = self._text(seed.get("language"))
        return "\n".join(
            part
            for part in (
                title,
                normalized_title
                if normalized_title and normalized_title != title
                else "",
                clean_content[:6000],
                f"source:{source_id}" if source_id else "",
                f"language:{language}" if language else "",
            )
            if part
        )

    def _extract_keywords(self, seed: Mapping[str, Any]) -> list[str]:
        title_tokens = tokenize_to_array(self._text(seed.get("title")), min_length=2)
        content_tokens = tokenize_to_array(
            self._text(seed.get("clean_content") or seed.get("content")),
            min_length=2,
        )
        counts = Counter()
        for token in content_tokens:
            counts[token] += 1
        for token in title_tokens:
            counts[token] += 3

        keywords = [
            token
            for token, _ in counts.most_common(self.max_keywords * 3)
            if self._keyword_allowed(token)
        ]
        unique = []
        seen = set()
        for token in keywords:
            if token in seen:
                continue
            seen.add(token)
            unique.append(token)
            if len(unique) >= self.max_keywords:
                break
        return unique

    def _extract_entities(self, seed: Mapping[str, Any]) -> list[dict[str, str]]:
        entities: list[dict[str, str]] = []
        seen = set()
        metadata = seed.get("metadata") or {}
        if isinstance(metadata, Mapping):
            for key in METADATA_ENTITY_KEYS:
                values = metadata.get(key)
                for entity in self._iter_entities(
                    values, entity_type=self._entity_type_for_key(key)
                ):
                    name = entity["name"]
                    marker = (name.casefold(), entity["type"])
                    if marker in seen:
                        continue
                    seen.add(marker)
                    entities.append(entity)
                    if len(entities) >= self.max_entities:
                        return entities

        text = " ".join(
            part
            for part in (
                self._text(seed.get("title")),
                self._text(seed.get("clean_content") or seed.get("content"))[:1500],
            )
            if part
        )
        if contains_cjk(text):
            return entities

        for match in ENTITY_TEXT_RE.findall(text):
            normalized = match.strip()
            if len(normalized) < 4 or normalized.lower() in {"the", "this", "that"}:
                continue
            marker = (normalized.casefold(), "phrase")
            if marker in seen:
                continue
            seen.add(marker)
            entities.append({"name": normalized, "type": "phrase"})
            if len(entities) >= self.max_entities:
                return entities

        for match in ENTITY_TICKER_RE.findall(text):
            marker = (match.casefold(), "ticker")
            if marker in seen:
                continue
            seen.add(marker)
            entities.append({"name": match, "type": "ticker"})
            if len(entities) >= self.max_entities:
                break
        return entities

    def _resolve_quality_score(self, seed: Mapping[str, Any]) -> float:
        current = seed.get("quality_score")
        if current is None:
            current_value = 0.0
        else:
            try:
                current_value = float(current)
            except (TypeError, ValueError):
                current_value = 0.0
        if current_value > 0:
            return round(min(current_value, 1.0), 3)
        published_at = seed.get("published_at")
        if published_at is not None and not isinstance(published_at, datetime):
            published_at = None
        return _compute_quality_score(
            self._text(seed.get("title")),
            self._text(seed.get("clean_content") or seed.get("content")),
            published_at,
        )

    def _build_vector_payload(
        self,
        seed: Mapping[str, Any],
        keywords: list[str],
        entities: list[dict[str, str]],
        quality_score: float,
    ) -> dict[str, Any]:
        return {
            "article_id": seed["article_id"],
            "source_id": self._text(seed.get("source_id")),
            "canonical_url": self._text(seed.get("canonical_url")),
            "title": self._text(seed.get("title")),
            "language": self._text(seed.get("language")),
            "simhash": self._text(seed.get("simhash")),
            "keywords": keywords,
            "entities": entities,
            "quality_score": quality_score,
            "feature_version": self.feature_version,
        }

    def _repository_payload(self, extracted: Mapping[str, Any]) -> dict[str, Any]:
        return {
            "article_id": extracted["article_id"],
            "embedding_model": extracted["embedding_model"],
            "embedding_vector_id": extracted["embedding_vector_id"],
            "language": extracted["language"],
            "simhash": extracted["simhash"],
            "entities": extracted["entities"],
            "keywords": extracted["keywords"],
            "quality_score": extracted["quality_score"],
            "feature_version": extracted["feature_version"],
        }

    @staticmethod
    def _entity_type_for_key(key: str) -> str:
        if key in {"symbols", "tickers", "assets"}:
            return "ticker"
        if key in {"countries", "regions", "locations"}:
            return "location"
        if key in {"people"}:
            return "person"
        if key in {"organizations", "orgs", "companies"}:
            return "organization"
        if key in {"topics", "tags"}:
            return "topic"
        return "metadata"

    def _iter_entities(self, value: Any, *, entity_type: str) -> list[dict[str, str]]:
        if value is None:
            return []
        if isinstance(value, str):
            text = value.strip()
            return [{"name": text, "type": entity_type}] if text else []
        if isinstance(value, Mapping):
            name = self._text(
                value.get("name") or value.get("value") or value.get("text")
            )
            if not name:
                return []
            return [
                {"name": name, "type": self._text(value.get("type")) or entity_type}
            ]
        if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray)):
            items = []
            for item in value:
                items.extend(self._iter_entities(item, entity_type=entity_type))
            return items
        text = self._text(value)
        return [{"name": text, "type": entity_type}] if text else []

    @staticmethod
    def _keyword_allowed(token: str) -> bool:
        if token.isdigit():
            return False
        if contains_cjk(token):
            return len(token) >= 2
        return len(token) >= 3

    @staticmethod
    def _text(value: Any) -> str:
        if value is None:
            return ""
        if isinstance(value, str):
            return value.strip()
        return str(value).strip()


__all__ = ["ArticleFeatureExtractor", "OpenAIEmbeddingClient"]
