# Offline Promotion Rule (v1)

This rule governs whether a candidate policy/parameter set is allowed to move from offline replay evaluation to live A/B.

## Inputs

Use output from `compare_scorecards(...)` / `compare_records(...)`.

## Hard Guardrails

Candidate is rejected if any required window fails:

- `compliance_incidents.delta > 0`
- `negative_signal_rate.delta > max_negative_signal_rate_delta`
- `evaluated_decisions.candidate < min_evaluated_decisions`

## Improvement Requirement

Candidate must show at least one material improvement in required windows:

- `progression_rate.delta >= min_progression_rate_delta`
- OR `median_response_latency_hours.delta <= -min_latency_improvement_hours`

(negative latency delta means faster response.)

## Tie Rule

If guardrails pass but there is no material improvement, default to baseline (`HOLD_BASELINE`).

## Default v1 Thresholds

- `required_windows`: `24h`, `72h`, `7d`
- `min_evaluated_decisions`: `30`
- `max_negative_signal_rate_delta`: `0.0`
- `min_progression_rate_delta`: `0.02`
- `min_latency_improvement_hours`: `1.0`

## Decisions

- `PROMOTE`: guardrails pass and improvement requirement passes
- `REJECT`: one or more guardrails fail
- `HOLD_BASELINE`: guardrails pass, but no material improvement
