import json
from pathlib import Path

import pytest

from app.kernel.rollout import (
    build_launch_gate,
    build_rollback_event,
    evaluate_promotion_eligibility,
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
