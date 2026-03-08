from datetime import datetime, timedelta

from app.config import Settings
from app.kernel.replay import ReplayTimelineItem, replay_timeline
from app.models.core import Relationship


def _make_rel(**kwargs) -> Relationship:
    base = {
        "id": "rel-replay-1",
        "person_id": "person-replay-1",
        "stage": "onboarded",
        "trust_score": 0.5,
        "interaction_tension": 0.0,
        "intent_debt": 0,
        "last_contact_at": datetime(2026, 1, 1, 10, 0, 0),
        "last_inbound_at": None,
        "last_outbound_at": None,
        "debt_created_at": None,
        "dependency_blocked": False,
        "active": True,
        "engagement_score": 50.0,
        "churn_risk": 0.0,
        "relationship_type": "general",
        "priority": 5,
        "cadence_days": 7.0,
        "next_decision_at": None,
    }
    base.update(kwargs)
    return Relationship(**base)


def test_replay_timeline_deterministic_decisions_and_hashes():
    rel = _make_rel()
    t0 = datetime(2026, 1, 2, 9, 0, 0)

    timeline = [
        ReplayTimelineItem(ts=t0, kind="event", event_type="message_received"),
        ReplayTimelineItem(ts=t0 + timedelta(minutes=1), kind="decision"),
        ReplayTimelineItem(ts=t0 + timedelta(minutes=2), kind="decision"),
    ]

    settings = Settings(min_cooldown_hours=24.0, max_tension=0.85)

    run1 = replay_timeline(rel, timeline, settings=settings)
    run2 = replay_timeline(rel, timeline, settings=settings)

    assert len(run1) == 2
    assert len(run2) == 2

    # Decision 1: debt exists after inbound => fulfillment
    assert run1[0].decision.action_type.value == "SEND_FULFILLMENT"
    assert "PAY_DEBT" in run1[0].decision.reason_codes

    # Decision 2: immediate post-send => cooldown blocks sends => wait/no action
    assert "HARD_COOLDOWN_ACTIVE" in run1[1].constraint_reasons
    assert run1[1].decision.action_type.value in {"WAIT", "NO_ACTION"}

    # Deterministic replay should generate identical hashes and actions
    assert [r.state_hash for r in run1] == [r.state_hash for r in run2]
    assert [r.decision.action_type.value for r in run1] == [r.decision.action_type.value for r in run2]


def test_replay_blocks_send_when_dependency_blocked():
    rel = _make_rel(intent_debt=1, dependency_blocked=True, debt_created_at=datetime(2026, 1, 2, 9, 0, 0))
    t0 = datetime(2026, 1, 2, 9, 1, 0)

    timeline = [ReplayTimelineItem(ts=t0, kind="decision")]
    result = replay_timeline(rel, timeline)

    assert len(result) == 1
    assert "DEPENDENCY_BLOCKED" in result[0].constraint_reasons
    assert result[0].decision.action_type.value == "INTERNAL_ALERT"
    assert "SEND_FULFILLMENT" in result[0].blocked_actions
