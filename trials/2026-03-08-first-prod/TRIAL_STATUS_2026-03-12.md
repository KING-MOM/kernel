# Trial Status Snapshot: 2026-03-12

## Scope

- Trial: `2026-03-08-first-prod`
- Cohort: `10pct`
- Arm: `candidate`
- State: `RUNNING`
- Package hash: `trial-pkg-2026-03-08-a`
- Policy/Params: `v1.2` / `pset-1`

## Current Control Status

- Aggregate control recommendation: `NONE`
- Aggregate severity: `none`
- Unresolved breaches: `0`
- Guardrail note: no unresolved non-stale evaluations in scope

## Canonical Beta Set

Kernel is currently tracking 4 canonical beta contacts. Mexico WhatsApp aliases are treated as one identity in this snapshot.

1. `whatsapp:+5215520453254`
   - Stage: `value_delivered`
   - Intent debt: `0`
   - Tension: `0.4`
   - Last touch: `2026-03-10T15:43:30.500000+00:00`

2. `whatsapp:+5215530063065`
   - Stage: `engaged`
   - Intent debt: `1`
   - Tension: `0.0`
   - Last touch: `2026-03-09T20:51:35.165000+00:00`

3. `whatsapp:+5215554540593`
   - Aliases: `whatsapp:+5215554540593`, `whatsapp:+525554540593`
   - Stage: `value_delivered`
   - Intent debt: `0`
   - Tension: `0.4`
   - Last touch: `2026-03-11T15:00:04.200000+00:00`

4. `whatsapp:+5215560663926`
   - Stage: `value_delivered`
   - Intent debt: `0`
   - Tension: `1.0`
   - Last touch: `2026-03-10T00:02:45.017000+00:00`

## Live Metrics

| Window | Reply Rate | Progression Rate | Negative Signal Rate | Unresolved Reply Debt Rate | Median Response Latency (h) |
| --- | ---: | ---: | ---: | ---: | ---: |
| `24h` | `0.0` | `0.0` | `0.0` | `0.25` | `None` |
| `72h` | `0.1176` | `0.1176` | `0.0` | `0.25` | `0.0181` |
| `7d` | `0.1429` | `0.1429` | `0.0` | `0.25` | `0.024` |

## Interpretation

- The run is still healthy from a control perspective: no active guardrail breach, no pause, no rollback candidate.
- One of four canonical contacts currently has unresolved reply debt.
- The trial artifact set has been refreshed from live SQLite state, not only from the original launch scaffold.

## Caveat

`progression_rate` is currently using `reply_rate` as a live proxy. Online semantic progression labeling is not wired yet, so this metric is operationally useful for the trial but not final.

## Tuning Guidance

Do not tune during this trial. First collect real interaction data, then review the post-run bundle, then tune narrowly.

Tune first later:

- `cadence_days`
- `min_cooldown_hours`
- `max_tension`

Do not tune yet:

- trust/tension formulas
- per-contact personalization
- complex reward weights

## Source Artifacts

- [experiment_state.json](/Users/mau/Documents/New project/kernel/trials/2026-03-08-first-prod/artifacts/experiment_state.json)
- [launch_gate.json](/Users/mau/Documents/New project/kernel/trials/2026-03-08-first-prod/artifacts/launch_gate.json)
- [guardrail_aggregate.json](/Users/mau/Documents/New project/kernel/trials/2026-03-08-first-prod/artifacts/guardrail_aggregate.json)
- [guardrail_evals.json](/Users/mau/Documents/New project/kernel/trials/2026-03-08-first-prod/artifacts/guardrail_evals.json)
- [live_ops_report.json](/Users/mau/Documents/New project/kernel/trials/2026-03-08-first-prod/artifacts/live_ops_report.json)
- [live_ops_report.md](/Users/mau/Documents/New project/kernel/trials/2026-03-08-first-prod/artifacts/live_ops_report.md)
- [runtime_snapshot_summary.json](/Users/mau/Documents/New project/kernel/trials/2026-03-08-first-prod/artifacts/runtime_snapshot_summary.json)
- [live_metrics.json](/Users/mau/Documents/New project/kernel/trials/2026-03-08-first-prod/inputs/live_metrics.json)
