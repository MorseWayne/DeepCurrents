from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
import json
from typing import Any


def safe_ratio(
    numerator: int | float,
    denominator: int | float,
    *,
    digits: int = 4,
) -> float:
    try:
        denominator_value = float(denominator)
    except (TypeError, ValueError):
        return 0.0
    if denominator_value == 0:
        return 0.0
    try:
        numerator_value = float(numerator)
    except (TypeError, ValueError):
        return 0.0
    return round(numerator_value / denominator_value, digits)


def mean_float(values: Sequence[int | float], *, digits: int = 4) -> float:
    numeric = [float(value) for value in values]
    if not numeric:
        return 0.0
    return round(sum(numeric) / len(numeric), digits)


@dataclass(frozen=True)
class StructuredLogEvent:
    event: str
    stage: str
    payload: dict[str, Any]
    context: dict[str, Any]
    emitted_at: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def default_ingestion_metrics(*, sources_total: int = 0) -> dict[str, Any]:
    return {
        "sources_total": max(sources_total, 0),
        "sources_skipped": 0,
        "sources_failed": 0,
        "articles_seen": 0,
        "articles_inserted": 0,
        "duplicate_refreshes": 0,
        "feature_failures": 0,
        "cheap_dedup_links": 0,
        "semantic_dedup_links": 0,
        "events_created": 0,
        "events_updated": 0,
        "event_enrichment_failures": 0,
        "events_touched": 0,
        "article_to_event_compression_ratio": 0.0,
        "new_items": 0,
        "errors": 0,
        "skipped": 0,
    }


def build_ranking_metrics(
    ranked_items: Sequence[Mapping[str, Any]],
    *,
    profile: str,
    events_considered: int,
) -> dict[str, Any]:
    total_scores = [_safe_float(item.get("total_score")) for item in ranked_items]
    single_source = 0
    high_uncertainty = 0
    escalating = 0

    for item in ranked_items:
        score = _mapping(item.get("score"))
        payload = _mapping(score.get("payload"))
        explanation = _mapping(payload.get("explanation"))
        facts = _mapping(explanation.get("event_facts"))
        risk_flags = _text_set(explanation.get("risk_flags"))

        source_count = _safe_int(facts.get("source_count"))
        uncertainty_score = _safe_float(score.get("uncertainty_score"))
        status = _text(facts.get("status")).casefold()

        if source_count <= 1 or "single_source_event" in risk_flags:
            single_source += 1
        if uncertainty_score >= 0.5 or "elevated_uncertainty" in risk_flags:
            high_uncertainty += 1
        if status == "escalating" or "escalating_event" in risk_flags:
            escalating += 1

    ranked_count = len(ranked_items)
    return {
        "profile": profile,
        "events_considered": max(events_considered, 0),
        "events_ranked": ranked_count,
        "top_score": round(max(total_scores), 4) if total_scores else 0.0,
        "avg_total_score": mean_float(total_scores),
        "single_source_event_ratio": safe_ratio(single_source, ranked_count),
        "high_uncertainty_event_ratio": safe_ratio(high_uncertainty, ranked_count),
        "escalating_event_ratio": safe_ratio(escalating, ranked_count),
    }


def build_evidence_metrics(
    evidence_packages: Sequence[Mapping[str, Any]],
    *,
    profile: str,
    events_considered: int,
) -> dict[str, Any]:
    packages = [_mapping(item) for item in evidence_packages]
    with_evidence = 0
    selected_supporting_counts: list[int] = []
    selected_contradicting_counts: list[int] = []
    selected_articles = 0
    candidate_articles = 0
    contradiction_candidates = 0
    contradiction_retained = 0

    for package in packages:
        supporting = _sequence_of_mappings(package.get("supporting_evidence"))
        contradicting = _sequence_of_mappings(package.get("contradicting_evidence"))
        metadata = _mapping(package.get("selection_metadata"))
        supporting_count = len(supporting)
        contradicting_count = len(contradicting)

        if supporting_count + contradicting_count > 0:
            with_evidence += 1

        selected_supporting_counts.append(supporting_count)
        selected_contradicting_counts.append(contradicting_count)
        selected_articles += supporting_count + contradicting_count

        supporting_candidates = _safe_int(metadata.get("supporting_candidate_count"))
        contradicting_candidates = _safe_int(metadata.get("contradicting_candidate_count"))
        candidate_articles += supporting_candidates + contradicting_candidates

        if contradicting_candidates > 0:
            contradiction_candidates += 1
            if contradicting_count > 0:
                contradiction_retained += 1

    return {
        "profile": profile,
        "events_considered": max(events_considered, 0),
        "events_with_evidence": with_evidence,
        "event_cards_selected": with_evidence,
        "event_card_entry_ratio": safe_ratio(with_evidence, events_considered),
        "avg_supporting_evidence_count": mean_float(selected_supporting_counts),
        "avg_contradicting_evidence_count": mean_float(
            selected_contradicting_counts
        ),
        "contradiction_retention_rate": safe_ratio(
            contradiction_retained,
            contradiction_candidates,
        ),
        "evidence_compression_ratio": safe_ratio(selected_articles, candidate_articles),
    }


def build_report_metrics(
    *,
    raw_news_input_count: int,
    cluster_count: int,
    report_generated: bool,
    investment_trend_count: int,
    guard_stats: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    guard = _mapping(guard_stats)
    pre_tokens = _safe_int(guard.get("pre_guard_tokens"))
    post_tokens = _safe_int(guard.get("post_guard_tokens"))
    trimmed_sections = _text_list(guard.get("trimmed_sections"))
    return {
        "raw_news_input_count": max(raw_news_input_count, 0),
        "cluster_count": max(cluster_count, 0),
        "report_generated": bool(report_generated),
        "investment_trend_count": max(investment_trend_count, 0),
        "guard_pre_tokens": pre_tokens,
        "guard_post_tokens": post_tokens,
        "trimmed_sections": trimmed_sections,
        "budget_truncation_rate": safe_ratio(max(pre_tokens - post_tokens, 0), pre_tokens),
        "final_hard_cap_hit": "final-hard-cap" in trimmed_sections,
    }


def log_stage_metrics(
    logger: Any,
    stage: str,
    payload: Mapping[str, Any],
    **context: Any,
) -> dict[str, Any]:
    event = StructuredLogEvent(
        event="pipeline_metrics",
        stage=stage,
        payload=_normalize_for_json(payload),
        context=_normalize_for_json(context),
        emitted_at=datetime.now(UTC).isoformat(),
    )
    serialized = json.dumps(event.to_dict(), ensure_ascii=True, sort_keys=True)
    logger.info(serialized)
    return event.to_dict()


def _normalize_for_json(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {
            _text(key): _normalize_for_json(item)
            for key, item in value.items()
        }
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        return [_normalize_for_json(item) for item in value]
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC).isoformat()
        return value.isoformat()
    return value


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _sequence_of_mappings(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return []
    return [dict(item) for item in value if isinstance(item, Mapping)]


def _text_set(value: Any) -> set[str]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return set()
    return {_text(item).casefold() for item in value if _text(item)}


def _text_list(value: Any) -> list[str]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return []
    return [_text(item) for item in value if _text(item)]


def _safe_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _safe_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    return str(value).strip()


__all__ = [
    "StructuredLogEvent",
    "build_evidence_metrics",
    "build_ranking_metrics",
    "build_report_metrics",
    "default_ingestion_metrics",
    "log_stage_metrics",
    "mean_float",
    "safe_ratio",
]
