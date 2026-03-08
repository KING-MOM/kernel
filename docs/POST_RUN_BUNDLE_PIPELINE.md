# Post-Run Bundle Pipeline

Generate one stable post-run package after experiment end.

## Command

```bash
python3 scripts/post_run_bundle.py \
  --out-dir /path/post-run-bundle \
  --state-file /path/experiment_state.json \
  --launch-gate /path/launch_gate.json \
  --guardrail-evals /path/guardrail_evals.json \
  --aggregate /path/guardrail_aggregate.json \
  --live-metrics /path/live_metrics.json \
  --eligibility /path/eligibility.json \
  --review-status /path/review_status.json \
  --manifest /path/manifest.json \
  --promotion /path/promotion.json
```

## Output

- copied run artifacts
- `live_ops_report.json`
- `live_ops_report.md`
- `post_run_manifest.json` with per-file hashes and package hash

Use `post_run_manifest.json` as the handoff pointer for review.
