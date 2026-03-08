#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.kernel.rollout import (
    append_transition_log,
    build_launch_gate,
    build_rollback_event,
    evaluate_promotion_eligibility,
    transition_experiment_state,
)


def _load(path: str) -> dict:
    return json.loads(Path(path).read_text())


def _dump(obj: dict, path: str) -> None:
    Path(path).write_text(json.dumps(obj, indent=2, sort_keys=True, ensure_ascii=True) + "\n")


def main() -> int:
    parser = argparse.ArgumentParser(description="Live rollout controls for Kernel experiments")
    sub = parser.add_subparsers(dest="cmd", required=True)

    elig = sub.add_parser("eligibility", help="Compute promotion eligibility")
    elig.add_argument("--manifest", required=True)
    elig.add_argument("--promotion", required=True)
    elig.add_argument("--review-status", required=True)
    elig.add_argument("--out", required=True)

    launch = sub.add_parser("launch-gate", help="Create launch gate artifact")
    launch.add_argument("--manifest", required=True)
    launch.add_argument("--promotion", required=True)
    launch.add_argument("--review-status", required=True)
    launch.add_argument("--eligibility", required=True)
    launch.add_argument("--launched-by", required=True)
    launch.add_argument("--cohort", required=True)
    launch.add_argument("--arm", required=True)
    launch.add_argument("--guardrails-json", required=True)
    launch.add_argument("--out", required=True)

    trans = sub.add_parser("transition", help="Apply state transition with prerequisites")
    trans.add_argument("--state-file", required=True)
    trans.add_argument("--to", required=True)
    trans.add_argument("--actor-id", required=True)
    trans.add_argument("--reason", required=True)
    trans.add_argument("--eligibility")
    trans.add_argument("--launch-gate")
    trans.add_argument("--rollback-event-json")

    rollback = sub.add_parser("rollback-event", help="Create rollback event artifact")
    rollback.add_argument("--trigger-mode", required=True, choices=["auto", "manual"])
    rollback.add_argument("--actor-id", required=True)
    rollback.add_argument("--reason", required=True)
    rollback.add_argument("--threshold-source", required=True)
    rollback.add_argument("--metric-name", required=True)
    rollback.add_argument("--observed-value", required=True, type=float)
    rollback.add_argument("--threshold-value", required=True, type=float)
    rollback.add_argument("--breach-window", required=True)
    rollback.add_argument("--out", required=True)

    args = parser.parse_args()

    if args.cmd == "eligibility":
        result = evaluate_promotion_eligibility(
            manifest=_load(args.manifest),
            promotion=_load(args.promotion),
            review_status=_load(args.review_status),
        )
        _dump(result, args.out)
        print(json.dumps({"status": "ok", "eligible": result["eligible"], "out": args.out}, sort_keys=True))
        return 0

    if args.cmd == "launch-gate":
        guardrails = _load(args.guardrails_json)
        artifact = build_launch_gate(
            manifest_path=Path(args.manifest),
            promotion_path=Path(args.promotion),
            review_status_path=Path(args.review_status),
            eligibility_path=Path(args.eligibility),
            launched_by=args.launched_by,
            cohort=args.cohort,
            experiment_arm=args.arm,
            guardrails=guardrails,
        )
        _dump(artifact, args.out)
        print(json.dumps({"status": "ok", "out": args.out}, sort_keys=True))
        return 0

    if args.cmd == "rollback-event":
        event = build_rollback_event(
            trigger_mode=args.trigger_mode,
            actor_id=args.actor_id,
            reason=args.reason,
            threshold_source=args.threshold_source,
            metric_name=args.metric_name,
            observed_value=args.observed_value,
            threshold_value=args.threshold_value,
            breach_window=args.breach_window,
        )
        _dump(event, args.out)
        print(json.dumps({"status": "ok", "out": args.out}, sort_keys=True))
        return 0

    # transition
    state_path = Path(args.state_file)
    state_doc = _load(args.state_file) if state_path.exists() else {"state": "DRAFT", "history": []}
    eligibility = _load(args.eligibility) if args.eligibility else None
    launch_gate = _load(args.launch_gate) if args.launch_gate else None
    rollback_event = _load(args.rollback_event_json) if args.rollback_event_json else None

    next_doc = transition_experiment_state(
        state_doc=state_doc,
        next_state=args.to,
        actor_id=args.actor_id,
        reason=args.reason,
        eligibility=eligibility,
        launch_gate=launch_gate,
        rollback_event=rollback_event,
    )
    append_transition_log(state_path=state_path, state_doc=next_doc)
    print(json.dumps({"status": "ok", "state": next_doc["state"], "state_file": args.state_file}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
