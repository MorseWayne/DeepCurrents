from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from src.services.evaluation_runner import EvaluationRunner


def test_evaluation_runner_runs_all_default_suites():
    runner = EvaluationRunner()

    result = runner.run_all(profile="risk_daily")

    assert result["profile"] == "risk_daily"
    assert len(result["suites"]) == 4

    suites = {item["suite"]: item for item in result["suites"]}
    assert suites["duplicate_pairs"]["status"] == "passed"
    assert suites["same_event_pairs"]["status"] == "passed"
    assert suites["top_event_relevance"]["status"] == "passed"
    assert suites["final_report_review"]["status"] == "not_configured"

    assert suites["duplicate_pairs"]["metrics"]["duplicate_leakage_rate"] == 0.0
    assert suites["same_event_pairs"]["metrics"]["same_event_miss_rate"] == 0.0
    assert suites["top_event_relevance"]["metrics"]["top_k_precision"] == 1.0
    assert suites["top_event_relevance"]["metrics"]["critical_miss_rate"] == 0.0

    assert result["summary"]["suite_count"] == 4
    assert result["summary"]["passed_suite_count"] == 3
    assert result["summary"]["failed_suite_count"] == 0
    assert result["summary"]["not_configured_suite_count"] == 1
    assert result["summary"]["duplicate_leakage_rate"] == 0.0
    assert result["summary"]["critical_miss_rate"] == 0.0
    assert result["summary"]["top_k_precision"] == 1.0
    assert result["summary"]["article_to_event_compression_ratio"] is None


def test_evaluation_runner_uses_injected_resolvers_and_provider():
    provider_calls: list[dict[str, Any]] = []

    def ranked_event_provider(payload: dict[str, Any]) -> list[dict[str, Any]]:
        provider_calls.append(dict(payload))
        return [
            {"event_id": "evt_oil_inventory_001"},
            {"event_id": "evt_turkey_cb_001"},
            {"event_id": "evt_red_sea_001"},
        ]

    runner = EvaluationRunner(
        duplicate_relation_resolver=lambda left, right: False,
        same_event_resolver=lambda left, right: False,
        ranked_event_provider=ranked_event_provider,
    )

    result = runner.run_all()
    suites = {item["suite"]: item for item in result["suites"]}

    assert provider_calls[0]["query_id"] == "top-2026-03-13-am"
    assert suites["duplicate_pairs"]["status"] == "failed"
    assert suites["duplicate_pairs"]["samples_failed"] == 2
    assert suites["same_event_pairs"]["status"] == "failed"
    assert suites["same_event_pairs"]["samples_failed"] == 2
    assert suites["top_event_relevance"]["status"] == "failed"
    assert suites["top_event_relevance"]["metrics"]["top_k_precision"] == 0.5
    assert suites["top_event_relevance"]["metrics"]["critical_miss_rate"] == 0.5
    assert suites["top_event_relevance"]["failures"][0]["sample_id"] == "evt_red_sea_001"


def test_evaluation_runner_exposes_final_report_review_placeholder():
    runner = EvaluationRunner()

    suite = runner.run_final_report_review_placeholder()

    assert suite["suite"] == "final_report_review"
    assert suite["status"] == "not_configured"
    assert suite["samples_total"] == 0
    assert suite["metrics"]["reason"]


def test_evaluation_runner_sample_output_fixture_is_well_formed():
    sample_path = (
        Path(__file__).resolve().parent
        / "fixtures"
        / "event_intelligence"
        / "evaluation_result_sample.json"
    )

    payload = json.loads(sample_path.read_text(encoding="utf-8"))

    assert payload["summary"]["suite_count"] == 4
    assert payload["suites"][0]["suite"] == "duplicate_pairs"
