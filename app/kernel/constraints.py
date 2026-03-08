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
]

ALL_ACTIONS: List[ActionType] = [
    ActionType.send_fulfillment,
    ActionType.send_nudge,
    ActionType.send_gentle_ping,
    ActionType.send_with_apology,
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

        if state.facts.dependency_blocked:
            reasons.append(ConstraintReason.dependency_blocked)
            allowed = [a for a in allowed if a not in SEND_ACTIONS]
            if ActionType.internal_alert not in allowed:
                allowed.append(ActionType.internal_alert)

        if state.facts.last_outbound_at is not None:
            hours_since = (_strip_tz(now) - _strip_tz(state.facts.last_outbound_at)).total_seconds() / 3600.0
            if hours_since < self.settings.min_cooldown_hours:
                reasons.append(ConstraintReason.hard_cooldown_active)
                allowed = [a for a in allowed if a not in SEND_ACTIONS]

        if state.inferred.tension_score > self.settings.max_tension:
            reasons.append(ConstraintReason.hard_tension_block)
            allowed = [a for a in allowed if a not in SEND_ACTIONS]

        blocked = [a for a in ALL_ACTIONS if a not in allowed]
        return ConstraintResult(allowed_actions=allowed, blocked_actions=blocked, reasons=reasons)
