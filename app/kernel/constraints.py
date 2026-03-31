from __future__ import annotations

from datetime import datetime
from typing import List

from app.config import Settings, get_settings
from app.kernel.contracts import ActionType, ConstraintReason, ConstraintResult, RelationshipState


def _strip_tz(dt: datetime) -> datetime:
    return dt.replace(tzinfo=None) if dt.tzinfo else dt


SEND_ACTIONS: List[ActionType] = [
    ActionType.send_fulfillment,
    ActionType.send_nudge,
    ActionType.send_gentle_ping,
    ActionType.send_with_apology,
    ActionType.send_warm_checkin,
    ActionType.send_value_drop,
    ActionType.send_contextual_followup,
]

RAPPORT_ACTIONS: List[ActionType] = [
    ActionType.send_warm_checkin,
    ActionType.send_value_drop,
    ActionType.send_contextual_followup,
]

ALL_ACTIONS: List[ActionType] = [
    ActionType.send_fulfillment,
    ActionType.send_nudge,
    ActionType.send_gentle_ping,
    ActionType.send_with_apology,
    ActionType.send_warm_checkin,
    ActionType.send_value_drop,
    ActionType.send_contextual_followup,
    ActionType.wait,
    ActionType.no_action,
    ActionType.internal_alert,
]


class ConstraintGate:
    """Hard-constraint gate. Blocks illegal actions before policy scoring."""

    def __init__(self, settings: Settings | None = None):
        self.settings = settings or get_settings()

    def evaluate(self, state: RelationshipState, now: datetime) -> ConstraintResult:
        allowed = list(ALL_ACTIONS)
        reasons: List[ConstraintReason] = []

        if not state.facts.active:
            reasons.append(ConstraintReason.inactive_relationship)
            allowed = [ActionType.no_action]

        if state.facts.owner_excluded:
            reasons.append(ConstraintReason.owner_excluded)
            allowed = [ActionType.no_action]

        if state.facts.dependency_blocked:
            reasons.append(ConstraintReason.dependency_blocked)
            allowed = [a for a in allowed if a not in SEND_ACTIONS]
            if ActionType.internal_alert not in allowed:
                allowed.append(ActionType.internal_alert)

        in_warmth_window = (
            state.facts.warmth_window_expires_at is not None
            and _strip_tz(now) < _strip_tz(state.facts.warmth_window_expires_at)
        )

        if state.facts.last_outbound_at is not None:
            hours_since = (_strip_tz(now) - _strip_tz(state.facts.last_outbound_at)).total_seconds() / 3600.0
            if hours_since < self.settings.min_cooldown_hours:
                reasons.append(ConstraintReason.hard_cooldown_active)
                allowed = [a for a in allowed if a not in SEND_ACTIONS]
                if self._debt_override_allows_fulfillment(state):
                    allowed.append(ActionType.send_fulfillment)

        if state.inferred.tension_score > self.settings.max_tension:
            reasons.append(ConstraintReason.hard_tension_block)
            allowed = [a for a in allowed if a not in SEND_ACTIONS]

        # Soft rapport block: rapport actions require low tension
        # Relaxed slightly if inside warmth window (positive recent signal)
        rapport_tension_limit = self.settings.rapport_tension_threshold
        if in_warmth_window:
            rapport_tension_limit = min(0.65, rapport_tension_limit + 0.15)
        if state.inferred.tension_score > rapport_tension_limit:
            allowed = [a for a in allowed if a not in RAPPORT_ACTIONS]

        blocked = [a for a in ALL_ACTIONS if a not in allowed]
        return ConstraintResult(allowed_actions=allowed, blocked_actions=blocked, reasons=reasons)

    def _debt_override_allows_fulfillment(self, state: RelationshipState) -> bool:
        return (
            state.inferred.reply_debt > 0
            and state.inferred.trust_score >= self.settings.debt_override_min_trust
            and state.inferred.engagement_score >= self.settings.debt_override_min_engagement
            and state.inferred.tension_score < self.settings.debt_override_max_tension
        )
