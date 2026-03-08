from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.kernel.authorization import check_promotion_authorization


ROLLOUT_SCHEMA_VERSION = "1.0"
ALLOWED_STATES = {"DRAFT", "READY", "RUNNING", "PAUSED", "COMPLETED", "ROLLED_BACK"}
ALLOWED_THRESHOLD_DIRECTIONS = {"upper", "lower"}
ALLOWED_GUARDRAIL_DECISIONS = {"NONE", "PAUSE", "ROLLBACK_CANDIDATE"}


def _json_dump(obj: Dict[str, Any], path: Path) -> None:
    path.write_text(json.dumps(obj, indent=2, sort_keys=True, ensure_ascii=True) + "\n")


def _load_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text())


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build_guardrail_signal(
    *,
    experiment_id: str,
    package_hash: str,
    metric_name: str,
    metric_window: str,
    observed_value: float,
    threshold_value: float,
    threshold_direction: str,  # upper|lower
    source: str,
    ts_utc: Optional[str] = None,
    signal_id: Optional[str] = None,
    source_event_id: Optional[str] = None,
    idempotency_key: Optional[str] = None,
) -> Dict[str, Any]:
    direction = threshold_direction.lower().strip()
    if direction not in ALLOWED_THRESHOLD_DIRECTIONS:
        raise ValueError("threshold_direction must be upper or lower")
    if not experiment_id.strip():
        raise ValueError("experiment_id is required")
    if not package_hash.strip():
        raise ValueError("package_hash is required")
    if not metric_name.strip():
        raise ValueError("metric_name is required")
    if not metric_window.strip():
        raise ValueError("metric_window is required")
    if not source.strip():
        raise ValueError("source is required")
    ts = ts_utc or datetime.now(timezone.utc).isoformat()
    sid = signal_id or str(uuid.uuid4())
    idem = idempotency_key or source_event_id or sid
    return {
        "rollout_schema_version": ROLLOUT_SCHEMA_VERSION,
        "signal_id": sid,
        "source_event_id": source_event_id,
        "idempotency_key": idem,
        "experiment_id": experiment_id,
        "package_hash": package_hash,
        "metric_name": metric_name,
        "metric_window": metric_window,
        "observed_value": observed_value,
        "threshold_value": threshold_value,
        "threshold_direction": direction,
        "source": source,
        "ts_utc": ts,
    }


def validate_guardrail_signal(signal: Dict[str, Any]) -> Dict[str, Any]:
    reasons: List[str] = []
    for field in (
        "signal_id",
        "idempotency_key",
        "experiment_id",
        "package_hash",
        "metric_name",
        "metric_window",
        "threshold_direction",
        "source",
        "ts_utc",
    ):
        if not signal.get(field):
            reasons.append(f"missing:{field}")

    direction = str(signal.get("threshold_direction", "")).lower().strip()
    if direction not in ALLOWED_THRESHOLD_DIRECTIONS:
        reasons.append("invalid:threshold_direction")

    for numeric in ("observed_value", "threshold_value"):
        value = signal.get(numeric)
        if not isinstance(value, (int, float)):
            reasons.append(f"invalid:{numeric}")

    return {"valid": len(reasons) == 0, "reasons": reasons}


def _is_threshold_breached(*, observed_value: float, threshold_value: float, threshold_direction: str) -> bool:
    if threshold_direction == "upper":
        return observed_value > threshold_value
    return observed_value < threshold_value


def evaluate_guardrail_signal(signal: Dict[str, Any]) -> Dict[str, Any]:
    validation = validate_guardrail_signal(signal)
    if not validation["valid"]:
        return {
            "rollout_schema_version": ROLLOUT_SCHEMA_VERSION,
            "decision": "PAUSE",
            "severity": "hard",
            "valid_signal": False,
            "reasons": [f"signal_invalid:{r}" for r in validation["reasons"]],
            "signal": signal,
            "breach": None,
            "evaluated_at_utc": datetime.now(timezone.utc).isoformat(),
        }

    observed = float(signal["observed_value"])
    threshold = float(signal["threshold_value"])
    direction = str(signal["threshold_direction"]).lower().strip()
    breached = _is_threshold_breached(
        observed_value=observed,
        threshold_value=threshold,
        threshold_direction=direction,
    )

    if not breached:
        decision = "NONE"
        severity = "none"
        reasons = ["threshold_not_breached"]
    else:
        metric = str(signal["metric_name"]).lower()
        is_hard_metric = metric in {"compliance_incidents", "negative_signal_rate"}
        if is_hard_metric:
            decision = "ROLLBACK_CANDIDATE"
            severity = "hard"
            reasons = ["hard_guardrail_breach", f"metric:{metric}"]
        else:
            decision = "PAUSE"
            severity = "soft"
            reasons = ["guardrail_breach_pause_recommended", f"metric:{metric}"]

    return {
        "rollout_schema_version": ROLLOUT_SCHEMA_VERSION,
        "decision": decision,
        "severity": severity,
        "valid_signal": True,
        "reasons": reasons,
        "signal": signal,
        "breach": {
            "active": breached and decision in {"PAUSE", "ROLLBACK_CANDIDATE"},
            "observed_value": observed,
            "threshold_value": threshold,
            "threshold_direction": direction,
        },
        "evaluated_at_utc": datetime.now(timezone.utc).isoformat(),
    }


def has_active_rollback_breach(evaluations: List[Dict[str, Any]]) -> bool:
    """Active rollback breach = latest non-resolved ROLLBACK_CANDIDATE for any metric/window."""
    latest_by_key: Dict[str, Dict[str, Any]] = {}
    for ev in evaluations:
        signal = ev.get("signal", {})
        key = f"{signal.get('metric_name')}|{signal.get('metric_window')}|{signal.get('package_hash')}"
        prev = latest_by_key.get(key)
        if prev is None or str(ev.get("evaluated_at_utc", "")) > str(prev.get("evaluated_at_utc", "")):
            latest_by_key[key] = ev

    for ev in latest_by_key.values():
        if str(ev.get("decision", "")).upper() == "ROLLBACK_CANDIDATE":
            if not bool(ev.get("resolved", False)):
                return True
    return False


def recommended_control_event_from_guardrail(
    *,
    evaluation: Dict[str, Any],
    actor_id: str = "guardrail-monitor",
) -> Optional[Dict[str, Any]]:
    decision = str(evaluation.get("decision", "")).upper().strip()
    signal = evaluation.get("signal", {})
    if decision == "PAUSE":
        return build_pause_event(
            actor_id=actor_id,
            reason=f"guardrail pause: {','.join(evaluation.get('reasons', []))}",
        )
    if decision == "ROLLBACK_CANDIDATE":
        return build_rollback_event(
            trigger_mode="auto",
            actor_id=actor_id,
            reason=f"guardrail rollback candidate: {','.join(evaluation.get('reasons', []))}",
            threshold_source=str(signal.get("source", "unknown")),
            metric_name=str(signal.get("metric_name", "unknown")),
            observed_value=float(signal.get("observed_value", 0.0)),
            threshold_value=float(signal.get("threshold_value", 0.0)),
            breach_window=str(signal.get("metric_window", "unknown")),
        )
    return None


def aggregate_guardrail_evaluations(
    evaluations: List[Dict[str, Any]],
    *,
    experiment_id: Optional[str] = None,
    package_hash: Optional[str] = None,
    pause_escalation_threshold: int = 3,
) -> Dict[str, Any]:
    filtered: List[Dict[str, Any]] = []
    for ev in evaluations:
        signal = ev.get("signal", {})
        if experiment_id and signal.get("experiment_id") != experiment_id:
            continue
        if package_hash and signal.get("package_hash") != package_hash:
            continue
        filtered.append(ev)

    if not filtered:
        return {
            "rollout_schema_version": ROLLOUT_SCHEMA_VERSION,
            "decision": "NONE",
            "severity": "none",
            "reasons": ["no_evaluations_in_scope"],
            "counts": {"rollback_candidate": 0, "pause": 0, "none": 0},
            "breadth": {"unique_metric_windows": 0},
        }

    unresolved = [ev for ev in filtered if not bool(ev.get("resolved", False))]
    rollback_candidates = [ev for ev in unresolved if str(ev.get("decision", "")).upper() == "ROLLBACK_CANDIDATE"]
    pauses = [ev for ev in unresolved if str(ev.get("decision", "")).upper() == "PAUSE"]
    nones = [ev for ev in unresolved if str(ev.get("decision", "")).upper() == "NONE"]

    unique_metric_windows = {
        f"{ev.get('signal', {}).get('metric_name')}|{ev.get('signal', {}).get('metric_window')}" for ev in unresolved
    }
    latest_eval = max(unresolved, key=lambda x: str(x.get("evaluated_at_utc", "")))

    reasons: List[str] = []
    decision = "NONE"
    severity = "none"

    if rollback_candidates:
        decision = "ROLLBACK_CANDIDATE"
        severity = "hard"
        reasons.append("rollback_candidate_present")
    elif len(pauses) >= pause_escalation_threshold:
        # Escalation rule: repeated medium breaches aggregate into rollback candidate.
        decision = "ROLLBACK_CANDIDATE"
        severity = "hard"
        reasons.append("pause_escalated_to_rollback_candidate")
        reasons.append(f"pause_count:{len(pauses)}")
    elif pauses:
        decision = "PAUSE"
        severity = "soft"
        reasons.append("pause_present")
    else:
        reasons.append("no_actionable_breach")

    reasons.append(f"latest_eval_ts:{latest_eval.get('evaluated_at_utc')}")
    reasons.append(f"breadth_metric_windows:{len(unique_metric_windows)}")
    return {
        "rollout_schema_version": ROLLOUT_SCHEMA_VERSION,
        "decision": decision,
        "severity": severity,
        "reasons": reasons,
        "counts": {
            "rollback_candidate": len(rollback_candidates),
            "pause": len(pauses),
            "none": len(nones),
        },
        "breadth": {"unique_metric_windows": len(unique_metric_windows)},
        "latest_evaluation": latest_eval,
    }


def recommended_control_event_from_aggregate(
    *,
    aggregate_result: Dict[str, Any],
    actor_id: str = "guardrail-aggregator",
) -> Optional[Dict[str, Any]]:
    decision = str(aggregate_result.get("decision", "")).upper().strip()
    latest = aggregate_result.get("latest_evaluation", {})
    signal = latest.get("signal", {})
    reasons = aggregate_result.get("reasons", [])
    if decision == "PAUSE":
        return build_pause_event(actor_id=actor_id, reason=f"aggregate pause: {','.join(reasons)}")
    if decision == "ROLLBACK_CANDIDATE":
        return build_rollback_event(
            trigger_mode="auto",
            actor_id=actor_id,
            reason=f"aggregate rollback candidate: {','.join(reasons)}",
            threshold_source=str(signal.get("source", "aggregate")),
            metric_name=str(signal.get("metric_name", "aggregate")),
            observed_value=float(signal.get("observed_value", 0.0)),
            threshold_value=float(signal.get("threshold_value", 0.0)),
            breach_window=str(signal.get("metric_window", "aggregate")),
        )
    return None


def ingest_monitor_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Normalize runtime monitor payload into canonical guardrail signal schema.
    Expected payload keys:
      experiment_id, package_hash, metric_name, metric_window, observed_value,
      threshold_value, threshold_direction, source, ts_utc (optional), source_event_id (optional)
    """
    return build_guardrail_signal(
        experiment_id=str(payload.get("experiment_id", "")),
        package_hash=str(payload.get("package_hash", "")),
        metric_name=str(payload.get("metric_name", "")),
        metric_window=str(payload.get("metric_window", "")),
        observed_value=float(payload.get("observed_value", 0.0)),
        threshold_value=float(payload.get("threshold_value", 0.0)),
        threshold_direction=str(payload.get("threshold_direction", "upper")),
        source=str(payload.get("source", "runtime-monitor")),
        ts_utc=payload.get("ts_utc"),
        source_event_id=payload.get("source_event_id"),
        idempotency_key=payload.get("idempotency_key"),
    )


def evaluate_promotion_eligibility(
    *,
    manifest: Dict[str, Any],
    promotion: Dict[str, Any],
    review_status: Dict[str, Any],
) -> Dict[str, Any]:
    reasons: List[str] = []

    promotion_decision = str(promotion.get("decision", "")).upper().strip()
    if promotion_decision != "PROMOTE":
        reasons.append(f"promotion_not_promote:{promotion_decision or 'missing'}")

    auth = check_promotion_authorization(manifest=manifest, review_status=review_status)
    if not auth.get("authorized", False):
        reasons.append(f"authorization_failed:{auth.get('reason', 'unknown')}")

    return {
        "rollout_schema_version": ROLLOUT_SCHEMA_VERSION,
        "eligible": len(reasons) == 0,
        "reasons": reasons,
        "promotion_decision": promotion_decision,
        "authorization": auth,
        "package_hash": manifest.get("package_hash"),
        "policy_version": manifest.get("provenance", {}).get("policy_version"),
        "parameter_set_version": manifest.get("provenance", {}).get("parameter_set_version"),
        "corpus_id": manifest.get("provenance", {}).get("corpus_id"),
    }


def build_launch_gate(
    *,
    manifest_path: Path,
    review_status_path: Path,
    promotion_path: Path,
    eligibility_path: Path,
    launched_by: str,
    cohort: str,
    experiment_arm: str,
    guardrails: Dict[str, Any],
    launched_at_utc: Optional[str] = None,
) -> Dict[str, Any]:
    if not launched_by.strip():
        raise ValueError("launched_by is required")
    if launched_at_utc is None:
        launched_at_utc = datetime.now(timezone.utc).isoformat()

    manifest = _load_json(manifest_path)
    promotion = _load_json(promotion_path)
    review_status = _load_json(review_status_path)
    eligibility = _load_json(eligibility_path)

    recomputed = evaluate_promotion_eligibility(
        manifest=manifest,
        promotion=promotion,
        review_status=review_status,
    )
    if not eligibility.get("eligible") or not recomputed.get("eligible"):
        raise ValueError("launch blocked: candidate is not promotion-eligible")

    return {
        "rollout_schema_version": ROLLOUT_SCHEMA_VERSION,
        "launched_at_utc": launched_at_utc,
        "launched_by": launched_by,
        "cohort": cohort,
        "experiment_arm": experiment_arm,
        "guardrails": guardrails,
        "package_hash": manifest.get("package_hash"),
        "manifest_sha256": _sha256_file(manifest_path),
        "review_status_sha256": _sha256_file(review_status_path),
        "promotion_sha256": _sha256_file(promotion_path),
        "eligibility_sha256": _sha256_file(eligibility_path),
        "policy_version": manifest.get("provenance", {}).get("policy_version"),
        "parameter_set_version": manifest.get("provenance", {}).get("parameter_set_version"),
        "corpus_id": manifest.get("provenance", {}).get("corpus_id"),
    }


def build_pause_event(*, actor_id: str, reason: str, ts_utc: Optional[str] = None) -> Dict[str, Any]:
    if not actor_id.strip():
        raise ValueError("actor_id is required")
    if not reason.strip():
        raise ValueError("reason is required")
    return {
        "event_type": "PAUSE",
        "trigger_mode": "manual",
        "actor_id": actor_id,
        "reason": reason,
        "ts_utc": ts_utc or datetime.now(timezone.utc).isoformat(),
    }


def build_rollback_event(
    *,
    trigger_mode: str,  # auto | manual
    actor_id: str,
    reason: str,
    threshold_source: str,
    metric_name: str,
    observed_value: float,
    threshold_value: float,
    breach_window: str,
    breach_timestamp_utc: Optional[str] = None,
) -> Dict[str, Any]:
    mode = trigger_mode.lower().strip()
    if mode not in {"auto", "manual"}:
        raise ValueError("trigger_mode must be auto or manual")
    if not actor_id.strip():
        raise ValueError("actor_id is required")
    if not reason.strip():
        raise ValueError("reason is required")
    return {
        "event_type": "ROLLBACK",
        "trigger_mode": mode,
        "actor_id": actor_id,
        "reason": reason,
        "threshold_source": threshold_source,
        "metric_name": metric_name,
        "observed_value": observed_value,
        "threshold_value": threshold_value,
        "breach_window": breach_window,
        "breach_timestamp_utc": breach_timestamp_utc or datetime.now(timezone.utc).isoformat(),
    }


def validate_state_transition(
    *,
    current_state: str,
    next_state: str,
    eligibility: Optional[Dict[str, Any]] = None,
    launch_gate: Optional[Dict[str, Any]] = None,
    rollback_event: Optional[Dict[str, Any]] = None,
    resume_rationale: Optional[str] = None,
    latest_guardrail_eval: Optional[Dict[str, Any]] = None,
    resume_guardrail_eval_ts: Optional[str] = None,
    active_rollback_breach: Optional[bool] = None,
    completion_meta: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    curr = current_state.upper().strip()
    nxt = next_state.upper().strip()
    reasons: List[str] = []

    if curr not in ALLOWED_STATES:
        reasons.append(f"invalid_current_state:{curr}")
    if nxt not in ALLOWED_STATES:
        reasons.append(f"invalid_next_state:{nxt}")
    if reasons:
        return {"allowed": False, "reasons": reasons}

    allowed_transitions = {
        "DRAFT": {"READY"},
        "READY": {"RUNNING"},
        "RUNNING": {"PAUSED", "COMPLETED", "ROLLED_BACK"},
        "PAUSED": {"RUNNING", "COMPLETED", "ROLLED_BACK"},
        "COMPLETED": set(),
        "ROLLED_BACK": set(),
    }
    if nxt not in allowed_transitions[curr]:
        reasons.append(f"transition_not_allowed:{curr}->{nxt}")

    if curr == "DRAFT" and nxt == "READY":
        if not eligibility or not eligibility.get("eligible", False):
            reasons.append("missing_or_ineligible_promotion_eligibility")
    if curr == "READY" and nxt == "RUNNING":
        if not launch_gate:
            reasons.append("missing_launch_gate")
    if curr == "PAUSED" and nxt == "RUNNING":
        if not resume_rationale or not resume_rationale.strip():
            reasons.append("missing_resume_rationale")
        if active_rollback_breach is True:
            reasons.append("active_rollback_breach_present")
        if latest_guardrail_eval is None:
            reasons.append("missing_latest_guardrail_eval")
        else:
            latest_ts = str(latest_guardrail_eval.get("evaluated_at_utc", ""))
            if not latest_ts:
                reasons.append("latest_guardrail_eval_missing_timestamp")
            if not resume_guardrail_eval_ts or resume_guardrail_eval_ts != latest_ts:
                reasons.append("resume_guardrail_eval_timestamp_mismatch")
            latest_decision = str(latest_guardrail_eval.get("decision", "")).upper().strip()
            if latest_decision == "ROLLBACK_CANDIDATE":
                reasons.append("latest_guardrail_eval_is_rollback_candidate")
    if nxt == "ROLLED_BACK":
        if not rollback_event:
            reasons.append("missing_rollback_event")
    if nxt == "COMPLETED":
        required = ("runtime_hours", "sample_size", "stop_reason")
        if not completion_meta:
            reasons.append("missing_completion_meta")
        else:
            for field in required:
                if completion_meta.get(field) in (None, "", []):
                    reasons.append(f"missing_completion_meta_field:{field}")

    return {"allowed": len(reasons) == 0, "reasons": reasons}


def transition_experiment_state(
    *,
    state_doc: Dict[str, Any],
    next_state: str,
    actor_id: str,
    reason: str,
    eligibility: Optional[Dict[str, Any]] = None,
    launch_gate: Optional[Dict[str, Any]] = None,
    rollback_event: Optional[Dict[str, Any]] = None,
    resume_rationale: Optional[str] = None,
    latest_guardrail_eval: Optional[Dict[str, Any]] = None,
    resume_guardrail_eval_ts: Optional[str] = None,
    active_rollback_breach: Optional[bool] = None,
    completion_meta: Optional[Dict[str, Any]] = None,
    ts_utc: Optional[str] = None,
) -> Dict[str, Any]:
    if not actor_id.strip():
        raise ValueError("actor_id is required")
    if not reason.strip():
        raise ValueError("reason is required")
    current_state = str(state_doc.get("state", "DRAFT")).upper().strip()
    validation = validate_state_transition(
        current_state=current_state,
        next_state=next_state,
        eligibility=eligibility,
        launch_gate=launch_gate,
        rollback_event=rollback_event,
        resume_rationale=resume_rationale,
        latest_guardrail_eval=latest_guardrail_eval,
        resume_guardrail_eval_ts=resume_guardrail_eval_ts,
        active_rollback_breach=active_rollback_breach,
        completion_meta=completion_meta,
    )
    if not validation["allowed"]:
        raise ValueError(f"transition blocked: {', '.join(validation['reasons'])}")

    now = ts_utc or datetime.now(timezone.utc).isoformat()
    nxt = next_state.upper().strip()
    event = {
        "from_state": current_state,
        "to_state": nxt,
        "actor_id": actor_id,
        "reason": reason,
        "ts_utc": now,
        "reasons_validated": validation["reasons"],
    }
    if launch_gate is not None:
        event["launch_gate_hash"] = launch_gate.get("manifest_sha256")
    if rollback_event is not None:
        event["rollback_event"] = rollback_event
    if completion_meta is not None:
        event["completion_meta"] = completion_meta

    history = list(state_doc.get("history", []))
    history.append(event)
    new_doc = dict(state_doc)
    new_doc["rollout_schema_version"] = ROLLOUT_SCHEMA_VERSION
    new_doc["state"] = nxt
    new_doc["updated_at_utc"] = now
    new_doc["history"] = history
    return new_doc


def append_transition_log(*, state_path: Path, state_doc: Dict[str, Any]) -> None:
    _json_dump(state_doc, state_path)
