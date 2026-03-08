#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.kernel.live_ops import build_live_ops_report, render_live_ops_markdown
from app.kernel.post_run import write_post_run_bundle


def _load(path: str):
    return json.loads(Path(path).read_text())


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate post-run bundle from live run artifacts")
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--state-file", required=True)
    parser.add_argument("--launch-gate", required=True)
    parser.add_argument("--guardrail-evals", required=True)
    parser.add_argument("--aggregate")
    parser.add_argument("--live-metrics")
    parser.add_argument("--eligibility")
    parser.add_argument("--review-status")
    parser.add_argument("--manifest")
    parser.add_argument("--promotion")
    parser.add_argument("--stale-after-hours", type=float, default=72.0)
    args = parser.parse_args()

    state_doc = _load(args.state_file)
    launch_gate = _load(args.launch_gate)
    guardrail_evals = _load(args.guardrail_evals)
    if not isinstance(guardrail_evals, list):
        raise ValueError("guardrail-evals must be a JSON list")
    aggregate = _load(args.aggregate) if args.aggregate else None
    live_metrics = _load(args.live_metrics) if args.live_metrics else None

    report_json = build_live_ops_report(
        state_doc=state_doc,
        launch_gate=launch_gate,
        guardrail_evaluations=guardrail_evals,
        aggregate_result=aggregate,
        live_metrics=live_metrics,
        stale_after_hours=args.stale_after_hours,
    )
    report_md = render_live_ops_markdown(report_json)

    artifacts = {
        "state_file": Path(args.state_file),
        "launch_gate": Path(args.launch_gate),
        "guardrail_evals": Path(args.guardrail_evals),
        "aggregate": Path(args.aggregate) if args.aggregate else None,
        "live_metrics": Path(args.live_metrics) if args.live_metrics else None,
        "eligibility": Path(args.eligibility) if args.eligibility else None,
        "review_status": Path(args.review_status) if args.review_status else None,
        "manifest": Path(args.manifest) if args.manifest else None,
        "promotion": Path(args.promotion) if args.promotion else None,
    }

    manifest = write_post_run_bundle(
        out_dir=Path(args.out_dir),
        report_json=report_json,
        report_markdown=report_md,
        artifact_paths=artifacts,
    )
    print(json.dumps({"status": "ok", "manifest_path": manifest["manifest_path"], "package_hash": manifest["package_hash"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
