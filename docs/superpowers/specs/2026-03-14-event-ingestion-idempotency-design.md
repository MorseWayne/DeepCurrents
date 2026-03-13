# Event Ingestion Idempotency Design

## Goal

Reduce noisy rerun logs and make event ingestion idempotent for already-ingested articles without changing event clustering behavior.

## Scope

- Replace per-article duplicate-refresh logs with aggregated source and run summaries.
- Make event creation idempotent when the same deterministic `event_id` is generated on rerun.
- Make event state transition writes idempotent for the same deterministic `transition_id`.
- Preserve existing refresh flow so reruns can still backfill features, dedup links, event members, and scores.

## Non-Goals

- No change to `DEDUP_HOURS_BACK`, merge thresholds, or event grouping rules.
- No change to article, feature, or Qdrant identifiers.
- No cleanup of historical log files.

## Design

### Collector Logging

`RSSCollector._ingest_event_intelligence_article()` keeps the existing duplicate-refresh control flow. When `create_article()` fails but `get_article()` confirms the article already exists, the collector increments `duplicate_refreshes` and continues refresh work without emitting a per-article log line.

The collector emits two summary logs instead:

- one source-level summary at the end of `fetch_source()` when that source refreshed any existing articles
- one run-level summary at the end of `collect_all()` with the total duplicate refresh count and source count

This keeps reruns observable without flooding logs with one line per repeated article.

### Event Repository Idempotency

`EventRepository.create_event()` becomes idempotent with `INSERT ... ON CONFLICT (event_id) DO NOTHING RETURNING *`.

If the insert conflicts, the repository reads and returns the existing event row instead of overwriting it.

This avoids clobbering previously enriched fields on rerun while keeping repository semantics simple for callers: builder code always receives a concrete event row whether it was inserted now or already existed.

### Transition Repository Idempotency

`EventRepository.record_state_transition()` becomes idempotent with `ON CONFLICT (transition_id) DO NOTHING RETURNING *`.

For reruns with the same deterministic `transition_id`, the repository reads and returns the existing transition instead of raising a primary-key error.

### Builder Behavior

`EventBuilder` stays structurally unchanged. Once repository writes are idempotent:

- new-event creation no longer fails on rerun
- member insertion continues through the existing `ON CONFLICT (event_id, article_id)` path
- score writes continue through the existing `ON CONFLICT (event_id, profile)` path

This keeps the fix narrow and avoids accidental clustering behavior changes.

## Risks

- Duplicate refresh summaries no longer include article URLs, so debugging a specific repeated article now requires querying the database or temporarily increasing logging.
- Historical noisy log lines remain in the existing log file until rotation or truncation.

## Validation

- Repository tests for duplicate `event_id` create path.
- Repository tests for duplicate `transition_id` transition path.
- Collector tests asserting duplicate article refresh is still processed and is only reported via source/run summary logs.
- Static validation with `py_compile`.
