from datetime import datetime, timedelta

import pytest
from pydantic import ValidationError

from app.config import Settings
from app.kernel.constraints import ConstraintGate
from app.kernel.contracts import (
    ActionType,
    Channel,
    ConstraintReason,
    Direction,
    EventType,
    ObservedEvent,
    RelationshipFacts,
    RelationshipInferred,
    RelationshipState,
)
from app.models.core import Relationship
from app.models.physics import decide_action_with_context


def test_observed_event_rejects_empty_contact_id():
    with pytest.raises(ValidationError):
        ObservedEvent(
            event_id="evt-1",
            contact_id="",
            timestamp=datetime.utcnow(),
            channel=Channel.email,
            direction=Direction.inbound,
            event_type=EventType.message_received,
        )


def test_constraint_gate_blocks_send_actions_during_cooldown():
    now = datetime(2026, 3, 8, 12, 0, 0)
    state = RelationshipState(
        relationship_id="rel-1",
        facts=RelationshipFacts(
            last_contact_at=now - timedelta(hours=1),
            last_outbound_at=now - timedelta(hours=1),
        ),
        inferred=RelationshipInferred(),
    )

    gate = ConstraintGate(Settings(min_cooldown_hours=24.0, max_tension=0.85))
    result = gate.evaluate(state, now)

    assert ConstraintReason.hard_cooldown_active in result.reasons
    assert ActionType.send_nudge in result.blocked_actions
    assert ActionType.send_fulfillment in result.blocked_actions
    assert ActionType.wait in result.allowed_actions


def test_constraint_gate_allows_fulfillment_for_healthy_reply_debt_during_cooldown():
    now = datetime(2026, 3, 8, 12, 0, 0)
    state = RelationshipState(
        relationship_id="rel-healthy-debt",
        facts=RelationshipFacts(
            last_contact_at=now - timedelta(minutes=20),
            last_outbound_at=now - timedelta(minutes=20),
            last_inbound_at=now - timedelta(minutes=1),
            debt_created_at=now - timedelta(minutes=1),
        ),
        inferred=RelationshipInferred(
            trust_score=1.0,
            tension_score=0.0,
            reply_debt=1,
            engagement_score=96.0,
            churn_risk=0.1,
        ),
    )

    gate = ConstraintGate(Settings(min_cooldown_hours=24.0, max_tension=0.85))
    result = gate.evaluate(state, now)

    assert ConstraintReason.hard_cooldown_active in result.reasons
    assert ActionType.send_fulfillment in result.allowed_actions
    assert ActionType.send_nudge in result.blocked_actions
    assert ActionType.send_gentle_ping in result.blocked_actions


def test_constraint_gate_keeps_fulfillment_blocked_when_debt_override_thresholds_fail():
    now = datetime(2026, 3, 8, 12, 0, 0)
    state = RelationshipState(
        relationship_id="rel-unhealthy-debt",
        facts=RelationshipFacts(
            last_contact_at=now - timedelta(minutes=20),
            last_outbound_at=now - timedelta(minutes=20),
            last_inbound_at=now - timedelta(minutes=1),
            debt_created_at=now - timedelta(minutes=1),
        ),
        inferred=RelationshipInferred(
            trust_score=0.6,
            tension_score=0.0,
            reply_debt=1,
            engagement_score=60.0,
            churn_risk=0.5,
        ),
    )

    gate = ConstraintGate(Settings(min_cooldown_hours=24.0, max_tension=0.85))
    result = gate.evaluate(state, now)

    assert ConstraintReason.hard_cooldown_active in result.reasons
    assert ActionType.send_fulfillment in result.blocked_actions


def test_policy_never_returns_blocked_send_action():
    now = datetime(2026, 3, 8, 12, 0, 0)
    rel = Relationship(
        id="rel-1",
        person_id="person-1",
        stage="onboarded",
        trust_score=0.5,
        interaction_tension=0.9,
        intent_debt=0,
        last_contact_at=now - timedelta(days=10),
        last_outbound_at=now - timedelta(hours=1),
        active=True,
        dependency_blocked=False,
        engagement_score=50.0,
        churn_risk=0.0,
        cadence_days=7.0,
    )

    decision = decide_action_with_context(rel, now, settings=Settings(min_cooldown_hours=24.0, max_tension=0.85))

    assert decision.action_type in {ActionType.wait, ActionType.no_action, ActionType.internal_alert}
    assert decision.action_type not in {
        ActionType.send_fulfillment,
        ActionType.send_nudge,
        ActionType.send_gentle_ping,
        ActionType.send_with_apology,
    }


def test_policy_returns_fulfillment_when_healthy_reply_debt_overrides_cooldown():
    now = datetime(2026, 3, 8, 12, 0, 0)
    rel = Relationship(
        id="rel-healthy-isa",
        person_id="person-1",
        stage="value_delivered",
        trust_score=1.0,
        interaction_tension=0.0,
        intent_debt=1,
        last_contact_at=now - timedelta(minutes=1),
        last_inbound_at=now - timedelta(minutes=1),
        last_outbound_at=now - timedelta(minutes=20),
        debt_created_at=now - timedelta(minutes=1),
        active=True,
        dependency_blocked=False,
        engagement_score=96.0,
        churn_risk=0.1,
        cadence_days=7.0,
    )

    decision = decide_action_with_context(rel, now, settings=Settings(min_cooldown_hours=24.0, max_tension=0.85))

    assert decision.action_type == ActionType.send_fulfillment
