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
    parser.add_argument("--out", help="Optional output markdown path")
    args = parser.parse_args()

    comparison = json.loads(Path(args.comparison).read_text())
    promotion = json.loads(Path(args.promotion).read_text())
    segmented_comparison = json.loads(Path(args.segmented_comparison).read_text()) if args.segmented_comparison else None
    segmented_promotion = json.loads(Path(args.segmented_promotion).read_text()) if args.segmented_promotion else None

    report = build_governance_report(
        comparison=comparison,
        promotion=promotion,
        segmented_comparison=segmented_comparison,
        segmented_promotion=segmented_promotion,
    )
    md = render_markdown_report(report)

    if args.out:
        Path(args.out).write_text(md)
    else:
        print(md)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
