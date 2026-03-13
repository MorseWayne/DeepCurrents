from __future__ import annotations

from datetime import UTC, datetime

from src.services.event_state_machine import EventStateMachine


def test_event_state_machine_promotes_new_event_to_active_after_second_article():
    machine = EventStateMachine()

    decision = machine.evaluate(
        {"event_id": "evt_1", "status": "new"},
        article={"article_id": "art_2"},
        article_count=2,
        source_count=2,
        merge_signals={"confidence": 0.88, "support_score": 0.91},
        anchor_time=datetime(2026, 3, 13, 6, 0, tzinfo=UTC),
    )

    assert decision is not None
    assert decision.from_state == "new"
    assert decision.to_state == "active"
    assert decision.reason == "event_confirmed"


def test_event_state_machine_marks_escalating_when_scope_expands():
    machine = EventStateMachine()

    decision = machine.evaluate(
        {"event_id": "evt_1", "status": "active"},
        article={"article_id": "art_3"},
        article_count=4,
        source_count=3,
        merge_signals={
            "confidence": 0.92,
            "support_score": 0.89,
            "new_entity_count": 2,
            "new_region_count": 1,
            "risk_signal_delta": 1.0,
        },
        anchor_time=datetime(2026, 3, 13, 8, 0, tzinfo=UTC),
    )

    assert decision is not None
    assert decision.to_state == "escalating"
    assert decision.reason == "impact_scope_expanded"


def test_event_state_machine_marks_resolved_on_resolution_signal():
    machine = EventStateMachine()

    decision = machine.evaluate(
        {"event_id": "evt_1", "status": "updated"},
        article={"article_id": "art_4"},
        article_count=5,
        source_count=3,
        merge_signals={
            "confidence": 0.74,
            "support_score": 0.77,
            "resolution_signal": True,
        },
        anchor_time=datetime(2026, 3, 13, 9, 0, tzinfo=UTC),
    )

    assert decision is not None
    assert decision.to_state == "resolved"
    assert decision.reason == "resolution_signal"


def test_event_state_machine_marks_escalating_event_as_stabilizing_when_only_corroboration_arrives():
    machine = EventStateMachine()

    decision = machine.evaluate(
        {"event_id": "evt_1", "status": "escalating"},
        article={"article_id": "art_5"},
        article_count=6,
        source_count=4,
        merge_signals={
            "confidence": 0.83,
            "support_score": 0.78,
            "new_entity_count": 0,
            "new_region_count": 0,
            "risk_signal_delta": 0.0,
        },
        anchor_time=datetime(2026, 3, 13, 10, 0, tzinfo=UTC),
    )

    assert decision is not None
    assert decision.to_state == "stabilizing"
    assert decision.reason == "corroboration_without_new_scope"


def test_event_state_machine_exposes_dormancy_check():
    machine = EventStateMachine(dormant_after_hours=48)

    decision = machine.evaluate_dormancy(
        {
            "event_id": "evt_1",
            "status": "active",
            "latest_article_at": datetime(2026, 3, 10, 0, 0, tzinfo=UTC),
        },
        as_of=datetime(2026, 3, 13, 12, 0, tzinfo=UTC),
    )

    assert decision is not None
    assert decision.from_state == "active"
    assert decision.to_state == "dormant"
    assert decision.reason == "event_stale"
