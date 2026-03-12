# AI Context Budget Optimization Design (Python `src/` only)

- Date: 2026-03-12
- Scope: `src/` (Python main pipeline) only; `src_ts/` excluded
- Status: Approved for implementation

## 1. Background

Current context budgeting in `src/services/ai_service.py` uses fixed percentage splits over `AI_MAX_CONTEXT_TOKENS` and rough char-based token estimation. This has three problems:

1. It does not align with the model's real context window.
2. It does not account for final strategist input growth (raw context + intermediate agent outputs + market block + templates).
3. It cannot re-balance budget based on actual segment utilization.

## 2. Decisions Confirmed

1. Remove `AI_MAX_CONTEXT_TOKENS` from runtime budgeting logic.
2. Resolve model context window at runtime from provider metadata; if metadata fails, fallback to local model-window mapping; if still unknown, fallback to conservative `16000`.
3. Output reserve is ratio-based (8%) with built-in min/max clamps.
4. Do not introduce new `.env` config in this iteration.
5. On full resolution failure, continue with conservative fallback rather than hard-failing.

## 3. Goals and Non-Goals

### Goals

1. Keep prompt input within practical model limits per request.
2. Improve budget utilization across news/cluster/trending context blocks.
3. Add a final pre-send guard for strategist input to avoid over-window failures.
4. Preserve current report generation behavior and fallback robustness.

### Non-Goals

1. No TypeScript pipeline changes.
2. No new external configuration surface in this phase.
3. No prompt-content redesign outside budget controls.

## 4. Proposed Architecture

All changes are in `src/services/ai_service.py` (or helper module under `src/services/` if extraction is cleaner).

### 4.1 Context Window Resolver

Add runtime resolver:

1. Try provider metadata API to obtain context window for the active model.
2. On failure, use internal `MODEL_CONTEXT_WINDOW_FALLBACKS` mapping.
3. If model is absent in mapping, use `16000`.
4. Cache successful lookups with short TTL to reduce metadata traffic.

### 4.2 Input Budget Calculator

Given `context_window`:

1. `output_reserve = clamp(context_window * 0.08, RESERVE_MIN, RESERVE_MAX)`
2. `usable_input = context_window - output_reserve - SAFETY_MARGIN - PROMPT_OVERHEAD`
3. Ensure lower bound (never below minimal working floor).

Constants are code-level defaults in this iteration.

### 4.3 Dynamic Segment Allocation

Build raw context with dynamic allocation:

1. Initial weights: `news=65%`, `cluster=20%`, `trending=15%`.
2. If a segment underuses budget, return remainder to a reflow pool.
3. Reflow priority: `news > cluster > trending`.
4. Final combined context must stay within `usable_input`.

For Python current pipeline, trending may be absent; its share naturally reflows.

### 4.4 Strategist Input Guard (Second Pass)

Before MarketStrategist call, estimate full composed input:

1. raw context
2. macro output
3. sentiment output
4. market data block
5. template/system overhead

If over budget, trim in priority order:

1. low-priority raw context entries
2. cluster context
3. high-priority raw news (last resort)

Always enforce a final hard cap before sending request.

## 5. Data Flow Changes

1. `generate_daily_report()` resolves effective context window per active model/provider.
2. It computes `usable_input` and composes `raw_context` under that budget.
3. Agent calls run as before.
4. Strategist input is assembled and passed through guard compressor.
5. Strategist call executes with bounded input.

## 6. Error Handling and Observability

### Error Handling

1. Metadata API errors: warn and degrade to mapping/fallback.
2. Budget computation anomalies: fallback to conservative defaults.
3. Guard cannot fully satisfy size target: force hard truncation to safe bound.

### Logging (no content leakage)

Per report run, log:

1. `model`, `resolved_window`, `output_reserve`, `safety_margin`, `usable_input`
2. segment allocations and actual usage
3. strategist pre/post guard token estimate and trimmed sections

Only lengths/counters are logged, not raw text body.

## 7. Test Plan

Update/add tests under `tests/`:

1. `test_ai_service`: metadata success path uses runtime window.
2. `test_ai_service`: metadata fail + mapping hit path.
3. `test_ai_service`: metadata fail + mapping miss uses `16000` fallback.
4. `test_ai_service`: news builder degrades to `header-only` under tight budget.
5. `test_ai_service`: strategist guard trims oversized input and still proceeds.
6. `test_config`: remove assertions that depend on `AI_MAX_CONTEXT_TOKENS` behavior.

## 8. Compatibility and Rollout

1. Keep `.env` key temporarily tolerated by settings layer for backward compatibility.
2. Mark `AI_MAX_CONTEXT_TOKENS` as deprecated in docs; runtime logic no longer depends on it.
3. Rollout should be code + tests + README/doc sync in the same change set.

## 9. Risks and Mitigations

1. Provider metadata heterogeneity.
   - Mitigation: robust parser + mapping fallback + safe default.
2. Token estimation inaccuracy.
   - Mitigation: safety margin + second-pass guard + hard cap.
3. Quality loss from aggressive trimming.
   - Mitigation: priority-aware trimming with high-priority content protected until last step.

