#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.kernel.rollout import (
    aggregate_guardrail_evaluations,
    append_transition_log,
    build_guardrail_signal,
    build_launch_gate,
    build_rollback_event,
    evaluate_promotion_eligibility,
    evaluate_guardrail_signal,
    has_active_rollback_breach,
    ingest_monitor_payload,
    recommended_control_event_from_aggregate,
    recommended_control_event_from_guardrail,
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
    trans.add_argument("--resume-rationale")
    trans.add_argument("--latest-guardrail-eval")
    trans.add_argument("--resume-guardrail-eval-ts")
    trans.add_argument("--guardrail-evals-json", help="Optional JSON list path for active breach detection")
    trans.add_argument("--completion-meta-json")

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

    signal = sub.add_parser("guardrail-signal", help="Create guardrail signal artifact")
    signal.add_argument("--experiment-id", required=True)
    signal.add_argument("--package-hash", required=True)
    signal.add_argument("--metric-name", required=True)
    signal.add_argument("--metric-window", required=True)
    signal.add_argument("--observed-value", required=True, type=float)
    signal.add_argument("--threshold-value", required=True, type=float)
    signal.add_argument("--threshold-direction", required=True, choices=["upper", "lower"])
    signal.add_argument("--source", required=True)
    signal.add_argument("--source-event-id")
    signal.add_argument("--idempotency-key")
    signal.add_argument("--cohort")
    signal.add_argument("--experiment-arm")
    signal.add_argument("--segment")
    signal.add_argument("--out", required=True)

    geval = sub.add_parser("guardrail-eval", help="Evaluate guardrail signal and emit recommendation")
    geval.add_argument("--signal", required=True)
    geval.add_argument("--out", required=True)
    geval.add_argument("--actor-id", default="guardrail-monitor")
    geval.add_argument("--control-event-out", help="Optional output path for recommended control event JSON")

    gagg = sub.add_parser("guardrail-aggregate", help="Aggregate multiple guardrail evaluations")
    gagg.add_argument("--evaluations-json", required=True, help="Path to JSON list of guardrail evaluations")
    gagg.add_argument("--experiment-id")
    gagg.add_argument("--package-hash")
    gagg.add_argument("--cohort")
    gagg.add_argument("--experiment-arm")
    gagg.add_argument("--segment")
    gagg.add_argument("--stale-after-hours", type=float, default=72.0)
    gagg.add_argument("--pause-escalation-threshold", type=int, default=3)
    gagg.add_argument("--pause-thresholds-by-metric-json", help="Optional JSON dict metric->threshold")
    gagg.add_argument("--out", required=True)
    gagg.add_argument("--actor-id", default="guardrail-aggregator")
    gagg.add_argument("--control-event-out")

    ming = sub.add_parser("monitor-ingest", help="Normalize monitor payload into guardrail signal artifact")
    ming.add_argument("--payload-json", required=True)
    ming.add_argument("--out", required=True)

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

    if args.cmd == "guardrail-signal":
        artifact = build_guardrail_signal(
            experiment_id=args.experiment_id,
            package_hash=args.package_hash,
            metric_name=args.metric_name,
            metric_window=args.metric_window,
            observed_value=args.observed_value,
            threshold_value=args.threshold_value,
            threshold_direction=args.threshold_direction,
            source=args.source,
            source_event_id=args.source_event_id,
            idempotency_key=args.idempotency_key,
            cohort=args.cohort,
            experiment_arm=args.experiment_arm,
            segment=args.segment,
        )
        _dump(artifact, args.out)
        print(json.dumps({"status": "ok", "out": args.out, "signal_id": artifact["signal_id"]}, sort_keys=True))
        return 0

    if args.cmd == "guardrail-eval":
        signal_obj = _load(args.signal)
        evaluation = evaluate_guardrail_signal(signal_obj)
        _dump(evaluation, args.out)
        control_event = recommended_control_event_from_guardrail(evaluation=evaluation, actor_id=args.actor_id)
        if args.control_event_out and control_event is not None:
            _dump(control_event, args.control_event_out)
        print(
            json.dumps(
                {
                    "status": "ok",
                    "out": args.out,
                    "decision": evaluation["decision"],
                    "control_event_emitted": bool(args.control_event_out and control_event is not None),
                },
                sort_keys=True,
            )
        )
        return 0

    if args.cmd == "guardrail-aggregate":
        evaluations = _load(args.evaluations_json)
        if not isinstance(evaluations, list):
            raise ValueError("evaluations_json must be a JSON list")
        aggregate = aggregate_guardrail_evaluations(
            evaluations,
            experiment_id=args.experiment_id,
            package_hash=args.package_hash,
            cohort=args.cohort,
            experiment_arm=args.experiment_arm,
            segment=args.segment,
            pause_escalation_threshold=args.pause_escalation_threshold,
            pause_escalation_threshold_by_metric=_load(args.pause_thresholds_by_metric_json)
            if args.pause_thresholds_by_metric_json
            else None,
            stale_after_hours=args.stale_after_hours,
        )
        _dump(aggregate, args.out)
        control_event = recommended_control_event_from_aggregate(
            aggregate_result=aggregate,
            actor_id=args.actor_id,
        )
        if args.control_event_out and control_event is not None:
            _dump(control_event, args.control_event_out)
        print(
            json.dumps(
                {
                    "status": "ok",
                    "out": args.out,
                    "decision": aggregate["decision"],
                    "control_event_emitted": bool(args.control_event_out and control_event is not None),
                },
                sort_keys=True,
            )
        )
        return 0

    if args.cmd == "monitor-ingest":
        payload = _load(args.payload_json)
        signal = ingest_monitor_payload(payload)
        _dump(signal, args.out)
        print(json.dumps({"status": "ok", "out": args.out, "signal_id": signal["signal_id"]}, sort_keys=True))
        return 0

    # transition
    state_path = Path(args.state_file)
    state_doc = _load(args.state_file) if state_path.exists() else {"state": "DRAFT", "history": []}
    eligibility = _load(args.eligibility) if args.eligibility else None
    launch_gate = _load(args.launch_gate) if args.launch_gate else None
    rollback_event = _load(args.rollback_event_json) if args.rollback_event_json else None
    latest_guardrail_eval = _load(args.latest_guardrail_eval) if args.latest_guardrail_eval else None
    completion_meta = _load(args.completion_meta_json) if args.completion_meta_json else None
    active_rollback_breach = None
    if args.guardrail_evals_json:
        guardrail_evals = _load(args.guardrail_evals_json)
        if not isinstance(guardrail_evals, list):
            raise ValueError("guardrail_evals_json must be a JSON list")
        active_rollback_breach = has_active_rollback_breach(guardrail_evals, stale_after_hours=72.0)

    next_doc = transition_experiment_state(
        state_doc=state_doc,
        next_state=args.to,
        actor_id=args.actor_id,
        reason=args.reason,
        eligibility=eligibility,
        launch_gate=launch_gate,
        rollback_event=rollback_event,
        resume_rationale=args.resume_rationale,
        latest_guardrail_eval=latest_guardrail_eval,
        resume_guardrail_eval_ts=args.resume_guardrail_eval_ts,
        active_rollback_breach=active_rollback_breach,
        completion_meta=completion_meta,
    )
    append_transition_log(state_path=state_path, state_doc=next_doc)
    print(json.dumps({"status": "ok", "state": next_doc["state"], "state_file": args.state_file}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
