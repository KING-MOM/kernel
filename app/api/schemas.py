from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field
from app.kernel.contracts import Channel


class InboundEvent(BaseModel):
    agent_id: str = Field(..., min_length=1)
    person_id: str = Field(..., min_length=1)
    email: Optional[str] = None
    name: Optional[str] = None
    timezone: Optional[str] = None
    message_id: str = Field(..., min_length=1)
    subject: Optional[str] = None
    snippet: Optional[str] = None
    channel: Channel = Channel.email
    ts: datetime


class OutboundEvent(BaseModel):
    agent_id: str = Field(..., min_length=1)
    person_id: str = Field(..., min_length=1)
    email: Optional[str] = None
    name: Optional[str] = None
    timezone: Optional[str] = None
    message_id: str = Field(..., min_length=1)
    action: str = Field(..., min_length=1)
    reason: str = Field(..., min_length=1)
    parent_message_id: Optional[str] = None
    channel: Channel = Channel.email
    ts: datetime
    intent_type: Optional[str] = None
    rapport_eligible: bool = False


class DecideRequest(BaseModel):
    agent_id: str = Field(..., min_length=1)
    person_id: str = Field(..., min_length=1)
    ts: datetime


class DecideBatchRequest(BaseModel):
    agent_id: str = Field(..., min_length=1)
    person_ids: List[str]
    ts: datetime


class SweepRequest(BaseModel):
    agent_id: str = Field(..., min_length=1)
    ts: datetime
    max_results: int = 50


class OutcomeEvent(BaseModel):
    outbox_id: str = Field(..., min_length=1)
    delivered: Optional[bool] = None
    opened_at: Optional[datetime] = None
    replied_at: Optional[datetime] = None
    reply_sentiment: Optional[float] = None
    answered: Optional[bool] = None
    answered_at: Optional[datetime] = None
    voicemail: Optional[bool] = None
    appointment_created: Optional[bool] = None
    callback_requested: Optional[bool] = None
    follow_up_required: Optional[bool] = None
    follow_up_reason: Optional[str] = None
    negative_signal: Optional[bool] = None


# Responses

class InboundResponse(BaseModel):
    status: str
    relationship_id: str
    intent_debt: int
    interaction_tension: float


class OutboundResponse(BaseModel):
    status: str
    relationship_id: str
    intent_debt: int
    interaction_tension: float
    outbox_id: Optional[str] = None


class GoldenHour(BaseModel):
    day_of_week: int
    hour_utc: int


class DecideResponse(BaseModel):
    action: str
    reason: str
    confidence: float = 0.5
    parent_message_id: Optional[str] = None
    relationship_stage: Optional[str] = None
    engagement_score: Optional[float] = None
    churn_risk: Optional[float] = None
    next_decision_at: Optional[datetime] = None
    golden_hours: Optional[List[GoldenHour]] = None
    reason_codes: Optional[List[str]] = None
    score_breakdown: Optional[Dict[str, float]] = None
    policy_version: Optional[str] = None
    parameter_set_version: Optional[str] = None
    appropriateness_score: Optional[float] = None


class Decision(BaseModel):
    person_id: str
    action: str
    reason: str
    confidence: float = 0.5
    parent_message_id: Optional[str] = None
    reason_codes: Optional[List[str]] = None
    score_breakdown: Optional[Dict[str, float]] = None
    policy_version: Optional[str] = None
    parameter_set_version: Optional[str] = None


class DecideBatchResponse(BaseModel):
    decisions: List[Decision]


class SweepDecision(BaseModel):
    person_id: str
    relationship_id: str
    action: str
    reason: str
    confidence: float
    parent_message_id: Optional[str] = None
    engagement_score: float
    churn_risk: float
    reason_codes: Optional[List[str]] = None
    score_breakdown: Optional[Dict[str, float]] = None
    policy_version: Optional[str] = None
    parameter_set_version: Optional[str] = None
    appropriateness_score: Optional[float] = None


class SweepResponse(BaseModel):
    decisions: List[SweepDecision]
    next_sweep_at: Optional[datetime] = None


class OutcomeResponse(BaseModel):
    status: str


# Read endpoint schemas

class PersonResponse(BaseModel):
    id: str
    agent_id: str
    external_id: str
    email: Optional[str] = None
    name: Optional[str] = None
    timezone: str = "UTC"
    role: Optional[str] = None
    communication_style: Optional[str] = None
    preferred_channel: Optional[str] = None

    model_config = {"from_attributes": True}


class RelationshipResponse(BaseModel):
    id: str
    person_id: str
    stage: str
    trust_score: float
    interaction_tension: float
    intent_debt: int
    engagement_score: float
    churn_risk: float
    relationship_type: str
    priority: int
    cadence_days: float
    last_contact_at: Optional[datetime] = None
    last_inbound_at: Optional[datetime] = None
    last_outbound_at: Optional[datetime] = None
    next_decision_at: Optional[datetime] = None
    active: bool
    rapport_score: Optional[float] = None
    warmth_window_expires_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class EventResponse(BaseModel):
    id: str
    type: str
    payload: Dict[str, Any] = {}
    created_at: datetime

    model_config = {"from_attributes": True}


class StatsResponse(BaseModel):
    total_persons: int
    active_relationships: int
    stage_breakdown: Dict[str, int]
    avg_engagement_score: float
    avg_churn_risk: float
    pending_decisions: int


class PaginatedResponse(BaseModel):
    items: List[Any]
    total: int
    skip: int
    limit: int
