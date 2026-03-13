from __future__ import annotations

from typing import Any

import pytest

from src.services.feedback_service import FeedbackService


class FakeFeedbackRepository:
    def __init__(self):
        self.labels: list[dict[str, Any]] = []

    async def create_label(self, label: dict[str, Any]) -> dict[str, Any]:
        stored = dict(label)
        self.labels.append(stored)
        return dict(stored)

    async def list_labels(
        self,
        *,
        label_type: str | None = None,
        subject_id: str | None = None,
        source: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        items = [dict(item) for item in self.labels]
        if label_type:
            items = [item for item in items if item.get("label_type") == label_type]
        if subject_id:
            items = [item for item in items if item.get("subject_id") == subject_id]
        if source:
            items = [item for item in items if item.get("source") == source]
        return items[:limit]


class FakeReportRunTracker:
    def __init__(self):
        self.traces: dict[str, dict[str, Any]] = {}

    async def get_report_trace(self, report_run_id: str) -> dict[str, Any] | None:
        trace = self.traces.get(report_run_id)
        return dict(trace) if trace else None


def make_trace() -> dict[str, Any]:
    return {
        "report_run": {"report_run_id": "run_1"},
        "event_links": [
            {
                "event_id": "evt_energy",
                "rationale_json": {
                    "brief_id": "brief_evt_energy_v1",
                    "state_change": "escalated",
                    "why_it_matters": "Energy risk premium is rising.",
                    "evidence_refs": ["art_1", "art_2"],
                },
            }
        ],
        "summary": {"report_run_id": "run_1"},
    }


@pytest.mark.asyncio
async def test_feedback_service_records_report_review():
    repo = FakeFeedbackRepository()
    service = FeedbackService(repo)

    stored = await service.record_report_review(
        report_run_id="run_1",
        issue_type="summary_distortion",
        decision="confirmed",
        reviewer_id="alice",
        reviewer_role="editor",
        expected_action="tighten prompt phrasing",
        notes="summary overstates certainty",
    )

    assert stored["label_type"] == "report_review"
    assert stored["subject_id"] == "run_1"
    assert stored["label_value"]["issue_type"] == "summary_distortion"
    assert stored["label_value"]["reviewer"]["reviewer_id"] == "alice"


@pytest.mark.asyncio
async def test_feedback_service_records_report_event_review_with_trace_context():
    repo = FakeFeedbackRepository()
    tracker = FakeReportRunTracker()
    tracker.traces["run_1"] = make_trace()
    service = FeedbackService(repo, tracker)

    stored = await service.record_report_event_review(
        report_run_id="run_1",
        event_id="evt_energy",
        issue_type="weak_evidence",
        decision="needs_followup",
        reviewer_id="bob",
        notes="needs more independent sources",
    )

    label_value = stored["label_value"]
    assert stored["label_type"] == "report_event_review"
    assert label_value["target"]["event_id"] == "evt_energy"
    assert label_value["target"]["brief_id"] == "brief_evt_energy_v1"
    assert label_value["context"]["state_change"] == "escalated"
    assert label_value["context"]["evidence_refs"] == ["art_1", "art_2"]
    assert "out_of_trace_target" not in label_value["context"]


@pytest.mark.asyncio
async def test_feedback_service_marks_out_of_trace_targets_without_failing():
    repo = FakeFeedbackRepository()
    tracker = FakeReportRunTracker()
    tracker.traces["run_1"] = make_trace()
    service = FeedbackService(repo, tracker)

    stored = await service.record_report_event_review(
        report_run_id="run_1",
        event_id="evt_missing",
        issue_type="missed_event",
        decision="confirmed",
        reviewer_id="carol",
    )

    assert stored["label_value"]["target"]["event_id"] == "evt_missing"
    assert stored["label_value"]["context"]["out_of_trace_target"] is True


@pytest.mark.asyncio
async def test_feedback_service_lists_feedback_and_filters_by_issue_type():
    repo = FakeFeedbackRepository()
    service = FeedbackService(repo)

    await service.record_report_review(
        report_run_id="run_1",
        issue_type="summary_distortion",
        decision="confirmed",
        reviewer_id="alice",
    )
    await service.record_report_review(
        report_run_id="run_1",
        issue_type="ranking_error",
        decision="needs_followup",
        reviewer_id="alice",
    )

    labels = await service.list_feedback(
        subject_id="run_1",
        label_type="report_review",
        issue_type="ranking_error",
    )

    assert len(labels) == 1
    assert labels[0]["label_value"]["issue_type"] == "ranking_error"


@pytest.mark.asyncio
async def test_feedback_service_summarizes_feedback_actions():
    repo = FakeFeedbackRepository()
    service = FeedbackService(repo)

    await service.record_report_review(
        report_run_id="run_1",
        issue_type="summary_distortion",
        decision="confirmed",
        reviewer_id="alice",
    )
    await service.record_report_event_review(
        report_run_id="run_1",
        event_id="evt_energy",
        issue_type="ranking_error",
        decision="confirmed",
        reviewer_id="alice",
    )
    await service.record_report_event_review(
        report_run_id="run_2",
        event_id="evt_energy",
        issue_type="ranking_error",
        decision="needs_followup",
        reviewer_id="bob",
    )

    summary = await service.summarize_feedback_actions()

    assert summary[0]["issue_type"] == "ranking_error"
    assert summary[0]["feedback_count"] == 2
    assert summary[0]["affected_event_ids"] == ["evt_energy"]
    assert summary[0]["recommended_actions"]
    assert summary[1]["issue_type"] == "summary_distortion"
