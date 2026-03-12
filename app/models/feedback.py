from typing import Optional, Dict, Any
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.models.core import Outbox, Relationship
from app.models.temporal import record_response_timing
from app.models.physics import _strip_tz


def _json_safe_value(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    return value


def record_outcome(db: Session, outbox_id: str, outcome: Dict[str, Any]) -> None:
    """Update an outbox record with delivery/reply outcome and adjust relationship metrics."""
    outbox = db.query(Outbox).filter(Outbox.id == outbox_id).first()
    if not outbox:
        return

    if "delivered" in outcome:
        outbox.delivered = outcome["delivered"]
    if "opened_at" in outcome and outcome["opened_at"]:
        outbox.opened_at = outcome["opened_at"]
    extra_outcome = {
        key: _json_safe_value(value)
        for key, value in outcome.items()
        if key
        not in {
            "delivered",
            "opened_at",
            "replied_at",
            "reply_sentiment",
        }
        and value is not None
    }
    if extra_outcome:
        merged = dict(outbox.outcome_payload or {})
        merged.update(extra_outcome)
        outbox.outcome_payload = merged
    if "replied_at" in outcome and outcome["replied_at"]:
        outbox.replied_at = outcome["replied_at"]
        outbox.reply_sentiment = outcome.get("reply_sentiment")

        # Update temporal data
        rel = db.query(Relationship).filter(Relationship.id == outbox.relationship_id).first()
        if rel:
            record_response_timing(db, rel.person_id, outbox.sent_at, outbox.replied_at)

            # Adjust engagement based on response speed
            sent_naive = _strip_tz(outbox.sent_at)
            replied_naive = _strip_tz(outbox.replied_at)
            response_hours = (replied_naive - sent_naive).total_seconds() / 3600.0

            if response_hours < 4:
                rel.trust_score = min(1.0, rel.trust_score + 0.05)
                rel.engagement_score = min(100.0, rel.engagement_score + 5.0)
            elif response_hours > 48:
                rel.engagement_score = max(0.0, rel.engagement_score - 3.0)
    else:
        rel = db.query(Relationship).filter(Relationship.id == outbox.relationship_id).first()

    if not rel:
        return

    effective_ts = (
        outcome.get("answered_at")
        or outcome.get("replied_at")
        or outcome.get("opened_at")
        or datetime.now(timezone.utc)
    )

    if outcome.get("answered") is True:
        rel.trust_score = min(1.0, rel.trust_score + 0.03)
        rel.engagement_score = min(100.0, rel.engagement_score + 3.0)

    if outcome.get("appointment_created") is True:
        rel.trust_score = min(1.0, rel.trust_score + 0.08)
        rel.engagement_score = min(100.0, rel.engagement_score + 8.0)
        rel.intent_debt = 0
        rel.debt_created_at = None

    if outcome.get("follow_up_required") is True or outcome.get("callback_requested") is True:
        rel.intent_debt = 1
        rel.debt_created_at = effective_ts
        rel.next_decision_at = effective_ts

    if outcome.get("negative_signal") is True:
        rel.interaction_tension = min(1.0, rel.interaction_tension + 0.25)
        rel.engagement_score = max(0.0, rel.engagement_score - 5.0)

    if outcome.get("voicemail") is True and outcome.get("answered") is not True:
        rel.engagement_score = max(0.0, rel.engagement_score - 1.0)


def compute_churn_risk(db: Session, rel: Relationship) -> float:
    """Compute churn risk from recent outbox outcomes (last 30 days)."""
    cutoff = datetime.utcnow() - timedelta(days=30)
    recent_outbox = (
        db.query(Outbox)
        .filter(
            Outbox.relationship_id == rel.id,
            Outbox.sent_at > cutoff,
        )
        .all()
    )

    if not recent_outbox:
        return 0.0

    replied = sum(1 for o in recent_outbox if o.replied_at)
    ratio = replied / len(recent_outbox)
    return max(0.0, 1.0 - ratio)
