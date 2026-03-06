from datetime import datetime
from typing import Optional

from app.models.core import Relationship
from app.models.physics import get_days_passed

VALID_TRANSITIONS = {
    "onboarded":       ["warm", "dormant"],
    "warm":            ["engaged", "dormant"],
    "engaged":         ["value_delivered", "warm", "dormant"],
    "value_delivered":  ["engaged", "dormant"],
    "dormant":         ["re_engaged", "churned"],
    "re_engaged":      ["warm", "engaged", "dormant"],
    "churned":         ["re_engaged"],
}


def transition_stage(rel: Relationship, now: datetime) -> Optional[str]:
    """Evaluate whether the relationship should transition to a new stage.
    Returns the new stage name or None if no transition needed."""
    current = rel.stage
    days_silent = get_days_passed(now, rel.last_contact_at)

    # Decay to dormant on silence (checked first — silence overrides trust)
    if current in ("warm", "engaged", "value_delivered") and days_silent > 30:
        return "dormant"

    # Forward progression based on trust
    if current == "onboarded" and rel.trust_score >= 0.3:
        return "warm"
    if current == "warm" and rel.trust_score >= 0.5:
        return "engaged"
    if current == "engaged" and rel.intent_debt == 0 and rel.trust_score >= 0.7:
        return "value_delivered"

    # Dormant to churned
    if current == "dormant" and days_silent > 90:
        return "churned"

    # Re-engagement on fresh inbound
    if current in ("dormant", "churned"):
        if rel.last_inbound_at:
            inbound_days = get_days_passed(now, rel.last_inbound_at)
            if inbound_days < 1:
                return "re_engaged"

    return None


def apply_transition(rel: Relationship, new_stage: str, now: datetime) -> None:
    """Apply a stage transition after validating it."""
    valid = VALID_TRANSITIONS.get(rel.stage, [])
    if new_stage not in valid:
        raise ValueError(f"Invalid transition: {rel.stage} -> {new_stage}")
    rel.stage = new_stage
