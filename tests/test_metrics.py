from __future__ import annotations

from datetime import UTC, datetime
import json
from unittest.mock import MagicMock

from src.services.metrics import (
    build_evidence_metrics,
    build_ranking_metrics,
    build_report_metrics,
    log_stage_metrics,
    safe_ratio,
)


def test_safe_ratio_and_report_metrics_handle_zero_denominators():
    assert safe_ratio(3, 0) == 0.0

    metrics = build_report_metrics(
        raw_news_input_count=0,
        cluster_count=0,
        report_generated=False,
        investment_trend_count=0,
        guard_stats={"pre_guard_tokens": 0, "post_guard_tokens": 0},
    )

    assert metrics["budget_truncation_rate"] == 0.0
    assert metrics["final_hard_cap_hit"] is False


def test_log_stage_metrics_serializes_json_payload():
    fake_logger = MagicMock()

    event = log_stage_metrics(
        fake_logger,
        "ranking",
        {"top_score": 0.91, "as_of": datetime(2026, 3, 13, 12, 0, tzinfo=UTC)},
        service="unit-test",
    )

    fake_logger.info.assert_called_once()
    serialized = fake_logger.info.call_args.args[0]
    payload = json.loads(serialized)
    assert payload["stage"] == "ranking"
    assert payload["payload"]["top_score"] == 0.91
    assert payload["payload"]["as_of"].startswith("2026-03-13T12:00:00")
    assert payload["context"]["service"] == "unit-test"
    assert payload == event


def test_metric_builders_compute_stage_ratios():
    ranking_metrics = build_ranking_metrics(
        [
            {
                "event_id": "evt_1",
                "total_score": 0.9,
                "score": {
                    "uncertainty_score": 0.7,
                    "payload": {
                        "explanation": {
                            "risk_flags": [
                                "single_source_event",
                                "elevated_uncertainty",
                            ],
                            "event_facts": {"source_count": 1, "status": "escalating"},
                        }
                    },
                },
            },
            {
                "event_id": "evt_2",
                "total_score": 0.6,
                "score": {
                    "uncertainty_score": 0.1,
                    "payload": {
                        "explanation": {
                            "risk_flags": [],
                            "event_facts": {"source_count": 3, "status": "updated"},
                        }
                    },
                },
            },
        ],
        profile="risk_daily",
        events_considered=2,
    )
    evidence_metrics = build_evidence_metrics(
        [
            {
                "supporting_evidence": [{"article_id": "art_1"}],
                "contradicting_evidence": [{"article_id": "art_2"}],
                "selection_metadata": {
                    "supporting_candidate_count": 3,
                    "contradicting_candidate_count": 1,
                },
            },
            {
                "supporting_evidence": [{"article_id": "art_3"}],
                "contradicting_evidence": [],
                "selection_metadata": {
                    "supporting_candidate_count": 2,
                    "contradicting_candidate_count": 0,
                },
            },
        ],
        profile="risk_daily",
        events_considered=2,
    )

    assert ranking_metrics["single_source_event_ratio"] == 0.5
    assert ranking_metrics["high_uncertainty_event_ratio"] == 0.5
    assert ranking_metrics["escalating_event_ratio"] == 0.5
    assert evidence_metrics["event_card_entry_ratio"] == 1.0
    assert evidence_metrics["contradiction_retention_rate"] == 1.0
    assert evidence_metrics["evidence_compression_ratio"] == 0.5
