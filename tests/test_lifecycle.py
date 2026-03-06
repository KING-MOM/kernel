import pytest
from datetime import datetime, timedelta

from app.models.core import Relationship
from app.models.lifecycle import transition_stage, apply_transition, VALID_TRANSITIONS


def make_rel(**kwargs) -> Relationship:
    defaults = {
        "interaction_tension": 0.0,
        "intent_debt": 0,
        "trust_score": 0.5,
        "last_contact_at": datetime(2026, 1, 1),
        "last_inbound_at": None,
        "last_outbound_at": None,
        "debt_created_at": None,
        "dependency_blocked": False,
        "stage": "onboarded",
        "active": True,
        "engagement_score": 50.0,
        "churn_risk": 0.0,
        "relationship_type": "general",
        "priority": 5,
        "cadence_days": 7.0,
        "next_decision_at": None,
    }
    defaults.update(kwargs)
    return Relationship(**defaults)


def test_onboarded_to_warm():
    rel = make_rel(trust_score=0.35, stage="onboarded")
    now = datetime(2026, 1, 5)
    result = transition_stage(rel, now)
    assert result == "warm"


def test_warm_to_engaged():
    rel = make_rel(trust_score=0.55, stage="warm")
    now = datetime(2026, 1, 5)
    result = transition_stage(rel, now)
    assert result == "engaged"


def test_engaged_to_value_delivered():
    rel = make_rel(trust_score=0.75, intent_debt=0, stage="engaged")
    now = datetime(2026, 1, 5)
    result = transition_stage(rel, now)
    assert result == "value_delivered"


def test_no_transition_low_trust():
    rel = make_rel(trust_score=0.2, stage="onboarded")
    now = datetime(2026, 1, 5)
    result = transition_stage(rel, now)
    assert result is None


def test_warm_to_dormant_silence():
    base = datetime(2026, 1, 1)
    now = base + timedelta(days=35)
    rel = make_rel(stage="warm", last_contact_at=base)
    result = transition_stage(rel, now)
    assert result == "dormant"


def test_dormant_to_churned():
    base = datetime(2026, 1, 1)
    now = base + timedelta(days=95)
    rel = make_rel(stage="dormant", last_contact_at=base)
    result = transition_stage(rel, now)
    assert result == "churned"


def test_re_engagement_on_inbound():
    now = datetime(2026, 3, 1, 12)
    rel = make_rel(
        stage="dormant",
        last_contact_at=datetime(2026, 1, 1),
        last_inbound_at=datetime(2026, 3, 1, 11),  # recent inbound
    )
    result = transition_stage(rel, now)
    assert result == "re_engaged"


def test_churned_re_engagement():
    now = datetime(2026, 3, 1, 12)
    rel = make_rel(
        stage="churned",
        last_contact_at=datetime(2025, 10, 1),
        last_inbound_at=datetime(2026, 3, 1, 11),
    )
    result = transition_stage(rel, now)
    assert result == "re_engaged"


def test_apply_valid_transition():
    rel = make_rel(stage="onboarded")
    now = datetime(2026, 1, 5)
    apply_transition(rel, "warm", now)
    assert rel.stage == "warm"


def test_apply_invalid_transition_raises():
    rel = make_rel(stage="onboarded")
    now = datetime(2026, 1, 5)
    with pytest.raises(ValueError, match="Invalid transition"):
        apply_transition(rel, "churned", now)


def test_all_stages_have_transitions():
    for stage in VALID_TRANSITIONS:
        assert len(VALID_TRANSITIONS[stage]) > 0
