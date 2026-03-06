import math
from typing import Optional, Tuple
from datetime import datetime

from app.config import Settings, get_settings
from app.models.core import Relationship


def _strip_tz(dt: datetime) -> datetime:
    """Strip timezone info for safe subtraction."""
    return dt.replace(tzinfo=None) if dt.tzinfo else dt


def get_days_passed(now: datetime, last_contact: datetime) -> float:
    return (_strip_tz(now) - _strip_tz(last_contact)).total_seconds() / 86400.0


def decay_tension(rel: Relationship, now: datetime, settings: Optional[Settings] = None) -> float:
    s = settings or get_settings()
    days = get_days_passed(now, rel.last_contact_at)
    if days <= 0:
        return rel.interaction_tension
    return rel.interaction_tension * math.exp(-s.lambda_decay * days)


def react_to_event(rel: Relationship, event_type: str, now: datetime, settings: Optional[Settings] = None) -> None:
    s = settings or get_settings()
    if event_type == "message_received":
        rel.interaction_tension = 0.0
        rel.intent_debt = 1
        rel.debt_created_at = now
        rel.last_contact_at = now
        rel.last_inbound_at = now
        rel.trust_score = min(1.0, rel.trust_score + s.trust_increment_inbound)
    elif event_type == "message_sent":
        rel.interaction_tension = min(1.0, rel.interaction_tension + s.tension_increment_outbound)
        rel.intent_debt = 0
        rel.debt_created_at = None
        rel.last_contact_at = now
        rel.last_outbound_at = now
        rel.trust_score = min(1.0, rel.trust_score + s.trust_increment_outbound)


def compute_engagement_score(rel: Relationship, now: datetime) -> float:
    """Compute composite engagement score (0-100) from multiple factors."""
    # Recency factor: exponential decay from last contact
    days_since = get_days_passed(now, rel.last_contact_at)
    recency = math.exp(-0.05 * days_since) * 100.0

    # Trust factor: direct mapping
    trust = rel.trust_score * 100.0

    # Activity factor: based on whether there's been recent bidirectional contact
    has_inbound = rel.last_inbound_at is not None
    has_outbound = rel.last_outbound_at is not None
    if has_inbound and has_outbound:
        activity = 80.0
    elif has_inbound or has_outbound:
        activity = 40.0
    else:
        activity = 10.0

    # Debt penalty: having unresolved debt reduces engagement
    debt_penalty = 0.0
    if rel.intent_debt > 0 and rel.debt_created_at:
        debt_days = get_days_passed(now, rel.debt_created_at)
        debt_penalty = min(30.0, debt_days * 5.0)

    score = (recency * 0.3 + trust * 0.3 + activity * 0.2 + (100.0 - debt_penalty) * 0.2)
    return max(0.0, min(100.0, score))


def compute_urgency_score(rel: Relationship, now: datetime) -> float:
    """Compute urgency score (0-1) for how urgently we should act."""
    urgency = 0.0

    # Debt urgency: ramps to 1.0 over 3 days
    if rel.intent_debt > 0 and rel.debt_created_at:
        debt_days = get_days_passed(now, rel.debt_created_at)
        urgency = max(urgency, min(1.0, debt_days / 3.0))

    # Silence urgency: based on cadence_days
    cadence = getattr(rel, "cadence_days", 7.0) or 7.0
    days_silent = get_days_passed(now, rel.last_contact_at)
    if days_silent > cadence:
        silence_urgency = min(1.0, (days_silent - cadence) / cadence)
        urgency = max(urgency, silence_urgency * 0.7)

    # Churn risk amplifier
    churn = getattr(rel, "churn_risk", 0.0) or 0.0
    if churn > 0.5:
        urgency = min(1.0, urgency * (1.0 + churn))

    return urgency


def decide_action(rel: Relationship, now: datetime, settings: Optional[Settings] = None) -> Tuple[str, str, float]:
    """Decide what action to take. Returns (action, reason, confidence)."""
    s = settings or get_settings()

    # Hard blockers
    if rel.intent_debt > 0:
        if rel.dependency_blocked:
            return "INTERNAL_ALERT", "Blocked by dependency", 0.9
        if rel.debt_created_at:
            debt_days = get_days_passed(now, rel.debt_created_at)
            if debt_days > 3:
                return "SEND_WITH_APOLOGY", f"Overdue {debt_days:.1f} days", 0.95
        return "SEND_FULFILLMENT", "Paying debt", 0.9

    if rel.last_outbound_at:
        hours_since = (_strip_tz(now) - _strip_tz(rel.last_outbound_at)).total_seconds() / 3600.0
        if hours_since < s.min_cooldown_hours and rel.interaction_tension > 0.2:
            return "WAIT", "Cadence cooldown", 0.8

    if rel.interaction_tension > s.max_tension:
        return "WAIT", "Tension high", 0.85

    # Stage-aware decisions
    stage = getattr(rel, "stage", "onboarded") or "onboarded"

    if rel.intent_debt < 0:
        days_silent = get_days_passed(now, rel.last_contact_at)
        if days_silent <= 5:
            return "WAIT", "Standard window", 0.7

        # Stage-aware silence handling (dormancy transitions handled by lifecycle.py)
        if stage == "dormant":
            if days_silent > 30 and rel.trust_score > 0.6:
                return "SEND_GENTLE_PING", "Dormant re-engagement", 0.6
            return "WAIT", "Dormant, no action", 0.7

        if stage == "churned":
            return "NO_ACTION", "Churned", 0.9

        if days_silent > 30 and rel.trust_score > 0.6:
            return "SEND_NUDGE", "Long silence, high trust", 0.75
        if days_silent > 12:
            return "SEND_GENTLE_PING", "Check-in", 0.65

    # Proactive outreach based on urgency
    urgency = compute_urgency_score(rel, now)
    if urgency > 0.7 and stage not in ("dormant", "churned"):
        return "SEND_NUDGE", f"Urgency {urgency:.2f}", urgency

    return "NO_ACTION", "Idle", 0.5
