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

## 4. State machine

States:

`DRAFT -> READY -> RUNNING -> PAUSED -> COMPLETED | ROLLED_BACK`

Prerequisites enforced:

- `DRAFT -> READY`: requires eligible promotion
- `READY -> RUNNING`: requires launch gate artifact
- `* -> ROLLED_BACK`: requires rollback event

All transitions append immutable history entries.

## CLI

Use `scripts/experiment_control.py`:

- `eligibility` to write `eligibility.json`
- `launch-gate` to write `launch_gate.json`
- `rollback-event` to write rollback event artifact
- `transition` to apply state transitions with prerequisite validation
