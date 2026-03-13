# Macro Transmission Report Expansion Design

## Background

The current event-centric report output is structurally valid but too shallow in its conclusions.

Observed symptoms in the current report flow:

- executive summary, deep insights, and investment trends often restate the same point with little incremental value
- the report can describe events, but it does not clearly explain the transmission chain from event shock to macro variables to asset pricing to allocation stance
- when `MarketStrategist` output is sparse, fallback text collapses into generic summary language and loses analytical depth
- the current schema has no dedicated place for a macro-level transmission thesis or per-asset transmission breakdowns

The target improvement is not "longer prose". The target is a higher-dimensional report structure with explicit macro transmission reasoning.

## Goal

Extend the daily report format so it always presents:

- one macro-oriented "top-line transmission chain"
- two to four key asset breakdowns derived from that macro chain

This must remain compatible with the current pipeline and degrade safely when model output is incomplete.

## Non-Goals

- redesigning event ranking, clustering, or evidence selection
- requiring raw article access in the final report stage
- replacing existing `investmentTrends`; they remain as concise allocation output
- broad UI or notification redesign beyond rendering the new sections

## Approaches Considered

### 1. Prompt-only expansion

Ask the existing report model to write richer `economicAnalysis` and `investmentTrends` text without changing the schema.

Pros:

- smallest implementation surface
- no downstream model changes

Cons:

- unstable under sparse output
- difficult to validate or fallback deterministically
- still mixes macro explanation and asset conclusions into free text

### 2. Structured report expansion with deterministic fallback (chosen)

Add explicit schema fields for a macro transmission chain and asset transmission breakdowns, then normalize and backfill them when the model omits or weakly fills them.

Pros:

- directly addresses the missing report dimensions
- keeps macro reasoning and asset reasoning separate
- enables deterministic sparse fallback
- gives notifier/rendering a stable structure

Cons:

- requires coordinated updates across models, prompts, parsing, fallback, and rendering

### 3. Post-processing only

Leave the report schema unchanged and programmatically append a derived transmission section after report generation.

Pros:

- less dependent on LLM compliance
- easier to ship as a narrow patch

Cons:

- derived analysis quality is capped by existing terse fields
- creates two parallel report representations
- does not improve the JSON contract itself

## Chosen Design

### Report structure

Extend `DailyReport` with two optional fields:

- `macroTransmissionChain`
- `assetTransmissionBreakdowns`

`macroTransmissionChain` is the single macro thesis for the day. It answers:

- what the primary shock is
- which macro variables are being repriced first
- how those variables are flowing into market pricing
- what that implies for current allocation posture

Suggested shape:

- `headline`: one-sentence macro thesis
- `shockSource`: primary event/theme driver
- `macroVariables`: two to four macro variables
- `marketPricing`: cross-asset pricing impact summary
- `allocationImplication`: concise portfolio implication
- `steps`: ordered three to five step chain with `stage` and `driver`
- `timeframe`
- `confidence`

`assetTransmissionBreakdowns` holds two to four key assets or asset buckets. Each entry answers:

- current directional view
- which part of the macro chain it is expressing
- why the pricing impulse should continue or fade
- what signals would confirm or invalidate the view

Suggested shape per entry:

- `assetClass`
- `trend`
- `coreView`
- `transmissionPath`
- `keyDrivers`
- `watchSignals`
- `timeframe`
- `confidence`

### Report section roles

The new section boundaries are explicit:

- `executiveSummary`: short top-line framing
- `macroTransmissionChain`: the main macro transmission logic
- `globalEvents`: the most important underlying events
- `economicAnalysis`: supplementary narrative around the macro chain
- `assetTransmissionBreakdowns`: detailed asset-level transmission views
- `investmentTrends`: concise allocation summary

This prevents the current overlap where `economicAnalysis` and `investmentTrends` both attempt to carry the entire analytical load.

### Prompt changes

`MarketStrategist` must be instructed to produce:

- exactly one `macroTransmissionChain`
- two to four `assetTransmissionBreakdowns`
- a clear separation between macro transmission logic and asset-level trade implications

Prompt rules should explicitly reject event restatement as a substitute for transmission logic. The model should be told to express the chain in the form:

`shock -> macro variables -> market pricing -> allocation implication`

`MacroAnalyst` and `SentimentAnalyst` can remain structurally unchanged. Their existing outputs continue to feed the strategist, but the strategist becomes responsible for emitting the richer final report schema.

### Normalization

`AIService.normalize_daily_report_payload()` should normalize the new fields defensively:

- missing fields become empty optional structures rather than parse failures
- scalar or malformed list fields are coerced into stable containers where possible
- `trend`, `timeframe`, and `confidence` are normalized using the same conventions as current investment trends

Normalization should preserve backward compatibility so existing fixtures and historical report payloads continue to parse.

### Sparse fallback

This design requires deterministic fallback rather than prompt-only hope.

If `macroTransmissionChain` is missing or too sparse:

- derive it from the highest-priority selected event and strongest selected theme
- prefer `stateChange`, `whyItMatters`, `marketChannels`, `regions`, and theme summary fields
- always emit a usable four-part chain even if phrasing is conservative

If `assetTransmissionBreakdowns` is missing or too sparse:

- derive two to four entries from `investmentTrends`, selected themes, and selected events
- guarantee at least one energy/risk-linked asset view when the theme set clearly points there
- attach explicit watch signals where possible from event or theme metadata

Sparse detection should treat generic phrases such as "geopolitics affects markets" as insufficient.

### Rendering

Notifier output should add two dedicated sections:

- `总主线传导链 | Macro Transmission`
- `关键资产拆解 | Asset Breakdown`

The rendering order should reflect the intended reading path:

1. top-line summary
2. macro transmission chain
3. key events
4. asset breakdowns
5. concise investment strategy
6. risk assessment

Older reports without the new fields must still render cleanly.

## Error Handling

- Missing new fields must not cause report parsing failure.
- Malformed new fields must degrade into empty or normalized structures, not exceptions.
- Sparse strategist output must trigger targeted fallback for the new fields in addition to existing summary/economic/trend fallback.
- Logging should capture whether the new fields were model-produced or fallback-produced.

## Observability

Add report-stage diagnostics for:

- whether `macroTransmissionChain` is present
- how many `assetTransmissionBreakdowns` were produced
- which fields were fallback-filled

This is necessary because the current failure mode is not model-call failure; it is low-information successful output.

## Testing Plan

- normalization tests for missing and malformed transmission fields
- orchestrator tests for fallback generation of both new sections
- notifier/render tests for reports with and without the new fields
- one manual fixture update to show the new sections in a representative report preview

## Success Criteria

- the final report always contains a macro-oriented transmission chain unless there is no reportable event context at all
- the final report contains at least two asset-level transmission breakdowns in normal macro-daily runs
- `economicAnalysis` no longer carries the entire transmission burden by itself
- sparse strategist output no longer collapses the report back to low-dimensional summary prose

## Notes

- This spec documents the approved brainstorming outcome for report-depth expansion.
- Full skill-prescribed spec-review automation is unavailable in this session because no spec-review subagent or `writing-plans` skill is exposed here.
