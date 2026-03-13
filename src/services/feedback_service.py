from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from typing import Any, Protocol
from uuid import uuid4


ISSUE_ACTIONS: dict[str, list[str]] = {
    "false_merge": [
        "Review merge signals, entity overlap, region overlap, and conflict guards.",
        "Inspect same-event thresholds and semantic merge confidence gates.",
    ],
    "missed_event": [
        "Review ranking thresholds, incremental selection window, and theme quotas.",
        "Check whether relevant events were filtered out before report context build.",
    ],
    "weak_evidence": [
        "Review evidence source diversity, tier weighting, and contradiction retention.",
        "Inspect whether primary evidence slots are dominated by near-duplicate sources.",
    ],
    "summary_distortion": [
        "Review brief schema fidelity, prompt wording, and context truncation behavior.",
        "Inspect whether key caveats or contradictions were dropped before generation.",
    ],
    "ranking_error": [
        "Review scoring profile weights and novelty/corroboration/source-quality dimensions.",
        "Compare selected event order against report trace rationale and profile output.",
    ],
}
VALID_LABEL_TYPES = {"report_review", "report_event_review"}
VALID_DECISIONS = {"confirmed", "rejected", "needs_followup"}


class FeedbackRepositoryLike(Protocol):
    async def create_label(self, label: Mapping[str, Any]) -> dict[str, Any]: ...

    async def list_labels(
        self,
        *,
        label_type: str | None = None,
        subject_id: str | None = None,
        source: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]: ...


class ReportRunTrackerLike(Protocol):
    async def get_report_trace(self, report_run_id: str) -> dict[str, Any] | None: ...


class FeedbackService:
    def __init__(
        self,
        feedback_repository: FeedbackRepositoryLike,
        report_run_tracker: ReportRunTrackerLike | None = None,
    ):
        self.feedback_repository = feedback_repository
        self.report_run_tracker = report_run_tracker

    async def record_report_review(
        self,
        *,
        report_run_id: str,
        issue_type: str,
        decision: str,
        reviewer_id: str,
        reviewer_role: str | None = None,
        expected_action: str | None = None,
        notes: str = "",
        source: str = "manual",
    ) -> dict[str, Any]:
        label_value = self._build_label_value(
            issue_type=issue_type,
            decision=decision,
            report_run_id=report_run_id,
            reviewer_id=reviewer_id,
            reviewer_role=reviewer_role,
            expected_action=expected_action,
        )
        return await self.feedback_repository.create_label(
            {
                "label_id": self._label_id("report_review", report_run_id),
                "label_type": "report_review",
                "subject_id": report_run_id,
                "label_value": label_value,
                "source": source,
                "notes": notes,
            }
        )

    async def record_report_event_review(
        self,
        *,
        report_run_id: str,
        issue_type: str,
        decision: str,
        reviewer_id: str,
        event_id: str,
        reviewer_role: str | None = None,
        brief_id: str | None = None,
        article_id: str | None = None,
        expected_action: str | None = None,
        notes: str = "",
        source: str = "manual",
    ) -> dict[str, Any]:
        trace_context = await self._resolve_trace_context(
            report_run_id=report_run_id,
            event_id=event_id,
        )
        label_value = self._build_label_value(
            issue_type=issue_type,
            decision=decision,
            report_run_id=report_run_id,
            reviewer_id=reviewer_id,
            reviewer_role=reviewer_role,
            event_id=event_id,
            brief_id=brief_id or self._text(trace_context.get("brief_id")),
            article_id=article_id,
            expected_action=expected_action,
            state_change=self._text(trace_context.get("state_change")),
            why_it_matters=self._text(trace_context.get("why_it_matters")),
            evidence_refs=self._text_list(trace_context.get("evidence_refs")),
            out_of_trace_target=bool(trace_context.get("out_of_trace_target")),
        )
        return await self.feedback_repository.create_label(
            {
                "label_id": self._label_id("report_event_review", report_run_id),
                "label_type": "report_event_review",
                "subject_id": report_run_id,
                "label_value": label_value,
                "source": source,
                "notes": notes,
            }
        )

    async def list_feedback(
        self,
        *,
        subject_id: str | None = None,
        label_type: str | None = None,
        issue_type: str | None = None,
        source: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        self._validate_label_type(label_type)
        rows = await self.feedback_repository.list_labels(
            subject_id=subject_id,
            label_type=label_type,
            source=source,
            limit=limit,
        )
        normalized = [self._normalize_label(item) for item in rows]
        if issue_type:
            expected = issue_type.strip()
            normalized = [
                item
                for item in normalized
                if self._label_issue_type(item) == expected
            ]
        return normalized

    async def summarize_feedback_actions(
        self,
        *,
        subject_id: str | None = None,
        label_type: str | None = None,
        issue_type: str | None = None,
        source: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        labels = await self.list_feedback(
            subject_id=subject_id,
            label_type=label_type,
            issue_type=issue_type,
            source=source,
            limit=limit,
        )
        grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for label in labels:
            issue = self._label_issue_type(label)
            if not issue:
                continue
            grouped[issue].append(label)

        summaries: list[dict[str, Any]] = []
        for issue, items in grouped.items():
            affected_report_runs = sorted(
                {
                    self._text(item.get("subject_id"))
                    for item in items
                    if self._text(item.get("subject_id"))
                }
            )
            affected_event_ids = sorted(
                {
                    self._text(
                        self._mapping(item.get("label_value"))
                        .get("target", {})
                        .get("event_id")
                    )
                    for item in items
                    if self._text(
                        self._mapping(item.get("label_value"))
                        .get("target", {})
                        .get("event_id")
                    )
                }
            )
            summaries.append(
                {
                    "issue_type": issue,
                    "feedback_count": len(items),
                    "affected_report_runs": affected_report_runs,
                    "affected_event_ids": affected_event_ids,
                    "recommended_actions": list(ISSUE_ACTIONS.get(issue, [])),
                }
            )

        summaries.sort(
            key=lambda item: (-self._safe_int(item.get("feedback_count")), item["issue_type"])
        )
        return summaries

    async def _resolve_trace_context(
        self,
        *,
        report_run_id: str,
        event_id: str,
    ) -> dict[str, Any]:
        if self.report_run_tracker is None:
            return {"out_of_trace_target": True}

        trace = await self.report_run_tracker.get_report_trace(report_run_id)
        if not trace:
            return {"out_of_trace_target": True}

        for item in self._sequence_of_mappings(trace.get("event_links")):
            if self._text(item.get("event_id")) != event_id:
                continue
            rationale_json = self._mapping(item.get("rationale_json"))
            return {
                "brief_id": self._text(rationale_json.get("brief_id")),
                "state_change": self._text(rationale_json.get("state_change")),
                "why_it_matters": self._text(rationale_json.get("why_it_matters")),
                "evidence_refs": self._text_list(rationale_json.get("evidence_refs")),
                "out_of_trace_target": False,
            }
        return {"out_of_trace_target": True}

    def _build_label_value(
        self,
        *,
        issue_type: str,
        decision: str,
        report_run_id: str,
        reviewer_id: str,
        reviewer_role: str | None = None,
        event_id: str | None = None,
        brief_id: str | None = None,
        article_id: str | None = None,
        expected_action: str | None = None,
        state_change: str | None = None,
        why_it_matters: str | None = None,
        evidence_refs: Sequence[str] | None = None,
        out_of_trace_target: bool = False,
    ) -> dict[str, Any]:
        normalized_issue = self._text(issue_type)
        normalized_decision = self._text(decision)
        if not normalized_issue:
            raise ValueError("issue_type is required")
        if normalized_decision not in VALID_DECISIONS:
            raise ValueError(f"unsupported decision: {normalized_decision}")

        return {
            "issue_type": normalized_issue,
            "decision": normalized_decision,
            "target": {
                "report_run_id": report_run_id,
                **({"event_id": event_id} if self._text(event_id) else {}),
                **({"brief_id": brief_id} if self._text(brief_id) else {}),
                **({"article_id": article_id} if self._text(article_id) else {}),
            },
            "context": {
                **({"state_change": state_change} if self._text(state_change) else {}),
                **({"why_it_matters": why_it_matters} if self._text(why_it_matters) else {}),
                **({"evidence_refs": list(evidence_refs or [])} if evidence_refs else {}),
                **({"expected_action": expected_action} if self._text(expected_action) else {}),
                **({"out_of_trace_target": True} if out_of_trace_target else {}),
            },
            "reviewer": {
                "reviewer_id": reviewer_id,
                **({"reviewer_role": reviewer_role} if self._text(reviewer_role) else {}),
            },
        }

    def _normalize_label(self, value: Mapping[str, Any]) -> dict[str, Any]:
        normalized = dict(value)
        normalized["label_value"] = self._mapping(value.get("label_value"))
        return normalized

    def _validate_label_type(self, label_type: str | None) -> None:
        if label_type is None:
            return
        if label_type not in VALID_LABEL_TYPES:
            raise ValueError(f"unsupported label_type: {label_type}")

    def _label_id(self, label_type: str, subject_id: str) -> str:
        timestamp = datetime.now(UTC).strftime("%Y%m%d%H%M%S")
        return f"{label_type}_{subject_id}_{timestamp}_{uuid4().hex[:8]}"

    def _label_issue_type(self, label: Mapping[str, Any]) -> str:
        label_value = self._mapping(label.get("label_value"))
        return self._text(label_value.get("issue_type"))

    @staticmethod
    def _mapping(value: Any) -> dict[str, Any]:
        return dict(value) if isinstance(value, Mapping) else {}

    @staticmethod
    def _sequence_of_mappings(value: Any) -> list[dict[str, Any]]:
        if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
            return []
        return [dict(item) for item in value if isinstance(item, Mapping)]

    @staticmethod
    def _text(value: Any) -> str:
        if value is None:
            return ""
        if isinstance(value, str):
            return value.strip()
        return str(value).strip()

    @staticmethod
    def _text_list(value: Any) -> list[str]:
        if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
            return []
        return [str(item).strip() for item in value if str(item).strip()]

    @staticmethod
    def _safe_int(value: Any) -> int:
        try:
            return int(value)
        except (TypeError, ValueError):
            return 0


__all__ = ["FeedbackService"]
