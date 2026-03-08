# Live Rollout Controls (v1)

This layer bridges offline governance into controlled live execution.

## 1. Promotion eligibility gate

A candidate is rollout-eligible only when both are true:

- offline promotion decision is `PROMOTE`
- review authorization is `APPROVED` with exact `package_hash` match

Machine-readable denial reasons are emitted for all failures.

## 2. Launch gate artifact

Launch is recorded separately from eligibility. `launch_gate.json` binds:

- who launched (`launched_by`) and when
- cohort and experiment arm
- active guardrails at launch
- package hash and SHA-256 hashes of manifest/review/promotion/eligibility artifacts
- policy/parameter/corpus provenance

## 3. Pause vs rollback events

Manual pause and rollback are distinct:

- `PAUSE` is manual stop for investigation
- `ROLLBACK` includes trigger mode (`auto` or `manual`) and breach metadata:
  - threshold source
  - observed metric and threshold
  - breach window and breach timestamp

## 3.1 Guardrail signal ingestion

Guardrail signal artifact requires:

- signal identifiers (`signal_id`, `idempotency_key`, optional `source_event_id`)
- experiment binding (`experiment_id`)
- package binding (`package_hash`)
- optional scope keys (`cohort`, `experiment_arm`, `segment`)
- metric fields (`metric_name`, `metric_window`)
- observed/threshold values
- threshold direction (`upper` or `lower`)
- source and timestamp

Evaluator output decisions:

- `NONE`
- `PAUSE`
- `ROLLBACK_CANDIDATE`

Evaluator emits machine-readable reasons and severity.

Monitor integration rule:

- runtime monitor payloads must normalize into the same canonical `guardrail_signal` schema
- no parallel runtime-only schema is allowed

## 3.2 Multi-signal aggregation policy (v1)

Aggregation unit:

- per `experiment_id` and `package_hash` scope
- optional refinement by `cohort`, `experiment_arm`, `segment`

Deterministic precedence:

1. any unresolved `ROLLBACK_CANDIDATE` => aggregate `ROLLBACK_CANDIDATE`
2. else, if unresolved `PAUSE` count >= threshold (default 3) => escalate to `ROLLBACK_CANDIDATE`
3. else, any unresolved `PAUSE` => aggregate `PAUSE`
4. else => `NONE`

Tie-break metadata:

- latest evaluation timestamp
- breach breadth (`unique metric_name|metric_window` count)

Unresolved semantics (single source of truth):

- decision is actionable (`PAUSE` or `ROLLBACK_CANDIDATE`)
- evaluation is not marked `resolved=true`
- evaluation is not stale (default stale expiry `72h`)

Per-metric escalation:

- optional metric-specific pause thresholds override the default escalation threshold
- fallback uses default threshold when metric override is absent

## 4. State machine

States:

`DRAFT -> READY -> RUNNING -> PAUSED -> COMPLETED | ROLLED_BACK`

Prerequisites enforced:

- `DRAFT -> READY`: requires eligible promotion
- `READY -> RUNNING`: requires launch gate artifact
- `PAUSED -> RUNNING`: requires resume rationale, latest guardrail evaluation timestamp match, and no active rollback breach
- `* -> ROLLED_BACK`: requires rollback event
- `* -> COMPLETED`: requires completion metadata (`runtime_hours`, `sample_size`, `stop_reason`)

All transitions append immutable history entries.

## CLI

Use `scripts/experiment_control.py`:

- `eligibility` to write `eligibility.json`
- `launch-gate` to write `launch_gate.json`
- `rollback-event` to write rollback event artifact
- `guardrail-signal` to write guardrail signal artifact
- `guardrail-eval` to evaluate signal and optionally emit recommended control event
- `guardrail-aggregate` to aggregate multiple evaluations and optionally emit recommended control event
- `monitor-ingest` to normalize monitor payload into canonical signal artifact
- `transition` to apply state transitions with prerequisite validation

Active rollback breach definition:

- latest unresolved, non-stale evaluation per metric/window/package has decision `ROLLBACK_CANDIDATE`
