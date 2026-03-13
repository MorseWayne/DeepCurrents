from __future__ import annotations

from datetime import datetime
from typing import Any, Mapping, Protocol, Sequence


THEME_ALIASES: dict[str, set[str]] = {
    "geopolitics": {"conflict", "policy", "shipping"},
    "central_banks": {"central_bank", "rates", "fx"},
    "energy": {"energy", "commodities", "shipping", "supply_disruption"},
}


class EventRepositoryLike(Protocol):
    async def get_event(self, event_id: str) -> dict[str, Any] | None: ...

    async def list_recent_events(
        self,
        *,
        statuses: Sequence[str] | None = None,
        since: datetime | None = None,
        limit: int = 500,
    ) -> list[dict[str, Any]]: ...

    async def list_event_members(self, event_id: str) -> list[dict[str, Any]]: ...

    async def list_event_state_transitions(self, event_id: str) -> list[dict[str, Any]]: ...

    async def list_event_scores(self, event_id: str) -> list[dict[str, Any]]: ...


class ArticleRepositoryLike(Protocol):
    async def get_article(self, article_id: str) -> dict[str, Any] | None: ...

    async def get_article_features(self, article_id: str) -> dict[str, Any] | None: ...

    async def list_dedup_links(self, article_id: str) -> list[dict[str, Any]]: ...


class EventEnrichmentLike(Protocol):
    async def get_event_enrichment(
        self,
        event_id: str,
        *,
        event: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]: ...


class EventQueryService:
    def __init__(
        self,
        event_repository: EventRepositoryLike,
        article_repository: ArticleRepositoryLike,
        event_enrichment: EventEnrichmentLike,
    ):
        self.event_repository = event_repository
        self.article_repository = article_repository
        self.event_enrichment = event_enrichment

    async def list_events(
        self,
        *,
        event_id: str | None = None,
        statuses: Sequence[str] | None = None,
        since: datetime | None = None,
        theme: str | None = None,
        limit: int = 500,
    ) -> list[dict[str, Any]]:
        if event_id:
            loaded = await self.event_repository.get_event(event_id)
            candidate_events = [loaded] if loaded is not None else []
        else:
            candidate_events = await self.event_repository.list_recent_events(
                statuses=statuses,
                since=since,
                limit=limit,
            )

        items: list[dict[str, Any]] = []
        for event in candidate_events:
            if not isinstance(event, Mapping):
                continue
            if not self._matches_event_filters(
                event,
                event_id=event_id,
                statuses=statuses,
                since=since,
            ):
                continue

            enrichment = await self.event_enrichment.get_event_enrichment(
                self._text(event.get("event_id")),
                event=event,
            )
            if theme and not self._matches_theme(event, enrichment, theme):
                continue

            items.append(
                {
                    "event_id": self._text(event.get("event_id")),
                    "status": self._text(event.get("status")),
                    "canonical_title": self._text(event.get("canonical_title")),
                    "primary_region": self._text(event.get("primary_region"))
                    or self._first_name(enrichment.get("regions")),
                    "event_type": self._text(event.get("event_type"))
                    or self._text(enrichment.get("event_type")),
                    "latest_article_at": event.get("latest_article_at"),
                    "article_count": self._safe_int(event.get("article_count")),
                    "source_count": self._safe_int(event.get("source_count")),
                    "enrichment_summary": self._build_enrichment_summary(enrichment),
                    "last_transition": self._serialize_last_transition(enrichment),
                }
            )
            if len(items) >= limit:
                break
        return items

    async def get_event_timeline(self, event_id: str) -> dict[str, Any]:
        event = await self.event_repository.get_event(event_id)
        if event is None:
            raise ValueError(f"event not found: {event_id}")

        members = await self.event_repository.list_event_members(event_id)
        transitions = await self.event_repository.list_event_state_transitions(event_id)
        scores = await self.event_repository.list_event_scores(event_id)
        enrichment = await self.event_enrichment.get_event_enrichment(
            event_id,
            event=event,
        )

        serialized_members: list[dict[str, Any]] = []
        for member in members:
            article_id = self._text(member.get("article_id"))
            article = await self.article_repository.get_article(article_id) or {}
            dedup_links = await self.article_repository.list_dedup_links(article_id)
            serialized_members.append(
                {
                    "article_id": article_id,
                    "source_id": self._source_id(article),
                    "title": self._text(article.get("title")),
                    "published_at": article.get("published_at"),
                    "role": self._text(member.get("role")),
                    "is_primary": bool(member.get("is_primary")),
                    "dedup_relations_count": len(dedup_links),
                }
            )

        return {
            "event": dict(event),
            "members": serialized_members,
            "transitions": [dict(item) for item in transitions],
            "enrichment": dict(enrichment),
            "scores": [dict(item) for item in scores],
        }

    async def get_event_debug_view(self, event_id: str) -> dict[str, Any]:
        timeline = await self.get_event_timeline(event_id)
        members = await self.event_repository.list_event_members(event_id)

        dedup_links: list[dict[str, Any]] = []
        seen_dedup_ids: set[str] = set()
        member_articles: list[dict[str, Any]] = []
        dedup_relation_types: set[str] = set()

        for member in members:
            article_id = self._text(member.get("article_id"))
            article = await self.article_repository.get_article(article_id) or {}
            features = (
                await self.article_repository.get_article_features(article_id) or {}
            )
            article_dedup_links = await self.article_repository.list_dedup_links(
                article_id
            )
            member_articles.append(
                {
                    "article": dict(article),
                    "features": dict(features),
                    "dedup_links": [dict(link) for link in article_dedup_links],
                }
            )
            for link in article_dedup_links:
                link_key = self._dedup_key(link)
                if link_key in seen_dedup_ids:
                    continue
                seen_dedup_ids.add(link_key)
                dedup_links.append(dict(link))
                relation_type = self._text(link.get("relation_type"))
                if relation_type:
                    dedup_relation_types.add(relation_type)

        debug_notes = self._build_debug_notes(
            timeline=timeline,
            dedup_relation_types=dedup_relation_types,
        )
        return {
            **timeline,
            "dedup_links": dedup_links,
            "member_articles": member_articles,
            "debug_notes": debug_notes,
        }

    def _matches_event_filters(
        self,
        event: Mapping[str, Any],
        *,
        event_id: str | None,
        statuses: Sequence[str] | None,
        since: datetime | None,
    ) -> bool:
        if event_id and self._text(event.get("event_id")) != event_id:
            return False

        if statuses:
            normalized_statuses = {self._text(item).lower() for item in statuses}
            if self._text(event.get("status")).lower() not in normalized_statuses:
                return False

        if since is not None:
            latest = self._optional_datetime(
                event.get("latest_article_at") or event.get("last_updated_at")
            )
            if latest is None or latest < since:
                return False

        return True

    def _matches_theme(
        self,
        event: Mapping[str, Any],
        enrichment: Mapping[str, Any],
        theme: str,
    ) -> bool:
        normalized_theme = self._text(theme).casefold()
        if not normalized_theme:
            return True

        candidates = {normalized_theme}
        candidates.update(THEME_ALIASES.get(normalized_theme, set()))

        event_type = self._text(event.get("event_type")).casefold()
        if not event_type:
            event_type = self._text(enrichment.get("event_type")).casefold()
        if event_type in candidates or any(item in event_type for item in candidates):
            return True

        channels = {
            self._text(item.get("name")).casefold()
            for item in enrichment.get("market_channels", [])
            if isinstance(item, Mapping)
        }
        if channels & candidates:
            return True
        if any(candidate in channel for candidate in candidates for channel in channels):
            return True
        return False

    def _build_enrichment_summary(
        self,
        enrichment: Mapping[str, Any],
    ) -> dict[str, Any]:
        return {
            "regions": self._extract_names(enrichment.get("regions")),
            "assets": self._extract_names(enrichment.get("assets")),
            "market_channels": self._extract_names(
                enrichment.get("market_channels")
            ),
            "supporting_source_count": len(enrichment.get("supporting_sources", [])),
            "contradicting_source_count": len(
                enrichment.get("contradicting_sources", [])
            ),
        }

    def _serialize_last_transition(
        self,
        enrichment: Mapping[str, Any],
    ) -> dict[str, Any]:
        last_transition = enrichment.get("last_transition")
        if isinstance(last_transition, Mapping):
            return dict(last_transition)
        return {}

    def _build_debug_notes(
        self,
        *,
        timeline: Mapping[str, Any],
        dedup_relation_types: set[str],
    ) -> list[str]:
        notes: list[str] = []
        enrichment = timeline.get("enrichment")
        if isinstance(enrichment, Mapping):
            contradicting_sources = enrichment.get("contradicting_sources", [])
            supporting_sources = enrichment.get("supporting_sources", [])
            if contradicting_sources:
                notes.append("conflicting sources present in event evidence")
            if len(supporting_sources) + len(contradicting_sources) <= 1:
                notes.append("single-source event; corroboration remains weak")
            last_transition = enrichment.get("last_transition")
            if isinstance(last_transition, Mapping):
                reason = self._text(last_transition.get("reason"))
                from_state = self._text(last_transition.get("from_state"))
                to_state = self._text(last_transition.get("to_state"))
                if reason or from_state or to_state:
                    notes.append(
                        f"latest transition: {from_state or 'unknown'} -> {to_state or 'unknown'} ({reason or 'no reason'})"
                    )

        if dedup_relation_types:
            notes.append(
                "dedup links present: " + ", ".join(sorted(dedup_relation_types))
            )
        else:
            notes.append("no dedup links found across event members")
        return notes

    def _extract_names(self, items: Any) -> list[str]:
        if not isinstance(items, Sequence) or isinstance(items, (str, bytes)):
            return []
        names: list[str] = []
        for item in items:
            if isinstance(item, Mapping):
                name = self._text(item.get("name"))
                if name:
                    names.append(name)
            else:
                name = self._text(item)
                if name:
                    names.append(name)
        return names

    def _first_name(self, items: Any) -> str:
        names = self._extract_names(items)
        return names[0] if names else ""

    def _source_id(self, article: Mapping[str, Any]) -> str:
        metadata = article.get("metadata")
        if isinstance(metadata, Mapping):
            source = self._text(metadata.get("source_id") or metadata.get("source"))
            if source:
                return source
        source_id = self._text(article.get("source_id"))
        return source_id or "unknown"

    def _dedup_key(self, link: Mapping[str, Any]) -> str:
        link_id = self._text(link.get("link_id"))
        if link_id:
            return link_id
        return "|".join(
            (
                self._text(link.get("left_article_id")),
                self._text(link.get("right_article_id")),
                self._text(link.get("relation_type")),
            )
        )

    @staticmethod
    def _optional_datetime(value: Any) -> datetime | None:
        if not isinstance(value, datetime):
            return None
        return value

    @staticmethod
    def _safe_int(value: Any) -> int:
        try:
            return int(value)
        except (TypeError, ValueError):
            return 0

    @staticmethod
    def _text(value: Any) -> str:
        if value is None:
            return ""
        if isinstance(value, str):
            return value.strip()
        return str(value).strip()


__all__ = ["EventQueryService"]
