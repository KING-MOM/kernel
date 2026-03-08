# Ops Runbook v1

This runbook is for operators running live Kernel experiments.

## Operator dashboard/report surface

Generate report from live artifacts:

```bash
python3 scripts/live_ops_report.py \
  --state-file /path/experiment_state.json \
  --launch-gate /path/launch_gate.json \
  --guardrail-evals /path/guardrail_evals.json \
  --aggregate /path/guardrail_aggregate.json \
  --live-metrics /path/live_metrics.json \
  --out-json /path/live_ops_report.json \
  --out-md /path/live_ops_report.md
```

## What operators should review

- experiment state
- launch provenance
- active guardrail signals
- aggregate control recommendation
- unresolved breaches
- pause/rollback history
- core live metrics by window and scope

## Standard operating cadence

- On launch day: review every 30 minutes for first 4 hours.
- During stable runtime: review every 2-4 hours.
- On any `ROLLBACK_CANDIDATE`: immediate review and decision.

## Pause procedure

- Trigger `PAUSED` when aggregate recommends `PAUSE` and operator confirms risk.
- Record clear rationale in transition reason.
- Do not resume without fresh guardrail evaluation and timestamp bind.

## Rollback procedure

- Trigger `ROLLED_BACK` for unresolved severe breaches (`ROLLBACK_CANDIDATE`) per policy.
- Record threshold source, metric, observed/threshold values, and breach window.

## Completion procedure

- Transition to `COMPLETED` only with:
  - runtime_hours
  - sample_size
  - stop_reason

