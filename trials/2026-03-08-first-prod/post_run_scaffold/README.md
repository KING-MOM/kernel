# Post-run Scaffold

This directory is prepared before launch.

- `input/` expected finalized run artifacts
- `output/` target for `scripts/post_run_bundle.py --out-dir`
- target manifest path: `output/post_run_manifest.json`

Expected inputs:
- experiment_state.json
- launch_gate.json
- guardrail_evals.json
- guardrail_aggregate.json
- live_metrics.json
- promotion_eligibility.json
- review_status.json
- manifest.json
- promotion.json
