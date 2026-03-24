from __future__ import annotations

from collections import Counter, defaultdict
import json
from typing import Any, Mapping, Protocol, Sequence

from ..utils.logger import get_logger

logger = get_logger("event-enrichment")

REGION_METADATA_KEYS = ("regions", "countries", "locations", "markets")
ASSET_METADATA_KEYS = ("assets", "symbols", "tickers")
ENTITY_METADATA_KEYS = (
    "entities",
    "entity",
    "companies",
    "organizations",
    "orgs",
    "countries",
    "regions",
    "locations",
    "people",
    "topics",
    "tags",
)
LOCATION_ENTITY_TYPES = {"location", "region", "country"}
ASSET_ENTITY_TYPES = {"ticker", "asset"}
ACTION_GROUPS = {
    "rate_cut": {
        "cut",
        "cuts",
        "lower",
        "lowers",
        "lowered",
        "easing",
        "降息",
        "下调",
    },
    "rate_hike": {
        "hike",
        "hikes",
        "raise",
        "raises",
        "raised",
        "tightening",
        "加息",
        "上调",
    },
    "approval": {"approve", "approved", "批准", "通过"},
    "rejection": {"reject", "rejected", "deny", "denied", "否认", "驳回"},
    "surge": {"surge", "jump", "spike", "飙升", "跳涨"},
    "slump": {"slump", "fall", "drop", "plunge", "下跌", "暴跌"},
}
ACTION_CONFLICTS = {
    "rate_cut": {"rate_hike"},
    "rate_hike": {"rate_cut"},
    "approval": {"rejection"},
    "rejection": {"approval"},
    "surge": {"slump"},
    "slump": {"surge"},
}
EVENT_TYPE_RULES = (
    (
        "conflict",
        {
            "attack",
            "missile",
            "strike",
            "drone",
            "war",
            "troops",
            "sanction",
            "sanctions",
            "袭击",
            "冲突",
            "制裁",
        },
    ),
    (
        "central_bank",
        {
            "benchmark rate",
            "interest rate",
            "central bank",
            "rate decision",
            "央行",
            "基准利率",
            "利率决议",
        },
    ),
    (
        "policy",
        {
            "policy",
            "tariff",
            "bill",
            "ministry",
            "parliament",
            "政策",
            "法案",
            "关税",
        },
    ),
    (
        "supply_disruption",
        {
            "outage",
            "shutdown",
            "supply",
            "refinery",
            "pipeline",
            "shipping",
            "freight",
            "港口",
            "停摆",
            "断供",
        },
    ),
    (
        "macro_data",
        {
            "inflation",
            "cpi",
            "gdp",
            "payrolls",
            "pmi",
            "通胀",
            "非农",
            "国内生产总值",
        },
    ),
)
MARKET_CHANNEL_RULES = {
    "rates": {
        "interest rate",
        "yield",
        "bond",
        "treasury",
        "benchmark rate",
        "央行",
        "利率",
        "国债",
    },
    "fx": {
        "fx",
        "currency",
        "dollar",
        "euro",
        "yen",
        "yuan",
        "汇率",
        "美元",
        "欧元",
        "日元",
    },
    "equities": {
        "stock",
        "stocks",
        "equity",
        "equities",
        "share",
        "shares",
        "index",
        "指数",
        "股市",
    },
    "commodities": {
        "brent",
        "wti",
        "oil",
        "gas",
        "copper",
        "gold",
        "commodity",
        "commodities",
        "原油",
        "天然气",
        "铜",
        "黄金",
    },
    "energy": {
        "brent",
        "wti",
        "oil",
        "gas",
        "refinery",
        "pipeline",
        "power",
        "electricity",
        "原油",
        "天然气",
        "炼厂",
        "电力",
    },
    "shipping": {
        "shipping",
        "freight",
        "red sea",
        "bab al-mandab",
        "container",
        "航运",
        "运费",
        "红海",
    },
    "credit": {
        "spread",
        "spreads",
        "credit",
        "default",
        "defaults",
        "债券利差",
        "信用",
        "违约",
    },
}


class EventRepositoryLike(Protocol):
    async def get_event(self, event_id: str) -> dict[str, Any] | None: ...

    async def update_event(
        self, event_id: str, fields: Mapping[str, Any]
    ) -> dict[str, Any]: ...

    async def list_event_members(self, event_id: str) -> list[dict[str, Any]]: ...

    async def list_event_state_transitions(self, event_id: str) -> list[dict[str, Any]]: ...


class ArticleRepositoryLike(Protocol):
    async def get_article(self, article_id: str) -> dict[str, Any] | None: ...

    async def get_article_features(self, article_id: str) -> dict[str, Any] | None: ...


class AIServiceLike(Protocol):
    async def call_agent(
        self, name: str, system_prompt: str, user_content: str, use_json: bool = True
    ) -> str: ...


class CacheLike(Protocol):
    async def get(self, key: str) -> Any | None: ...

    async def set(
        self, key: str, value: Any, *, ttl_seconds: int = 900
    ) -> bool: ...


class EventEnrichmentService:
    ENRICHMENT_CACHE_PREFIX = "enrichment:"
    ENRICHMENT_CACHE_TTL = 900

    def __init__(
        self,
        event_repository: EventRepositoryLike,
        article_repository: ArticleRepositoryLike,
        ai_service: AIServiceLike | None = None,
        *,
        cache: CacheLike | None = None,
        max_entities: int = 12,
        max_regions: int = 8,
        max_assets: int = 8,
        max_channels: int = 6,
    ):
        self.event_repository = event_repository
        self.article_repository = article_repository
        self.ai_service = ai_service
        self._cache = cache
        self.max_entities = max_entities
        self.max_regions = max_regions
        self.max_assets = max_assets
        self.max_channels = max_channels

    async def enrich_event(
        self,
        event_id: str,
        *,
        event: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        from .prompts import EVENT_ENRICHMENT_PROMPT, build_event_enrichment_input

        event_row = dict(event or await self.event_repository.get_event(event_id) or {})
        if not event_row:
            raise ValueError(f"event not found: {event_id}")

        members = await self.event_repository.list_event_members(event_id)
        transitions = await self.event_repository.list_event_state_transitions(event_id)
        (
            regions,
            entities,
            assets,
            channels,
            member_contexts,
            full_text,
        ) = await self._aggregate_members(members)

        # 混合模式：规则打底，LLM 增强
        llm_metadata = {}
        if self.ai_service:
            try:
                llm_input = build_event_enrichment_input(
                    title=self._text(event_row.get("canonical_title")),
                    facts=[m["actions"] for m in member_contexts if m.get("actions")],
                )
                raw_json = await self.ai_service.call_agent(
                    "EventEnrichment",
                    EVENT_ENRICHMENT_PROMPT,
                    llm_input,
                    use_json=True,
                )
                llm_metadata = json.loads(raw_json)
                
                # 合并 LLM 提取的标的
                for asset in llm_metadata.get("affectedAssets", []):
                    ticker = asset.get("ticker")
                    if ticker and ticker not in [a["name"] for a in assets]:
                        assets.append({"name": ticker, "count": 1, "reason": asset.get("reason")})
                
                # 合并 LLM 提取的频道
                for channel in llm_metadata.get("marketChannels", []):
                    if channel not in [c["name"] for c in channels]:
                        channels.append({"name": channel, "count": 1})
            except Exception as e:
                logger.warning(f"LLM enrichment failed for {event_id}, using rules only: {e}")

        last_transition = dict(transitions[-1]) if transitions else {}
        contradicting_article_ids = self._contradicting_article_ids(transitions)
        dominant_actions = self._dominant_actions(
            member_contexts,
            contradicting_article_ids=contradicting_article_ids,
        )
        supporting_sources, contradicting_sources = self._classify_sources(
            member_contexts,
            contradicting_article_ids=contradicting_article_ids,
            dominant_actions=dominant_actions,
        )
        event_type = llm_metadata.get("eventType") or self._infer_event_type(full_text, channels)
        primary_region = regions[0]["name"] if regions else self._text(
            event_row.get("primary_region")
        )

        enrichment = {
            "regions": regions,
            "entities": entities,
            "assets": assets,
            "market_channels": channels,
            "event_type": event_type,
            "supporting_sources": supporting_sources,
            "contradicting_sources": contradicting_sources,
            "member_count": len(members),
            "source_count": len({item["source_id"] for item in supporting_sources + contradicting_sources}),
            "last_transition": self._serialize_transition(last_transition),
            "llm_enhanced": bool(llm_metadata),
        }

        metadata = event_row.get("metadata")
        merged_metadata = dict(metadata) if isinstance(metadata, Mapping) else {}
        merged_metadata["enrichment"] = enrichment
        updated_event = await self.event_repository.update_event(
            event_id,
            {
                "primary_region": primary_region,
                "event_type": event_type,
                "metadata": self._normalize_metadata(merged_metadata),
            },
        )
        return {"event": updated_event, "enrichment": enrichment}

    async def get_event_enrichment(
        self,
        event_id: str,
        *,
        event: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        cache_key = f"{self.ENRICHMENT_CACHE_PREFIX}{event_id}"
        if self._cache:
            cached = await self._cache.get(cache_key)
            if isinstance(cached, Mapping):
                return dict(cached)

        event_row = dict(event or await self.event_repository.get_event(event_id) or {})
        if not event_row:
            raise ValueError(f"event not found: {event_id}")
        metadata = event_row.get("metadata")
        if isinstance(metadata, Mapping):
            enrichment = metadata.get("enrichment")
            if isinstance(enrichment, Mapping):
                result = dict(enrichment)
                if self._cache:
                    await self._cache.set(
                        cache_key,
                        result,
                        ttl_seconds=self.ENRICHMENT_CACHE_TTL,
                    )
                return result
        result = await self.enrich_event(event_id, event=event_row)
        enrichment = dict(result["enrichment"])
        if self._cache:
            await self._cache.set(
                cache_key,
                enrichment,
                ttl_seconds=self.ENRICHMENT_CACHE_TTL,
            )
        return enrichment

    async def _aggregate_members(
        self,
        members: Sequence[Mapping[str, Any]],
    ) -> tuple[
        list[dict[str, Any]],
        list[dict[str, Any]],
        list[dict[str, Any]],
        list[dict[str, Any]],
        list[dict[str, Any]],
        str,
    ]:
        region_counts: Counter[str] = Counter()
        entity_counts: Counter[tuple[str, str]] = Counter()
        asset_counts: Counter[str] = Counter()
        channel_counts: Counter[str] = Counter()
        member_contexts: list[dict[str, Any]] = []
        text_fragments: list[str] = []

        for member in members:
            article_id = self._text(member.get("article_id"))
            if not article_id:
                continue
            article = await self.article_repository.get_article(article_id) or {}
            features = (
                await self.article_repository.get_article_features(article_id) or {}
            )
            source_id = self._source_id(article)

            text = self._article_text(article)
            text_fragments.append(text)
            member_contexts.append(
                {
                    "article_id": article_id,
                    "source_id": source_id,
                    "actions": self._action_groups_from_text(text),
                }
            )
            for region in self._extract_regions(article, features):
                region_counts[region] += 1
            for entity_name, entity_type in self._extract_entities(article, features):
                entity_counts[(entity_name, entity_type)] += 1
            article_assets = self._extract_assets(article, features)
            for asset in article_assets:
                asset_counts[asset] += 1
            for channel in self._infer_market_channels(text, article_assets):
                channel_counts[channel] += 1

        regions = [
            {"name": name, "count": count}
            for name, count in region_counts.most_common(self.max_regions)
        ]
        entities = [
            {"name": name, "type": entity_type, "count": count}
            for (name, entity_type), count in entity_counts.most_common(self.max_entities)
        ]
        assets = [
            {"name": name, "count": count}
            for name, count in asset_counts.most_common(self.max_assets)
        ]
        channels = [
            {"name": name, "count": count}
            for name, count in channel_counts.most_common(self.max_channels)
        ]
        return regions, entities, assets, channels, member_contexts, " ".join(
            fragment for fragment in text_fragments if fragment
        )

    def _classify_sources(
        self,
        member_contexts: Sequence[Mapping[str, Any]],
        *,
        contradicting_article_ids: set[str],
        dominant_actions: set[str],
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        supporting: dict[str, list[str]] = defaultdict(list)
        contradicting: dict[str, list[str]] = defaultdict(list)

        for member in member_contexts:
            article_id = self._text(member.get("article_id"))
            if not article_id:
                continue
            source_id = self._text(member.get("source_id")) or "unknown"
            raw_actions = member.get("actions", set())
            article_actions = (
                {self._text(action) for action in raw_actions if action}
                if isinstance(raw_actions, (set, list, tuple))
                else set()
            )
            has_conflict = (
                article_id in contradicting_article_ids
                or self._has_action_conflict(article_actions, dominant_actions)
            )
            target = contradicting if has_conflict else supporting
            target[source_id].append(article_id)

        return (
            self._serialize_sources(supporting),
            self._serialize_sources(contradicting),
        )

    def _extract_regions(
        self,
        article: Mapping[str, Any],
        features: Mapping[str, Any],
    ) -> set[str]:
        regions: set[str] = set()
        metadata = article.get("metadata")
        if isinstance(metadata, Mapping):
            for key in REGION_METADATA_KEYS:
                regions.update(self._iter_names(metadata.get(key)))
        raw_entities = features.get("entities")
        if isinstance(raw_entities, Sequence) and not isinstance(
            raw_entities, (str, bytes)
        ):
            for entity in raw_entities:
                if not isinstance(entity, Mapping):
                    continue
                entity_type = self._text(entity.get("type")).lower()
                if entity_type in LOCATION_ENTITY_TYPES:
                    normalized = self._normalize_name(entity.get("name"))
                    if normalized:
                        regions.add(normalized)
        return regions

    def _extract_entities(
        self,
        article: Mapping[str, Any],
        features: Mapping[str, Any],
    ) -> set[tuple[str, str]]:
        entities: set[tuple[str, str]] = set()
        raw_entities = features.get("entities")
        if isinstance(raw_entities, Sequence) and not isinstance(
            raw_entities, (str, bytes)
        ):
            for entity in raw_entities:
                if not isinstance(entity, Mapping):
                    continue
                name = self._normalize_name(entity.get("name"))
                entity_type = self._text(entity.get("type")).lower() or "metadata"
                if name:
                    entities.add((name, entity_type))
        metadata = article.get("metadata")
        if isinstance(metadata, Mapping):
            for key in ENTITY_METADATA_KEYS:
                for name in self._iter_names(metadata.get(key)):
                    entity_type = self._entity_type_for_key(key)
                    entities.add((name, entity_type))
        return entities

    def _extract_assets(
        self,
        article: Mapping[str, Any],
        features: Mapping[str, Any],
    ) -> set[str]:
        assets: set[str] = set()
        metadata = article.get("metadata")
        if isinstance(metadata, Mapping):
            for key in ASSET_METADATA_KEYS:
                assets.update(self._iter_names(metadata.get(key)))
        raw_entities = features.get("entities")
        if isinstance(raw_entities, Sequence) and not isinstance(
            raw_entities, (str, bytes)
        ):
            for entity in raw_entities:
                if not isinstance(entity, Mapping):
                    continue
                entity_type = self._text(entity.get("type")).lower()
                if entity_type in ASSET_ENTITY_TYPES:
                    normalized = self._normalize_name(entity.get("name"))
                    if normalized:
                        assets.add(normalized)
        return assets

    def _infer_market_channels(self, text: str, assets: set[str]) -> set[str]:
        lowered = text.casefold()
        channels = {
            channel
            for channel, markers in MARKET_CHANNEL_RULES.items()
            if any(marker in lowered for marker in markers)
        }
        asset_text = " ".join(sorted(assets))
        lowered_assets = asset_text.casefold()
        for channel, markers in MARKET_CHANNEL_RULES.items():
            if any(marker in lowered_assets for marker in markers):
                channels.add(channel)
        return channels

    def _infer_event_type(
        self,
        text: str,
        channels: Sequence[Mapping[str, Any]],
    ) -> str:
        lowered = text.casefold()
        for event_type, markers in EVENT_TYPE_RULES:
            if any(marker in lowered for marker in markers):
                return event_type
        channel_names = {self._text(item.get("name")) for item in channels}
        if "shipping" in channel_names or "energy" in channel_names:
            return "supply_disruption"
        return "general"

    def _contradicting_article_ids(
        self,
        transitions: Sequence[Mapping[str, Any]],
    ) -> set[str]:
        article_ids: set[str] = set()
        for transition in transitions:
            metadata = transition.get("metadata")
            if not isinstance(metadata, Mapping):
                continue
            merge_signals = metadata.get("merge_signals")
            if not isinstance(merge_signals, Mapping):
                continue
            if bool(merge_signals.get("conflict")):
                article_id = self._text(transition.get("trigger_article_id"))
                if article_id:
                    article_ids.add(article_id)
        return article_ids

    def _dominant_actions(
        self,
        member_contexts: Sequence[Mapping[str, Any]],
        *,
        contradicting_article_ids: set[str],
    ) -> set[str]:
        counter: Counter[str] = Counter()
        for member in member_contexts:
            article_id = self._text(member.get("article_id"))
            if article_id in contradicting_article_ids:
                continue
            actions = member.get("actions", set())
            if isinstance(actions, (set, list, tuple)):
                for action in actions:
                    normalized = self._text(action)
                    if normalized:
                        counter[normalized] += 1
        if not counter:
            for member in member_contexts:
                actions = member.get("actions", set())
                if isinstance(actions, (set, list, tuple)):
                    for action in actions:
                        normalized = self._text(action)
                        if normalized:
                            counter[normalized] += 1
        if not counter:
            return set()
        max_count = max(counter.values())
        return {action for action, count in counter.items() if count == max_count}

    def _action_groups_from_text(self, text: str) -> set[str]:
        lowered = text.casefold()
        return {
            group
            for group, markers in ACTION_GROUPS.items()
            if any(marker in lowered for marker in markers)
        }

    def _has_action_conflict(
        self,
        article_actions: set[str],
        dominant_actions: set[str],
    ) -> bool:
        if not article_actions or not dominant_actions:
            return False
        for action in article_actions:
            if any(opposite in dominant_actions for opposite in ACTION_CONFLICTS.get(action, set())):
                return True
        return False

    def _serialize_sources(
        self,
        grouped_sources: Mapping[str, Sequence[str]],
    ) -> list[dict[str, Any]]:
        return [
            {
                "source_id": source_id,
                "article_count": len(article_ids),
                "article_ids": list(article_ids),
            }
            for source_id, article_ids in sorted(
                grouped_sources.items(),
                key=lambda item: (-len(item[1]), item[0]),
            )
        ]

    def _serialize_transition(self, transition: Mapping[str, Any]) -> dict[str, Any]:
        if not transition:
            return {}
        return {
            "transition_id": self._text(transition.get("transition_id")),
            "from_state": self._text(transition.get("from_state")),
            "to_state": self._text(transition.get("to_state")),
            "reason": self._text(transition.get("reason")),
            "trigger_article_id": self._text(transition.get("trigger_article_id")),
            "created_at": self._text(transition.get("created_at")),
        }

    def _article_text(self, article: Mapping[str, Any]) -> str:
        return " ".join(
            part
            for part in (
                self._text(article.get("title")),
                self._text(article.get("normalized_title")),
                self._text(article.get("clean_content") or article.get("content"))[:800],
            )
            if part
        )

    def _source_id(self, article: Mapping[str, Any]) -> str:
        metadata = article.get("metadata")
        if isinstance(metadata, Mapping):
            for key in ("source", "source_id"):
                normalized = self._normalize_name(metadata.get(key))
                if normalized:
                    return normalized
        normalized = self._normalize_name(article.get("source_id"))
        if normalized:
            return normalized
        return "unknown"

    def _iter_names(self, value: Any) -> set[str]:
        names: set[str] = set()
        if value is None:
            return names
        if isinstance(value, Mapping):
            normalized = self._normalize_name(
                value.get("name") or value.get("value") or value.get("text")
            )
            if normalized:
                names.add(normalized)
            return names
        if isinstance(value, (str, bytes)):
            normalized = self._normalize_name(value)
            if normalized:
                names.add(normalized)
            return names
        if isinstance(value, Sequence):
            for item in value:
                names.update(self._iter_names(item))
        return names

    @staticmethod
    def _entity_type_for_key(key: str) -> str:
        if key in {"countries", "regions", "locations"}:
            return "location"
        if key in {"companies", "organizations", "orgs"}:
            return "organization"
        if key in {"topics", "tags"}:
            return "topic"
        return "metadata"

    @staticmethod
    def _normalize_name(value: Any) -> str:
        if value is None:
            return ""
        if isinstance(value, str):
            return " ".join(value.split()).strip().casefold()
        return str(value).strip().casefold()

    @staticmethod
    def _normalize_metadata(metadata: Mapping[str, Any]) -> dict[str, Any]:
        return json.loads(json.dumps(dict(metadata), default=str))

    @staticmethod
    def _text(value: Any) -> str:
        if value is None:
            return ""
        if isinstance(value, str):
            return value.strip()
        return str(value).strip()


from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from .alpha_vantage_service import AlphaVantageService


def _score_to_label(score: float) -> str:
    if score >= 0.15:
        return "bullish"
    if score <= -0.15:
        return "bearish"
    return "neutral"


async def enrich_event_sentiment(
    event: dict,
    *,
    av_service: "AlphaVantageService | None",
) -> dict:
    """为事件注入 sentiment_score / sentiment_label。

    取事件关联资产列表中第一个 ticker，查询 Alpha Vantage；
    无 assets 或无 API key 时 sentiment_score = None。
    返回原 event dict（in-place 修改）。
    """
    assets: list[str] = event.get("assets") or []
    if not assets or av_service is None:
        event.setdefault("sentiment_score", None)
        event.setdefault("sentiment_label", "neutral")
        return event

    from .alpha_vantage_service import aggregate_sentiment

    ticker = assets[0]
    try:
        articles = await av_service.get_news_sentiment(ticker, days=3)
        score = aggregate_sentiment(articles) if articles else None
    except Exception as exc:
        logger.warning(f"Sentiment enrichment failed for {ticker}: {exc}")
        score = None

    event["sentiment_score"] = round(score, 4) if score is not None else None
    event["sentiment_label"] = _score_to_label(score) if score is not None else "neutral"
    return event


__all__ = ["EventEnrichmentService", "enrich_event_sentiment"]
