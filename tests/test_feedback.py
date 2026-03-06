from datetime import datetime, timedelta

from app.models.core import Relationship, Outbox
from app.models.feedback import record_outcome, compute_churn_risk


def _make_rel_and_outbox(db, sent_hours_ago=2):
    from app.models.core import Person
    person = Person(agent_id="test", external_id="fb-person-1", timezone="UTC")
    db.add(person)
    db.flush()

    rel = Relationship(
        person_id=person.id,
        active=True,
        stage="engaged",
        trust_score=0.5,
        engagement_score=50.0,
    )
    db.add(rel)
    db.flush()

    sent_at = datetime.utcnow() - timedelta(hours=sent_hours_ago)
    outbox = Outbox(
        relationship_id=rel.id,
        action="SEND_FULFILLMENT",
        sent_at=sent_at,
    )
    db.add(outbox)
    db.flush()

    return rel, outbox


def test_record_outcome_fast_reply(db_session):
    rel, outbox = _make_rel_and_outbox(db_session, sent_hours_ago=2)
    initial_trust = rel.trust_score
    initial_engagement = rel.engagement_score

    replied_at = outbox.sent_at + timedelta(hours=1)
    record_outcome(db_session, outbox.id, {
        "delivered": True,
        "replied_at": replied_at,
    })
    db_session.flush()

    assert rel.trust_score > initial_trust
    assert rel.engagement_score > initial_engagement
    assert outbox.replied_at == replied_at


def test_record_outcome_slow_reply(db_session):
    rel, outbox = _make_rel_and_outbox(db_session, sent_hours_ago=72)
    initial_engagement = rel.engagement_score

    replied_at = outbox.sent_at + timedelta(hours=72)
    record_outcome(db_session, outbox.id, {
        "replied_at": replied_at,
    })
    db_session.flush()

    assert rel.engagement_score < initial_engagement


def test_record_outcome_delivered_only(db_session):
    rel, outbox = _make_rel_and_outbox(db_session)
    record_outcome(db_session, outbox.id, {"delivered": True})
    db_session.flush()
    assert outbox.delivered is True
    assert outbox.replied_at is None


def test_record_outcome_nonexistent_outbox(db_session):
    # Should not raise
    record_outcome(db_session, "nonexistent-id", {"delivered": True})


def test_churn_risk_no_outbox(db_session):
    rel = Relationship(
        person_id="dummy",
        active=True,
        stage="onboarded",
    )
    # Don't add to DB, just test function
    risk = compute_churn_risk(db_session, rel)
    assert risk == 0.0


def test_churn_risk_all_replied(db_session):
    from app.models.core import Person
    person = Person(agent_id="test", external_id="churn-person-1", timezone="UTC")
    db_session.add(person)
    db_session.flush()

    rel = Relationship(person_id=person.id, active=True, stage="engaged")
    db_session.add(rel)
    db_session.flush()

    for i in range(3):
        sent = datetime.utcnow() - timedelta(days=i)
        outbox = Outbox(
            relationship_id=rel.id,
            action="SEND_NUDGE",
            sent_at=sent,
            replied_at=sent + timedelta(hours=2),
        )
        db_session.add(outbox)
    db_session.flush()

    risk = compute_churn_risk(db_session, rel)
    assert risk == 0.0


def test_churn_risk_none_replied(db_session):
    from app.models.core import Person
    person = Person(agent_id="test", external_id="churn-person-2", timezone="UTC")
    db_session.add(person)
    db_session.flush()

    rel = Relationship(person_id=person.id, active=True, stage="engaged")
    db_session.add(rel)
    db_session.flush()

    for i in range(3):
        sent = datetime.utcnow() - timedelta(days=i)
        outbox = Outbox(
            relationship_id=rel.id,
            action="SEND_NUDGE",
            sent_at=sent,
        )
        db_session.add(outbox)
    db_session.flush()

    risk = compute_churn_risk(db_session, rel)
    assert risk == 1.0
