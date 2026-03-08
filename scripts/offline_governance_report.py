#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.kernel.reporting import build_governance_report, render_markdown_report


def main() -> int:
    parser = argparse.ArgumentParser(description="Render offline governance report from JSON artifacts.")
    parser.add_argument("--comparison", required=True, help="Path to global comparison JSON")
    parser.add_argument("--promotion", required=True, help="Path to global promotion JSON")
    parser.add_argument("--segmented-comparison", help="Path to segmented comparison JSON")
    parser.add_argument("--segmented-promotion", help="Path to segmented promotion JSON")
    parser.add_argument("--corpus-id", help="Corpus identifier for provenance")
    parser.add_argument("--policy-version", help="Policy version for provenance")
    parser.add_argument("--parameter-set-version", help="Parameter set version for provenance")
    parser.add_argument("--provenance-json", help="Optional path to provenance JSON to merge")
    parser.add_argument("--out", help="Optional output markdown path")
    args = parser.parse_args()

    comparison = json.loads(Path(args.comparison).read_text())
    promotion = json.loads(Path(args.promotion).read_text())
    segmented_comparison = json.loads(Path(args.segmented_comparison).read_text()) if args.segmented_comparison else None
    segmented_promotion = json.loads(Path(args.segmented_promotion).read_text()) if args.segmented_promotion else None
    provenance = json.loads(Path(args.provenance_json).read_text()) if args.provenance_json else {}
    provenance.update(
        {
            "corpus_id": args.corpus_id,
            "policy_version": args.policy_version,
            "parameter_set_version": args.parameter_set_version,
            "baseline_total_decisions": comparison.get("summary", {}).get("baseline_total_decisions"),
            "candidate_total_decisions": comparison.get("summary", {}).get("candidate_total_decisions"),
        }
    )
    # Drop empty values from direct CLI args
    provenance = {k: v for k, v in provenance.items() if v is not None}

    report = build_governance_report(
        comparison=comparison,
        promotion=promotion,
        segmented_comparison=segmented_comparison,
        segmented_promotion=segmented_promotion,
        provenance=provenance,
    )
    md = render_markdown_report(report)

    if args.out:
        Path(args.out).write_text(md)
    else:
        print(md)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
