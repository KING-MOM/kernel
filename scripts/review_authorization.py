#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.kernel.authorization import check_promotion_authorization, load_json, write_review_status


def main() -> int:
    parser = argparse.ArgumentParser(description="Review authorization workflow for promotion decisions.")
    sub = parser.add_subparsers(dest="cmd", required=True)

    decide = sub.add_parser("decide", help="Create or update a review_status artifact")
    decide.add_argument("--manifest", required=True, help="Path to manifest.json")
    decide.add_argument("--out", required=True, help="Path to review_status.json")
    decide.add_argument("--status", required=True, choices=["PENDING", "APPROVED", "REJECTED", "SUPERSEDED"])
    decide.add_argument("--reviewer-id", required=True, help="Reviewer identity")
    decide.add_argument("--rationale", default="", help="Required for APPROVED/REJECTED/SUPERSEDED")

    check = sub.add_parser("check", help="Validate if promotion is authorized")
    check.add_argument("--manifest", required=True, help="Path to manifest.json")
    check.add_argument("--review-status", required=True, help="Path to review_status.json")

    args = parser.parse_args()

    if args.cmd == "decide":
        review = write_review_status(
            manifest_path=Path(args.manifest),
            out_path=Path(args.out),
            status=args.status,
            reviewer_id=args.reviewer_id,
            rationale=args.rationale,
        )
        print(json.dumps({"status": "ok", "review_status_path": str(Path(args.out)), "review": review}, sort_keys=True))
        return 0

    manifest = load_json(Path(args.manifest))
    review_status = load_json(Path(args.review_status))
    result = check_promotion_authorization(manifest=manifest, review_status=review_status)
    print(json.dumps(result, sort_keys=True))
    return 0 if result.get("authorized") else 2


if __name__ == "__main__":
    raise SystemExit(main())
