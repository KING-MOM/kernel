# First Controlled Production Run Template

This template is for the first live experiment run.

## Prerequisites checklist

- promotion package exists and integrity verified
- review authorization is `APPROVED` and hash matches
- promotion eligibility artifact says `eligible=true`
- rollout state initialized in `DRAFT`
- launch guardrails JSON prepared

## Commands (explicit sequence)

1. Compute eligibility

```bash
python3 scripts/experiment_control.py eligibility \
  --manifest /path/manifest.json \
  --promotion /path/promotion.json \
  --review-status /path/review_status.json \
  --out /path/eligibility.json
```

2. Transition `DRAFT -> READY`

```bash
python3 scripts/experiment_control.py transition \
  --state-file /path/experiment_state.json \
  --to READY \
  --actor-id ops@team \
  --reason "Promotion eligible and approved" \
  --eligibility /path/eligibility.json
```

3. Create launch gate

```bash
python3 scripts/experiment_control.py launch-gate \
  --manifest /path/manifest.json \
  --promotion /path/promotion.json \
  --review-status /path/review_status.json \
  --eligibility /path/eligibility.json \
  --launched-by ops@team \
  --cohort 10pct \
  --arm candidate \
  --guardrails-json /path/guardrails.json \
  --out /path/launch_gate.json
```

4. Transition `READY -> RUNNING`

```bash
python3 scripts/experiment_control.py transition \
  --state-file /path/experiment_state.json \
  --to RUNNING \
  --actor-id ops@team \
  --reason "Launch gate created" \
  --launch-gate /path/launch_gate.json
```

## Live review cadence

- First 4 hours: every 30 minutes.
- After 4 hours: every 2-4 hours.
- Immediate review on aggregate `ROLLBACK_CANDIDATE`.

## Pause/rollback decision policy

- Pause if aggregate decision is `PAUSE` and unresolved breaches remain.
- Rollback when aggregate decision is `ROLLBACK_CANDIDATE` and breach is not resolved quickly per policy.

## Completion criteria

- Planned runtime reached.
- Minimum sample size reached.
- No unresolved severe breaches at close.

## Completion command

```bash
python3 scripts/experiment_control.py transition \
  --state-file /path/experiment_state.json \
  --to COMPLETED \
  --actor-id ops@team \
  --reason "Planned run complete" \
  --completion-meta-json /path/completion_meta.json
```

## Post-run handoff

- Generate post-run bundle.
- Share bundle manifest + report with reviewers.

