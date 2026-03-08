#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.kernel.live_ops import build_live_ops_report, render_live_ops_markdown


def _load(path: str):
    return json.loads(Path(path).read_text())


def _dump(path: str, obj):
    Path(path).write_text(json.dumps(obj, indent=2, sort_keys=True, ensure_ascii=True) + "\n")


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate live ops report from runtime artifacts")
    parser.add_argument("--state-file", required=True)
    parser.add_argument("--launch-gate", required=True)
    parser.add_argument("--guardrail-evals", required=True, help="JSON list path")
    parser.add_argument("--aggregate")
    parser.add_argument("--live-metrics")
    parser.add_argument("--stale-after-hours", type=float, default=72.0)
    parser.add_argument("--out-json")
    parser.add_argument("--out-md")
    args = parser.parse_args()

    state_doc = _load(args.state_file)
    launch_gate = _load(args.launch_gate)
    guardrail_evals = _load(args.guardrail_evals)
    if not isinstance(guardrail_evals, list):
        raise ValueError("guardrail-evals must be a JSON list")

    aggregate = _load(args.aggregate) if args.aggregate else None
    live_metrics = _load(args.live_metrics) if args.live_metrics else None

    report = build_live_ops_report(
        state_doc=state_doc,
        launch_gate=launch_gate,
        guardrail_evaluations=guardrail_evals,
        aggregate_result=aggregate,
        live_metrics=live_metrics,
        stale_after_hours=args.stale_after_hours,
    )
    markdown = render_live_ops_markdown(report)

    if args.out_json:
        _dump(args.out_json, report)
    if args.out_md:
        Path(args.out_md).write_text(markdown)

    if not args.out_json and not args.out_md:
        print(markdown)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
