from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional

from pydantic import BaseModel, Field


class Channel(str, Enum):
    email = "email"
    sms = "sms"
    whatsapp = "whatsapp"
    voice_call = "voice_call"
    telegram = "telegram"
    other = "other"


class Direction(str, Enum):
    inbound = "INBOUND"
    outbound = "OUTBOUND"


class EventType(str, Enum):
    message_sent = "MESSAGE_SENT"
    message_received = "MESSAGE_RECEIVED"
    delivered = "DELIVERED"
    replied = "REPLIED"
    opt_out = "OPT_OUT"
    bounce = "BOUNCE"


class ActionType(str, Enum):
    send_fulfillment = "SEND_FULFILLMENT"
    send_nudge = "SEND_NUDGE"
    send_gentle_ping = "SEND_GENTLE_PING"
    send_with_apology = "SEND_WITH_APOLOGY"
    wait = "WAIT"
    no_action = "NO_ACTION"
    internal_alert = "INTERNAL_ALERT"


class PressureClass(str, Enum):
    low = "LOW"
    medium = "MEDIUM"
    high = "HIGH"
    none = "NONE"


class ConstraintReason(str, Enum):
    inactive_relationship = "INACTIVE_RELATIONSHIP"
    dependency_blocked = "DEPENDENCY_BLOCKED"
    owner_excluded = "OWNER_EXCLUDED"
    hard_cooldown_active = "HARD_COOLDOWN_ACTIVE"
    hard_tension_block = "HARD_TENSION_BLOCK"


class ObservedEvent(BaseModel):
    event_id: str = Field(..., min_length=1)
    contact_id: str = Field(..., min_length=1)
    timestamp: datetime
    channel: Channel
    direction: Direction
    event_type: EventType
    delivery_status: Optional[str] = None
    reply_to_event_id: Optional[str] = None
    timezone_context: str = "UTC"
    business_context: Optional[str] = None
    message_intensity: Optional[PressureClass] = None
    metadata: Dict[str, str] = Field(default_factory=dict)


class RelationshipFacts(BaseModel):
    last_contact_at: datetime
    last_inbound_at: Optional[datetime] = None
    last_outbound_at: Optional[datetime] = None
    debt_created_at: Optional[datetime] = None
    channel_permissions: List[Channel] = Field(default_factory=lambda: [Channel.email])
    contact_timezone: str = "UTC"
    active: bool = True
    dependency_blocked: bool = False
    owner_excluded: bool = False
    stage: str = "onboarded"


class RelationshipInferred(BaseModel):
    trust_score: float = Field(0.5, ge=0.0, le=1.0)
    tension_score: float = Field(0.0, ge=0.0, le=1.0)
    reply_debt: int = 0
    engagement_score: float = Field(50.0, ge=0.0, le=100.0)
    churn_risk: float = Field(0.0, ge=0.0, le=1.0)


class RelationshipState(BaseModel):
    relationship_id: str = Field(..., min_length=1)
    person_id: Optional[str] = None
    facts: RelationshipFacts
    inferred: RelationshipInferred


class ConstraintResult(BaseModel):
    allowed_actions: List[ActionType]
    blocked_actions: List[ActionType]
    reasons: List[ConstraintReason] = Field(default_factory=list)

    @property
    def is_actionable(self) -> bool:
        return len(self.allowed_actions) > 0


class DecisionResult(BaseModel):
    action_type: ActionType
    pressure_class: PressureClass = PressureClass.none
    reason_codes: List[str] = Field(default_factory=list)
    score_breakdown: Dict[str, float] = Field(default_factory=dict)
    next_decision_at: datetime
    policy_version: str = "v1.1"
    parameter_set_version: str = "baseline-2026-03-08"
    confidence: float = Field(0.5, ge=0.0, le=1.0)
