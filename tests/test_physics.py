import math
from datetime import datetime, timedelta

from app.config import Settings
from app.models.core import Relationship
from app.models.physics import (
    decay_tension, react_to_event, decide_action, get_days_passed,
    compute_engagement_score, compute_urgency_score,
)


def make_rel(**kwargs) -> Relationship:
    defaults = {
        "interaction_tension": 0.5,
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


def test_get_days_passed():
    t1 = datetime(2026, 1, 1)
    t2 = datetime(2026, 1, 3, 12)
    assert abs(get_days_passed(t2, t1) - 2.5) < 0.001


def test_decay_tension_zero_days():
    now = datetime(2026, 1, 1)
    rel = make_rel(interaction_tension=0.8, last_contact_at=now)
    result = decay_tension(rel, now)
    assert result == 0.8


def test_decay_tension_positive_days():
    now = datetime(2026, 1, 1)
    later = now + timedelta(days=5)
    rel = make_rel(interaction_tension=0.8, last_contact_at=now)
    s = Settings()
    result = decay_tension(rel, later, settings=s)
    expected = 0.8 * math.exp(-0.15 * 5)
    assert abs(result - expected) < 0.0001


def test_decay_tension_exponential():
    rel = make_rel(interaction_tension=1.0, last_contact_at=datetime.utcnow() - timedelta(days=2))
    now = datetime.utcnow()
    decayed = decay_tension(rel, now)
    assert 0.0 < decayed < 1.0


def test_react_message_received():
    now = datetime(2026, 1, 5)
    rel = make_rel(interaction_tension=0.5, trust_score=0.3)
    react_to_event(rel, "message_received", now)
    assert rel.interaction_tension == 0.0
    assert rel.intent_debt == 1
    assert rel.debt_created_at == now
    assert rel.last_contact_at == now
    assert rel.last_inbound_at == now
    assert rel.trust_score == 0.4


def test_react_message_sent():
    now = datetime(2026, 1, 5)
    rel = make_rel(interaction_tension=0.2, intent_debt=1, trust_score=0.5)
    react_to_event(rel, "message_sent", now)
    assert abs(rel.interaction_tension - 0.6) < 0.0001
    assert rel.intent_debt == 0
    assert rel.debt_created_at is None
    assert rel.last_outbound_at == now
    assert rel.trust_score == 0.55


def test_react_sets_debt_and_timestamps():
    rel = make_rel(interaction_tension=0.0, trust_score=0.5)
    now = datetime.utcnow()
    react_to_event(rel, "message_received", now)
    assert rel.intent_debt == 1
    assert rel.debt_created_at == now
    assert rel.last_inbound_at == now
    assert rel.interaction_tension == 0.0


def test_react_clears_debt_on_send():
    now = datetime.utcnow()
    rel = make_rel(interaction_tension=0.0, trust_score=0.5)
    react_to_event(rel, "message_received", now)
    later = now + timedelta(hours=1)
    react_to_event(rel, "message_sent", later)
    assert rel.intent_debt == 0
    assert rel.debt_created_at is None
    assert rel.last_outbound_at == later


def test_decide_with_debt():
    now = datetime(2026, 1, 5)
    rel = make_rel(intent_debt=1, debt_created_at=now)
    action, reason, confidence = decide_action(rel, now)
    assert action == "SEND_FULFILLMENT"
    assert confidence > 0.0


def test_decide_overdue_debt():
    now = datetime(2026, 1, 1)
    later = now + timedelta(days=4)
    rel = make_rel(intent_debt=1, debt_created_at=now)
    action, reason, confidence = decide_action(rel, later)
    assert action == "SEND_WITH_APOLOGY"
    assert "Overdue" in reason


def test_decide_blocked_debt():
    now = datetime(2026, 1, 5)
    rel = make_rel(intent_debt=1, dependency_blocked=True)
    action, reason, confidence = decide_action(rel, now)
    assert action == "INTERNAL_ALERT"


def test_decide_cooldown():
    now = datetime(2026, 1, 1, 12)
    rel = make_rel(
        last_outbound_at=now - timedelta(hours=2),
        interaction_tension=0.3,
    )
    action, reason, confidence = decide_action(rel, now)
    assert action == "WAIT"
    assert "cooldown" in reason.lower()


def test_decide_high_tension():
    now = datetime(2026, 1, 5)
    rel = make_rel(interaction_tension=0.9)
    action, reason, confidence = decide_action(rel, now)
    assert action == "WAIT"


def test_decide_nudge_long_silence_high_trust():
    base = datetime(2026, 1, 1)
    now = base + timedelta(days=35)
    rel = make_rel(
        intent_debt=-1,
        trust_score=0.7,
        last_contact_at=base,
        interaction_tension=0.0,
    )
    action, reason, confidence = decide_action(rel, now)
    assert action == "SEND_NUDGE"


def test_decide_ghosted():
    """Low trust + long silence: physics sends gentle ping, lifecycle handles dormancy transition."""
    base = datetime(2026, 1, 1)
    now = base + timedelta(days=15)
    rel = make_rel(
        intent_debt=-1,
        trust_score=0.3,
        last_contact_at=base,
        interaction_tension=0.0,
    )
    action, reason, confidence = decide_action(rel, now)
    assert action == "SEND_GENTLE_PING"


def test_decide_gentle_ping():
    base = datetime(2026, 1, 1)
    now = base + timedelta(days=15)
    rel = make_rel(
        intent_debt=-1,
        trust_score=0.5,
        last_contact_at=base,
        interaction_tension=0.0,
    )
    action, reason, confidence = decide_action(rel, now)
    assert action == "SEND_GENTLE_PING"


def test_decide_no_action():
    now = datetime(2026, 1, 5)
    rel = make_rel()
    action, reason, confidence = decide_action(rel, now)
    assert action == "NO_ACTION"


def test_custom_settings_affect_decay():
    s = Settings(lambda_decay=0.5)
    now = datetime(2026, 1, 1)
    later = now + timedelta(days=2)
    rel = make_rel(interaction_tension=1.0, last_contact_at=now)
    result = decay_tension(rel, later, settings=s)
    expected = 1.0 * math.exp(-0.5 * 2)
    assert abs(result - expected) < 0.0001


# Phase 2: Multi-dimensional scoring tests

def test_engagement_score_recent_contact():
    now = datetime(2026, 1, 5)
    rel = make_rel(
        last_contact_at=now,
        trust_score=0.8,
        last_inbound_at=now,
        last_outbound_at=now,
    )
    score = compute_engagement_score(rel, now)
    assert score > 70.0  # recent + high trust + bidirectional


def test_engagement_score_old_contact():
    now = datetime(2026, 1, 1)
    later = now + timedelta(days=60)
    rel = make_rel(last_contact_at=now, trust_score=0.2)
    score = compute_engagement_score(rel, later)
    assert score < 50.0  # old + low trust


def test_engagement_score_with_debt_penalty():
    now = datetime(2026, 1, 1)
    later = now + timedelta(days=5)
    rel = make_rel(
        last_contact_at=now,
        intent_debt=1,
        debt_created_at=now,
        trust_score=0.5,
    )
    score_with_debt = compute_engagement_score(rel, later)
    rel2 = make_rel(last_contact_at=now, trust_score=0.5)
    score_no_debt = compute_engagement_score(rel2, later)
    assert score_with_debt < score_no_debt


def test_urgency_with_debt():
    now = datetime(2026, 1, 1)
    later = now + timedelta(days=2)
    rel = make_rel(intent_debt=1, debt_created_at=now, last_contact_at=now)
    urgency = compute_urgency_score(rel, later)
    assert urgency > 0.5


def test_urgency_past_cadence():
    now = datetime(2026, 1, 1)
    later = now + timedelta(days=14)
    rel = make_rel(last_contact_at=now, cadence_days=7.0)
    urgency = compute_urgency_score(rel, later)
    assert urgency > 0.3


def test_urgency_within_cadence():
    now = datetime(2026, 1, 1)
    later = now + timedelta(days=3)
    rel = make_rel(last_contact_at=now, cadence_days=7.0)
    urgency = compute_urgency_score(rel, later)
    assert urgency < 0.1


def test_decide_returns_confidence():
    now = datetime(2026, 1, 5)
    rel = make_rel(intent_debt=1, debt_created_at=now)
    action, reason, confidence = decide_action(rel, now)
    assert 0.0 <= confidence <= 1.0


def test_decide_dormant_stage():
    base = datetime(2026, 1, 1)
    now = base + timedelta(days=15)
    rel = make_rel(
        intent_debt=-1,
        trust_score=0.5,
        last_contact_at=base,
        interaction_tension=0.0,
        stage="dormant",
    )
    action, reason, confidence = decide_action(rel, now)
    assert action in ("WAIT", "SEND_GENTLE_PING")


def test_decide_churned_stage():
    base = datetime(2026, 1, 1)
    now = base + timedelta(days=15)
    rel = make_rel(
        intent_debt=-1,
        last_contact_at=base,
        interaction_tension=0.0,
        stage="churned",
    )
    action, reason, confidence = decide_action(rel, now)
    assert action == "NO_ACTION"
