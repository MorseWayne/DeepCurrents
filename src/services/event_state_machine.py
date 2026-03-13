from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Mapping


@dataclass(frozen=True)
class EventStateDecision:
    from_state: str
    to_state: str
    reason: str
    metadata: dict[str, Any]


class EventStateMachine:
    def __init__(
        self,
        *,
        dormant_after_hours: int = 72,
        escalate_confidence_threshold: float = 0.8,
        update_novelty_threshold: float = 0.2,
    ):
        self.dormant_after = timedelta(hours=max(dormant_after_hours, 1))
        self.escalate_confidence_threshold = escalate_confidence_threshold
        self.update_novelty_threshold = update_novelty_threshold

    def evaluate(
        self,
        event: Mapping[str, Any],
        *,
        article: Mapping[str, Any],
        article_count: int,
        source_count: int,
        merge_signals: Mapping[str, Any],
        anchor_time: datetime,
    ) -> EventStateDecision | None:
        from_state = self._normalize_state(event.get("status"))
        confidence = self._safe_float(merge_signals.get("confidence"))
        support_score = self._safe_float(
            merge_signals.get("support_score") or max(confidence, 0.0)
        )
        new_entity_count = self._safe_int(merge_signals.get("new_entity_count"))
        new_region_count = self._safe_int(merge_signals.get("new_region_count"))
        risk_signal_delta = self._safe_float(merge_signals.get("risk_signal_delta"))
        resolution_signal = bool(merge_signals.get("resolution_signal"))

        if resolution_signal and from_state != "resolved":
            return self._decision(
                from_state,
                "resolved",
                "resolution_signal",
                merge_signals=merge_signals,
                article_count=article_count,
                source_count=source_count,
            )

        if from_state == "new" and (article_count >= 2 or source_count >= 2):
            return self._decision(
                from_state,
                "active",
                "event_confirmed",
                merge_signals=merge_signals,
                article_count=article_count,
                source_count=source_count,
            )

        if self._should_escalate(
            from_state,
            confidence=confidence,
            new_entity_count=new_entity_count,
            new_region_count=new_region_count,
            risk_signal_delta=risk_signal_delta,
        ):
            return self._decision(
                from_state,
                "escalating",
                "impact_scope_expanded",
                merge_signals=merge_signals,
                article_count=article_count,
                source_count=source_count,
            )

        novelty_score = self._novelty_score(
            new_entity_count=new_entity_count,
            new_region_count=new_region_count,
            risk_signal_delta=risk_signal_delta,
        )
        if self._should_update(from_state, novelty_score=novelty_score):
            return self._decision(
                from_state,
                "updated",
                "material_new_facts",
                merge_signals=merge_signals,
                article_count=article_count,
                source_count=source_count,
            )

        if self._should_stabilize(
            from_state,
            support_score=support_score,
            novelty_score=novelty_score,
            risk_signal_delta=risk_signal_delta,
        ):
            return self._decision(
                from_state,
                "stabilizing",
                "corroboration_without_new_scope",
                merge_signals=merge_signals,
                article_count=article_count,
                source_count=source_count,
            )

        return None

    def evaluate_dormancy(
        self,
        event: Mapping[str, Any],
        *,
        as_of: datetime | None = None,
    ) -> EventStateDecision | None:
        from_state = self._normalize_state(event.get("status"))
        if from_state in {"resolved", "dormant"}:
            return None

        reference_time = (
            self._optional_datetime(event.get("latest_article_at"))
            or self._optional_datetime(event.get("last_updated_at"))
            or self._optional_datetime(event.get("started_at"))
        )
        if reference_time is None:
            return None

        current_time = as_of or datetime.now(UTC)
        if current_time.tzinfo is None:
            current_time = current_time.replace(tzinfo=UTC)

        if current_time - reference_time < self.dormant_after:
            return None

        return EventStateDecision(
            from_state=from_state,
            to_state="dormant",
            reason="event_stale",
            metadata={
                "dormant_after_hours": round(
                    self.dormant_after.total_seconds() / 3600, 3
                ),
                "last_activity_at": reference_time.isoformat(),
            },
        )

    def _should_escalate(
        self,
        from_state: str,
        *,
        confidence: float,
        new_entity_count: int,
        new_region_count: int,
        risk_signal_delta: float,
    ) -> bool:
        if from_state in {"resolved", "dormant"}:
            return False
        if confidence < self.escalate_confidence_threshold:
            return False
        return (
            new_region_count > 0
            or new_entity_count >= 2
            or risk_signal_delta > 0
        )

    def _should_update(self, from_state: str, *, novelty_score: float) -> bool:
        if from_state in {"new", "resolved", "dormant"}:
            return False
        return novelty_score >= self.update_novelty_threshold

    def _should_stabilize(
        self,
        from_state: str,
        *,
        support_score: float,
        novelty_score: float,
        risk_signal_delta: float,
    ) -> bool:
        if from_state not in {"updated", "escalating"}:
            return False
        if support_score < 0.65:
            return False
        return novelty_score <= 0 and risk_signal_delta <= 0

    def _novelty_score(
        self,
        *,
        new_entity_count: int,
        new_region_count: int,
        risk_signal_delta: float,
    ) -> float:
        return round(
            min(
                1.0,
                new_entity_count * 0.15
                + new_region_count * 0.25
                + max(risk_signal_delta, 0.0) * 0.3,
            ),
            3,
        )

    def _decision(
        self,
        from_state: str,
        to_state: str,
        reason: str,
        *,
        merge_signals: Mapping[str, Any],
        article_count: int,
        source_count: int,
    ) -> EventStateDecision:
        return EventStateDecision(
            from_state=from_state,
            to_state=to_state,
            reason=reason,
            metadata={
                "article_count": article_count,
                "source_count": source_count,
                "confidence": round(self._safe_float(merge_signals.get("confidence")), 3),
                "support_score": round(
                    self._safe_float(merge_signals.get("support_score")), 3
                ),
                "new_entity_count": self._safe_int(
                    merge_signals.get("new_entity_count")
                ),
                "new_region_count": self._safe_int(
                    merge_signals.get("new_region_count")
                ),
                "risk_signal_delta": round(
                    self._safe_float(merge_signals.get("risk_signal_delta")),
                    3,
                ),
                "resolution_signal": bool(merge_signals.get("resolution_signal")),
            },
        )

    @staticmethod
    def _normalize_state(value: Any) -> str:
        if not isinstance(value, str):
            return "new"
        normalized = value.strip().lower()
        return normalized or "new"

    @staticmethod
    def _optional_datetime(value: Any) -> datetime | None:
        if not isinstance(value, datetime):
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value

    @staticmethod
    def _safe_float(value: Any) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return 0.0

    @staticmethod
    def _safe_int(value: Any) -> int:
        try:
            return int(value)
        except (TypeError, ValueError):
            return 0


__all__ = ["EventStateDecision", "EventStateMachine"]
