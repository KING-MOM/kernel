from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.kernel.authorization import check_promotion_authorization


ROLLOUT_SCHEMA_VERSION = "1.0"
ALLOWED_STATES = {"DRAFT", "READY", "RUNNING", "PAUSED", "COMPLETED", "ROLLED_BACK"}


def _json_dump(obj: Dict[str, Any], path: Path) -> None:
    path.write_text(json.dumps(obj, indent=2, sort_keys=True, ensure_ascii=True) + "\n")


def _load_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text())


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


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
    if nxt == "ROLLED_BACK":
        if not rollback_event:
            reasons.append("missing_rollback_event")

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
