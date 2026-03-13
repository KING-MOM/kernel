import logging
from typing import Optional, List
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import desc, asc

from app.models.core import Person, Relationship, Event, Inbox, Outbox
from app.kernel.contracts import Channel
from app.models.physics import (
    compute_engagement_score,
    compute_next_decision_at,
    decay_tension,
    decide_action_with_context,
    react_to_event,
)
from app.kernel.identities import person_id_aliases, canonical_person_external_id
from app.models.lifecycle import transition_stage, apply_transition
from app.models.temporal import get_golden_hours
from app.models.feedback import record_outcome, compute_churn_risk
from app.api.auth import verify_api_key
from app.api.dependencies import get_db
from app.api.schemas import (
    InboundEvent,
    OutboundEvent,
    DecideRequest,
    DecideBatchRequest,
    SweepRequest,
    OutcomeEvent,
    InboundResponse,
    OutboundResponse,
    DecideResponse,
    DecideBatchResponse,
    Decision,
    SweepResponse,
    SweepDecision,
    OutcomeResponse,
    GoldenHour,
)

logger = logging.getLogger(__name__)

router = APIRouter(dependencies=[Depends(verify_api_key)])


def _preferred_person_match(persons: List[Person], canonical_external_id: str) -> Optional[Person]:
    if not persons:
        return None
    exact = [person for person in persons if person.external_id == canonical_external_id]
    pool = exact or persons
    # Deterministic ordering matters once legacy rows already exist.
    return sorted(
        pool,
        key=lambda person: (
            person.created_at is None,
            person.created_at,
            person.id,
        ),
    )[0]


def get_or_create_person(db: Session, agent_id: str, external_id: str, email: Optional[str], name: Optional[str], timezone: Optional[str]) -> Person:
    canonical_external_id = canonical_person_external_id(external_id)
    matches = (
        db.query(Person)
        .filter(Person.agent_id == agent_id, Person.external_id.in_(person_id_aliases(external_id)))
        .all()
    )
    person = _preferred_person_match(matches, canonical_external_id)
    if not person:
        person = Person(agent_id=agent_id, external_id=canonical_external_id, email=email, name=name, timezone=timezone or "UTC")
        db.add(person)
        db.flush()
    else:
        updated = False
        if canonical_external_id and person.external_id != canonical_external_id:
            person.external_id = canonical_external_id
            updated = True
        if email and not person.email:
            person.email = email
            updated = True
        if name and not person.name:
            person.name = name
            updated = True
        if timezone and person.timezone == "UTC":
            person.timezone = timezone
            updated = True
        if updated:
            db.add(person)
    return person


def _set_preferred_channel(person: Person, channel: Channel) -> None:
    channel_value = channel.value
    if not person.preferred_channel:
        person.preferred_channel = channel_value


def get_or_create_relationship(db: Session, person: Person) -> Relationship:
    rel = (
        db.query(Relationship)
        .filter(Relationship.person_id == person.id, Relationship.active == True)
        .first()
    )
    if not rel:
        rel = Relationship(person_id=person.id, active=True, stage="onboarded")
        db.add(rel)
        db.flush()
    return rel


def latest_inbound_message_id(db: Session, rel: Relationship) -> Optional[str]:
    last_inbox = (
        db.query(Inbox)
        .filter(Inbox.relationship_id == rel.id)
        .order_by(desc(Inbox.processed_at))
        .first()
    )
    return last_inbox.message_id if last_inbox else None


def _update_relationship_metrics(db: Session, rel: Relationship, now: datetime) -> None:
    """Update computed metrics on the relationship."""
    rel.engagement_score = compute_engagement_score(rel, now)
    rel.churn_risk = compute_churn_risk(db, rel)

    # Check for lifecycle transitions
    new_stage = transition_stage(rel, now)
    if new_stage:
        try:
            apply_transition(rel, new_stage, now)
            logger.info("Relationship %s transitioned to %s", rel.id, new_stage)
        except ValueError:
            pass  # Invalid transition, skip


@router.post("/v1/relationships/events/inbound", response_model=InboundResponse)
def record_inbound(event: InboundEvent, db: Session = Depends(get_db)):
    # Idempotency by message_id
    if db.query(Inbox).filter(Inbox.message_id == event.message_id).first():
        rel = (
            db.query(Relationship)
            .join(Person, Relationship.person_id == Person.id)
            .filter(Person.agent_id == event.agent_id, Person.external_id.in_(person_id_aliases(event.person_id)))
            .first()
        )
        if not rel:
            raise HTTPException(status_code=404, detail="Relationship not found for duplicate message")
        return InboundResponse(
            status="duplicate",
            relationship_id=str(rel.id),
            intent_debt=rel.intent_debt,
            interaction_tension=rel.interaction_tension,
        )

    person = get_or_create_person(db, event.agent_id, event.person_id, event.email, event.name, event.timezone)
    rel = get_or_create_relationship(db, person)

    now = event.ts
    new_event = Event(
        relationship_id=rel.id,
        type="message_received",
        payload={"subject": event.subject, "snippet": event.snippet, "channel": event.channel.value},
        created_at=now,
    )
    db.add(new_event)
    db.flush()
    _set_preferred_channel(person, event.channel)

    react_to_event(rel, "message_received", now)
    # Make inbound debt immediately sweep-visible even if no explicit /decide call follows.
    rel.next_decision_at = now
    _update_relationship_metrics(db, rel, now)

    inbox_item = Inbox(
        relationship_id=rel.id,
        message_id=event.message_id,
        sender_external_id=event.person_id,
        sender_email=event.email,
        subject=event.subject,
        body=event.snippet,
        event_id=new_event.id,
        processed_at=now,
    )
    db.add(inbox_item)
    db.commit()

    return InboundResponse(
        status="ok",
        relationship_id=str(rel.id),
        intent_debt=rel.intent_debt,
        interaction_tension=rel.interaction_tension,
    )


@router.post("/v1/relationships/events/outbound", response_model=OutboundResponse)
def record_outbound(event: OutboundEvent, db: Session = Depends(get_db)):
    person = get_or_create_person(db, event.agent_id, event.person_id, event.email, event.name, event.timezone)
    rel = get_or_create_relationship(db, person)

    now = event.ts
    new_event = Event(
        relationship_id=rel.id,
        type="message_sent",
        payload={
            "action": event.action,
            "reason": event.reason,
            "parent_message_id": event.parent_message_id,
            "channel": event.channel.value,
        },
        created_at=now,
    )
    db.add(new_event)
    db.flush()
    _set_preferred_channel(person, event.channel)

    react_to_event(rel, "message_sent", now)
    rel.next_decision_at = compute_next_decision_at(rel, now, event.action)
    _update_relationship_metrics(db, rel, now)

    # Create outbox record for outcome tracking
    outbox = Outbox(
        relationship_id=rel.id,
        event_id=new_event.id,
        action=event.action,
        channel=event.channel.value,
        sent_at=now,
    )
    db.add(outbox)
    db.flush()

    db.commit()

    return OutboundResponse(
        status="ok",
        relationship_id=str(rel.id),
        intent_debt=rel.intent_debt,
        interaction_tension=rel.interaction_tension,
        outbox_id=outbox.id,
    )


@router.post("/v1/relationships/decide", response_model=DecideResponse)
def decide(event: DecideRequest, db: Session = Depends(get_db)):
    person = get_or_create_person(db, event.agent_id, event.person_id, None, None, None)
    rel = get_or_create_relationship(db, person)

    now = event.ts
    rel.interaction_tension = decay_tension(rel, now)
    _update_relationship_metrics(db, rel, now)
    decision = decide_action_with_context(rel, now)
    action = decision.action_type.value
    reason = ",".join(decision.reason_codes) if decision.reason_codes else action
    confidence = decision.confidence

    parent_message_id = None
    if action.startswith("SEND_"):
        parent_message_id = latest_inbound_message_id(db, rel)

    # Set next_decision_at
    rel.next_decision_at = decision.next_decision_at

    # Get golden hours for this person
    golden = get_golden_hours(db, person.id)
    golden_hours = [GoldenHour(day_of_week=d, hour_utc=h) for d, h in golden] if golden else None

    db.commit()

    return DecideResponse(
        action=action,
        reason=reason,
        confidence=confidence,
        parent_message_id=parent_message_id,
        relationship_stage=rel.stage,
        engagement_score=rel.engagement_score,
        churn_risk=rel.churn_risk,
        next_decision_at=rel.next_decision_at,
        golden_hours=golden_hours,
        reason_codes=decision.reason_codes,
        score_breakdown=decision.score_breakdown,
        policy_version=decision.policy_version,
        parameter_set_version=decision.parameter_set_version,
    )


@router.post("/v1/relationships/decide/batch", response_model=DecideBatchResponse)
def decide_batch(event: DecideBatchRequest, db: Session = Depends(get_db)):
    decisions: List[Decision] = []

    for person_id in event.person_ids:
        person = get_or_create_person(db, event.agent_id, person_id, None, None, None)
        rel = get_or_create_relationship(db, person)

        rel.interaction_tension = decay_tension(rel, event.ts)
        _update_relationship_metrics(db, rel, event.ts)
        decision = decide_action_with_context(rel, event.ts)
        action = decision.action_type.value
        reason = ",".join(decision.reason_codes) if decision.reason_codes else action
        confidence = decision.confidence

        parent_message_id = None
        if action.startswith("SEND_"):
            parent_message_id = latest_inbound_message_id(db, rel)

        decisions.append(Decision(
            person_id=person_id,
            action=action,
            reason=reason,
            confidence=confidence,
            parent_message_id=parent_message_id,
            reason_codes=decision.reason_codes,
            score_breakdown=decision.score_breakdown,
            policy_version=decision.policy_version,
            parameter_set_version=decision.parameter_set_version,
        ))

    db.commit()

    return DecideBatchResponse(decisions=decisions)


@router.post("/v1/relationships/sweep", response_model=SweepResponse)
def sweep(event: SweepRequest, db: Session = Depends(get_db)):
    """Find all relationships where next_decision_at <= now and return decisions."""
    now = event.ts

    # Find relationships ready for action
    ready_rels = (
        db.query(Relationship)
        .join(Person, Relationship.person_id == Person.id)
        .filter(
            Person.agent_id == event.agent_id,
            Relationship.active == True,
            Relationship.next_decision_at <= now,
        )
        .order_by(asc(Relationship.next_decision_at))
        .limit(event.max_results)
        .all()
    )

    decisions: List[SweepDecision] = []
    for rel in ready_rels:
        rel.interaction_tension = decay_tension(rel, now)
        _update_relationship_metrics(db, rel, now)
        decision = decide_action_with_context(rel, now)
        action = decision.action_type.value
        reason = ",".join(decision.reason_codes) if decision.reason_codes else action
        confidence = decision.confidence

        if action == "NO_ACTION":
            rel.next_decision_at = decision.next_decision_at
            continue

        parent_message_id = None
        if action.startswith("SEND_"):
            parent_message_id = latest_inbound_message_id(db, rel)

        # Schedule next check
        rel.next_decision_at = decision.next_decision_at

        decisions.append(SweepDecision(
            person_id=rel.person_id,
            relationship_id=rel.id,
            action=action,
            reason=reason,
            confidence=confidence,
            parent_message_id=parent_message_id,
            engagement_score=rel.engagement_score,
            churn_risk=rel.churn_risk,
            reason_codes=decision.reason_codes,
            score_breakdown=decision.score_breakdown,
            policy_version=decision.policy_version,
            parameter_set_version=decision.parameter_set_version,
        ))

    # Find the next sweep time
    next_rel = (
        db.query(Relationship)
        .join(Person, Relationship.person_id == Person.id)
        .filter(
            Person.agent_id == event.agent_id,
            Relationship.active == True,
            Relationship.next_decision_at > now,
        )
        .order_by(asc(Relationship.next_decision_at))
        .first()
    )
    next_sweep_at = next_rel.next_decision_at if next_rel else None

    db.commit()

    return SweepResponse(decisions=decisions, next_sweep_at=next_sweep_at)


@router.post("/v1/relationships/events/outcome", response_model=OutcomeResponse)
def record_event_outcome(event: OutcomeEvent, db: Session = Depends(get_db)):
    """Record the outcome of a sent message (delivered, opened, replied)."""
    outcome_data = {}
    if event.delivered is not None:
        outcome_data["delivered"] = event.delivered
    if event.opened_at:
        outcome_data["opened_at"] = event.opened_at
    if event.replied_at:
        outcome_data["replied_at"] = event.replied_at
        outcome_data["reply_sentiment"] = event.reply_sentiment
    if event.answered is not None:
        outcome_data["answered"] = event.answered
    if event.answered_at:
        outcome_data["answered_at"] = event.answered_at
    if event.voicemail is not None:
        outcome_data["voicemail"] = event.voicemail
    if event.appointment_created is not None:
        outcome_data["appointment_created"] = event.appointment_created
    if event.callback_requested is not None:
        outcome_data["callback_requested"] = event.callback_requested
    if event.follow_up_required is not None:
        outcome_data["follow_up_required"] = event.follow_up_required
    if event.follow_up_reason:
        outcome_data["follow_up_reason"] = event.follow_up_reason
    if event.negative_signal is not None:
        outcome_data["negative_signal"] = event.negative_signal

    record_outcome(db, event.outbox_id, outcome_data)
    db.commit()

    return OutcomeResponse(status="ok")
