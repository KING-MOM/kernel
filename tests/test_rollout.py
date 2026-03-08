import json
from pathlib import Path

import pytest

from app.kernel.rollout import (
    build_launch_gate,
    build_guardrail_signal,
    build_rollback_event,
    evaluate_promotion_eligibility,
    evaluate_guardrail_signal,
    has_active_rollback_breach,
    recommended_control_event_from_guardrail,
    transition_experiment_state,
    validate_state_transition,
)


def _manifest(hash_value: str = "h1"):
    return {
        "package_hash": hash_value,
        "review_workflow_version": "1.0",
        "report_schema_version": "1.0",
        "provenance": {
            "policy_version": "v1.2",
            "parameter_set_version": "pset-1",
            "corpus_id": "corpus-a",
        },
    }


def _review(hash_value: str = "h1", status: str = "APPROVED"):
    return {
        "status": status,
        "rationale": "ok",
        "package_hash": hash_value,
    }


def _promotion(decision: str = "PROMOTE"):
    return {"decision": decision}


def test_promotion_eligibility_requires_promote_and_authorized():
    eligible = evaluate_promotion_eligibility(
        manifest=_manifest("h1"),
        promotion=_promotion("PROMOTE"),
        review_status=_review("h1", "APPROVED"),
    )
    assert eligible["eligible"] is True

    denied = evaluate_promotion_eligibility(
        manifest=_manifest("h1"),
        promotion=_promotion("HOLD_BASELINE"),
        review_status=_review("h1", "APPROVED"),
    )
    assert denied["eligible"] is False
    assert any(r.startswith("promotion_not_promote") for r in denied["reasons"])


def test_validate_state_transition_prerequisites():
    bad = validate_state_transition(current_state="DRAFT", next_state="READY", eligibility={"eligible": False})
    assert bad["allowed"] is False

    ok = validate_state_transition(current_state="DRAFT", next_state="READY", eligibility={"eligible": True})
    assert ok["allowed"] is True

    no_launch = validate_state_transition(current_state="READY", next_state="RUNNING")
    assert no_launch["allowed"] is False

    rollback_missing = validate_state_transition(current_state="RUNNING", next_state="ROLLED_BACK")
    assert rollback_missing["allowed"] is False

    paused_resume_missing = validate_state_transition(current_state="PAUSED", next_state="RUNNING")
    assert paused_resume_missing["allowed"] is False

    paused_resume_blocked = validate_state_transition(
        current_state="PAUSED",
        next_state="RUNNING",
        resume_rationale="investigation complete",
        latest_guardrail_eval={"decision": "NONE", "evaluated_at_utc": "2026-03-08T12:00:00+00:00"},
        resume_guardrail_eval_ts="2026-03-08T12:00:00+00:00",
        active_rollback_breach=True,
    )
    assert paused_resume_blocked["allowed"] is False

    completed_missing_meta = validate_state_transition(current_state="RUNNING", next_state="COMPLETED")
    assert completed_missing_meta["allowed"] is False


def test_transition_experiment_state_and_rollback_event():
    state = {"state": "DRAFT", "history": []}
    state = transition_experiment_state(
        state_doc=state,
        next_state="READY",
        actor_id="ops",
        reason="eligible",
        eligibility={"eligible": True},
    )
    assert state["state"] == "READY"

    launch_gate = {"manifest_sha256": "abc"}
    state = transition_experiment_state(
        state_doc=state,
        next_state="RUNNING",
        actor_id="ops",
        reason="launch",
        launch_gate=launch_gate,
    )
    assert state["state"] == "RUNNING"

    rollback = build_rollback_event(
        trigger_mode="auto",
        actor_id="monitor",
        reason="negative signal threshold breached",
        threshold_source="guardrails.v1",
        metric_name="negative_signal_rate",
        observed_value=0.18,
        threshold_value=0.10,
        breach_window="24h",
    )
    state = transition_experiment_state(
        state_doc=state,
        next_state="ROLLED_BACK",
        actor_id="monitor",
        reason="auto rollback",
        rollback_event=rollback,
    )
    assert state["state"] == "ROLLED_BACK"
    assert state["history"][-1]["rollback_event"]["trigger_mode"] == "auto"


def test_paused_resume_and_completed_with_meta():
    state = {"state": "PAUSED", "history": []}
    latest_eval = {"decision": "NONE", "evaluated_at_utc": "2026-03-08T12:00:00+00:00"}
    state = transition_experiment_state(
        state_doc=state,
        next_state="RUNNING",
        actor_id="ops",
        reason="resume",
        resume_rationale="breach cleared and monitor stable",
        latest_guardrail_eval=latest_eval,
        resume_guardrail_eval_ts="2026-03-08T12:00:00+00:00",
        active_rollback_breach=False,
    )
    assert state["state"] == "RUNNING"

    state = transition_experiment_state(
        state_doc=state,
        next_state="COMPLETED",
        actor_id="ops",
        reason="end experiment",
        completion_meta={"runtime_hours": 72, "sample_size": 1200, "stop_reason": "planned end"},
    )
    assert state["state"] == "COMPLETED"
    assert state["history"][-1]["completion_meta"]["sample_size"] == 1200


def test_guardrail_signal_eval_and_recommended_event():
    signal = build_guardrail_signal(
        experiment_id="exp-1",
        package_hash="pkg-1",
        metric_name="negative_signal_rate",
        metric_window="24h",
        observed_value=0.18,
        threshold_value=0.10,
        threshold_direction="upper",
        source="runtime-monitor",
        source_event_id="evt-1",
    )
    evaluation = evaluate_guardrail_signal(signal)
    assert evaluation["decision"] == "ROLLBACK_CANDIDATE"
    assert evaluation["severity"] == "hard"
    event = recommended_control_event_from_guardrail(evaluation=evaluation)
    assert event is not None
    assert event["event_type"] == "ROLLBACK"
    assert event["trigger_mode"] == "auto"


def test_active_rollback_breach_from_latest_unresolved():
    ev1 = {
        "decision": "ROLLBACK_CANDIDATE",
        "resolved": False,
        "evaluated_at_utc": "2026-03-08T12:00:00+00:00",
        "signal": {"metric_name": "negative_signal_rate", "metric_window": "24h", "package_hash": "p1"},
    }
    ev2 = {
        "decision": "NONE",
        "resolved": False,
        "evaluated_at_utc": "2026-03-08T13:00:00+00:00",
        "signal": {"metric_name": "negative_signal_rate", "metric_window": "24h", "package_hash": "p1"},
    }
    assert has_active_rollback_breach([ev1]) is True
    assert has_active_rollback_breach([ev1, ev2]) is False


def test_build_launch_gate_binds_hashes(tmp_path: Path):
    manifest_path = tmp_path / "manifest.json"
    review_path = tmp_path / "review_status.json"
    promotion_path = tmp_path / "promotion.json"
    eligibility_path = tmp_path / "eligibility.json"

    manifest = _manifest("h1")
    review = _review("h1", "APPROVED")
    promotion = _promotion("PROMOTE")
    eligibility = evaluate_promotion_eligibility(
        manifest=manifest,
        promotion=promotion,
        review_status=review,
    )

    manifest_path.write_text(json.dumps(manifest, sort_keys=True) + "\n")
    review_path.write_text(json.dumps(review, sort_keys=True) + "\n")
    promotion_path.write_text(json.dumps(promotion, sort_keys=True) + "\n")
    eligibility_path.write_text(json.dumps(eligibility, sort_keys=True) + "\n")

    launch = build_launch_gate(
        manifest_path=manifest_path,
        review_status_path=review_path,
        promotion_path=promotion_path,
        eligibility_path=eligibility_path,
        launched_by="ops",
        cohort="10pct",
        experiment_arm="candidate",
        guardrails={"negative_signal_rate_max": 0.1},
    )
    assert launch["package_hash"] == "h1"
    assert launch["review_status_sha256"]


def test_build_launch_gate_blocks_ineligible(tmp_path: Path):
    manifest_path = tmp_path / "manifest.json"
    review_path = tmp_path / "review_status.json"
    promotion_path = tmp_path / "promotion.json"
    eligibility_path = tmp_path / "eligibility.json"

    manifest_path.write_text(json.dumps(_manifest("h1"), sort_keys=True) + "\n")
    review_path.write_text(json.dumps(_review("h1", "REJECTED"), sort_keys=True) + "\n")
    promotion_path.write_text(json.dumps(_promotion("PROMOTE"), sort_keys=True) + "\n")
    eligibility_path.write_text(json.dumps({"eligible": False}, sort_keys=True) + "\n")

    with pytest.raises(ValueError):
        build_launch_gate(
            manifest_path=manifest_path,
            review_status_path=review_path,
            promotion_path=promotion_path,
            eligibility_path=eligibility_path,
            launched_by="ops",
            cohort="10pct",
            experiment_arm="candidate",
            guardrails={"negative_signal_rate_max": 0.1},
        )
