import math
from datetime import datetime, timedelta
from typing import Dict, Optional, Tuple

from app.config import Settings, get_settings
from app.kernel.constraints import ConstraintGate
from app.kernel.contracts import (
    ActionType,
    DecisionResult,
    PressureClass,
)
from app.kernel.reducers import build_relationship_state
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


def _compute_next_decision_at(rel: Relationship, now: datetime, action: ActionType) -> datetime:
    if action == ActionType.wait:
        return now + timedelta(hours=4)
    if action in {
        ActionType.send_fulfillment,
        ActionType.send_nudge,
        ActionType.send_gentle_ping,
        ActionType.send_with_apology,
    }:
        cadence_days = getattr(rel, "cadence_days", 7.0) or 7.0
        return now + timedelta(days=cadence_days)
    return now + timedelta(days=1)


def _fallback_decision(rel: Relationship, now: datetime, reason_codes: Optional[list[str]] = None) -> DecisionResult:
    return DecisionResult(
        action_type=ActionType.no_action,
        pressure_class=PressureClass.none,
        reason_codes=reason_codes or ["NO_ALLOWED_ACTIONS"],
        score_breakdown={"base": 0.0},
        next_decision_at=_compute_next_decision_at(rel, now, ActionType.no_action),
        confidence=1.0,
    )


def decide_action_with_context(rel: Relationship, now: datetime, settings: Optional[Settings] = None) -> DecisionResult:
    """Decide action with explicit ConstraintGate + explainability metadata."""
    s = settings or get_settings()
    state = build_relationship_state(rel)
    gate = ConstraintGate(s).evaluate(state, now)
    allowed_actions = set(gate.allowed_actions)

    if not gate.is_actionable:
        return _fallback_decision(rel, now, [r.value for r in gate.reasons])

    if state.inferred.reply_debt > 0:
        if ActionType.internal_alert in allowed_actions and state.facts.dependency_blocked:
            return DecisionResult(
                action_type=ActionType.internal_alert,
                pressure_class=PressureClass.none,
                reason_codes=["DEBT_BLOCKED_DEPENDENCY", *[r.value for r in gate.reasons]],
                score_breakdown={"debt_priority": 1.0, "constraint_penalty": -1.0},
                next_decision_at=_compute_next_decision_at(rel, now, ActionType.internal_alert),
                confidence=0.9,
            )

        if ActionType.send_fulfillment in allowed_actions:
            if state.facts.debt_created_at:
                debt_days = get_days_passed(now, state.facts.debt_created_at)
                if debt_days > 3 and ActionType.send_with_apology in allowed_actions:
                    return DecisionResult(
                        action_type=ActionType.send_with_apology,
                        pressure_class=PressureClass.medium,
                        reason_codes=["OVERDUE_DEBT", *[r.value for r in gate.reasons]],
                        score_breakdown={"debt_priority": 1.0, "overdue_bonus": 0.2},
                        next_decision_at=_compute_next_decision_at(rel, now, ActionType.send_with_apology),
                        confidence=0.95,
                    )
            return DecisionResult(
                action_type=ActionType.send_fulfillment,
                pressure_class=PressureClass.low,
                reason_codes=["PAY_DEBT", *[r.value for r in gate.reasons]],
                score_breakdown={"debt_priority": 1.0},
                next_decision_at=_compute_next_decision_at(rel, now, ActionType.send_fulfillment),
                confidence=0.9,
            )
        return _fallback_decision(rel, now, [*["DEBT_PRESENT_BUT_BLOCKED"], *[r.value for r in gate.reasons]])

    stage = state.facts.stage or "onboarded"
    action_scores: Dict[ActionType, float] = {a: 0.0 for a in allowed_actions}

    # Base default to no-op
    if ActionType.no_action in action_scores:
        action_scores[ActionType.no_action] = 0.5
    if ActionType.wait in action_scores:
        action_scores[ActionType.wait] = 0.2
    if gate.reasons and ActionType.wait in action_scores:
        action_scores[ActionType.wait] += 0.4

    days_silent = get_days_passed(now, state.facts.last_contact_at)
    urgency = compute_urgency_score(rel, now)

    if stage == "churned" and ActionType.no_action in action_scores:
        action_scores[ActionType.no_action] += 0.9

    if state.inferred.reply_debt < 0:
        if days_silent <= 5 and ActionType.wait in action_scores:
            action_scores[ActionType.wait] += 0.7
        elif stage == "dormant":
            if days_silent > 30 and state.inferred.trust_score > 0.6 and ActionType.send_gentle_ping in action_scores:
                action_scores[ActionType.send_gentle_ping] += 0.6
            elif ActionType.wait in action_scores:
                action_scores[ActionType.wait] += 0.7
        else:
            if days_silent > 30 and state.inferred.trust_score > 0.6 and ActionType.send_nudge in action_scores:
                action_scores[ActionType.send_nudge] += 0.75
            elif days_silent > 12 and ActionType.send_gentle_ping in action_scores:
                action_scores[ActionType.send_gentle_ping] += 0.65

    if urgency > 0.7 and stage not in ("dormant", "churned") and ActionType.send_nudge in action_scores:
        action_scores[ActionType.send_nudge] = max(action_scores[ActionType.send_nudge], urgency)

    # Choose best action from allowed set.
    if not action_scores:
        return _fallback_decision(rel, now, [r.value for r in gate.reasons])

    winner = max(action_scores.items(), key=lambda kv: kv[1])[0]
    confidence = max(0.5, min(0.99, action_scores[winner]))

    pressure = PressureClass.none
    if winner in (ActionType.send_fulfillment, ActionType.send_gentle_ping):
        pressure = PressureClass.low
    elif winner in (ActionType.send_nudge, ActionType.send_with_apology):
        pressure = PressureClass.medium

    return DecisionResult(
        action_type=winner,
        pressure_class=pressure,
        reason_codes=[winner.value, *[r.value for r in gate.reasons]],
        score_breakdown={k.value: float(v) for k, v in action_scores.items()},
        next_decision_at=_compute_next_decision_at(rel, now, winner),
        confidence=confidence,
    )


def decide_action(rel: Relationship, now: datetime, settings: Optional[Settings] = None) -> Tuple[str, str, float]:
    """Backwards-compatible API returning (action, reason, confidence)."""
    decision = decide_action_with_context(rel, now, settings=settings)
    reason = ",".join(decision.reason_codes) if decision.reason_codes else decision.action_type.value
    return decision.action_type.value, reason, decision.confidence
