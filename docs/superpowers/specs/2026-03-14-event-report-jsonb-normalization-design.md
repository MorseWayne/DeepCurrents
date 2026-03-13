# Event Report JSONB Normalization Design

## Background

The event-centric report flow can incorrectly emit "没有新的事件变化需要报告" even when ingestion succeeds and ranked events exist.

Observed runtime evidence on 2026-03-14:

- ingestion completed with non-zero inserted articles and touched events
- ranking and evidence selection still produced candidate events
- downstream report context selection ended with zero selected events/themes
- `event_briefs.brief_json` read back from PostgreSQL through `asyncpg` as `str`, not `dict`

The current reporting pipeline frequently treats JSON payloads as usable only when they are already `Mapping` instances. When a JSONB field arrives as a string, downstream code silently collapses it to `{}` and the report flow degrades into a false "no event changes" outcome.

## Goal

Restore correct report generation when PostgreSQL JSONB values are surfaced as strings, while keeping the change narrowly scoped and safe for an already-active code path.

## Non-Goals

- broad repository refactors unrelated to JSON normalization
- redesigning the report ranking/context policy
- changing report selection thresholds

## Approaches Considered

### 1. Consumer-only fallback

Parse string payloads only where `brief_json` is consumed by reporting components.

Pros:

- smallest code change
- fastest report recovery

Cons:

- duplicates parsing logic
- leaves similar JSONB issues in other repositories/components

### 2. Connection-layer only fix

Rely only on PostgreSQL codec configuration so JSON/JSONB always arrives as native Python objects.

Pros:

- corrects the problem near the source
- keeps consumer logic clean

Cons:

- assumes every live pool path uses the codec correctly
- does not protect against tests, scripts, or legacy paths returning strings

### 3. Layered fix (chosen)

Normalize JSON payloads in shared repository support and add consumer-side tolerance for string-backed JSON payloads where reporting depends on them.

Pros:

- fixes the current production symptom
- reduces recurrence across repositories
- remains defensive if some connection path still returns strings

Cons:

- slightly broader than a one-line hotfix

## Chosen Design

### Shared normalization

Add a small shared helper in repository support that:

- returns mappings/lists unchanged
- parses JSON strings into Python objects
- falls back to the original scalar or an empty container when parsing is not possible

This helper becomes the standard way to normalize JSONB-backed repository fields.

### Reporting-path tolerance

Update the report/event brief consumers so that `brief_json` is normalized before field access.

Scope includes:

- event brief metrics
- theme grouping/summarization
- report context building
- any report trace path that assumes `brief_json` is already a mapping

### Verification strategy

Add regression coverage for the real failure mode:

- repository/runtime path where `brief_json` is string-backed
- event summarizer metrics still read score/confidence/evidence correctly
- report context builder can still select events/themes from string-backed brief payloads

## Error Handling

- Invalid JSON strings should not crash report generation.
- Invalid JSON should degrade to empty payload behavior only for that record.
- The pipeline should remain deterministic and log-driven.

## Testing Plan

- keep current unit coverage green
- add regression tests for string-backed `brief_json`
- run targeted tests for:
  - repository support normalization
  - event summarizer
  - report context builder
  - report engine/report flow

## Success Criteria

- string-backed `brief_json` no longer causes zero selected events/themes
- false "没有新的事件变化需要报告" is removed for this reproduction path
- new regression tests fail before the fix and pass after the fix

## Notes

- Full skill-prescribed spec-review automation is unavailable in this session because no spec-review subagent or `writing-plans` skill is exposed here.
- Implementation will proceed with the approved design above and targeted verification in-place.
