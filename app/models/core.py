import uuid
from datetime import datetime
from typing import Optional, List
from sqlalchemy import String, Float, Integer, Boolean, DateTime, ForeignKey, JSON, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.database import Base


def new_id() -> str:
    return str(uuid.uuid4())


class Person(Base):
    __tablename__ = "persons"
    __table_args__ = (UniqueConstraint("agent_id", "external_id", name="uq_person_agent_external"),)

    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    agent_id: Mapped[str] = mapped_column(String, index=True)
    external_id: Mapped[str] = mapped_column(String, index=True)
    email: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    name: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    timezone: Mapped[str] = mapped_column(String, default="UTC")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    # Phase 2: enriched profile
    role: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    communication_style: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    preferred_channel: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    goals: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    relationships: Mapped[List["Relationship"]] = relationship(back_populates="person")


class Relationship(Base):
    __tablename__ = "relationships"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    person_id: Mapped[str] = mapped_column(ForeignKey("persons.id"))

    stage: Mapped[str] = mapped_column(String, default="onboarded")
    trust_score: Mapped[float] = mapped_column(Float, default=0.5)
    interaction_tension: Mapped[float] = mapped_column(Float, default=0.0)
    intent_debt: Mapped[int] = mapped_column(Integer, default=0)

    last_contact_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    last_inbound_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    last_outbound_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    debt_created_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    dependency_blocked: Mapped[bool] = mapped_column(Boolean, default=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True)

    # Phase 2: enriched relationship metrics
    engagement_score: Mapped[float] = mapped_column(Float, default=50.0)
    churn_risk: Mapped[float] = mapped_column(Float, default=0.0)
    relationship_type: Mapped[str] = mapped_column(String, default="general")
    priority: Mapped[int] = mapped_column(Integer, default=5)
    cadence_days: Mapped[float] = mapped_column(Float, default=7.0)
    next_decision_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    warmth_window_expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    rapport_score: Mapped[float] = mapped_column(Float, default=0.0)

    person: Mapped["Person"] = relationship(back_populates="relationships")
    events: Mapped[List["Event"]] = relationship(back_populates="relationship")


class Event(Base):
    __tablename__ = "events"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    relationship_id: Mapped[str] = mapped_column(ForeignKey("relationships.id"))

    type: Mapped[str] = mapped_column(String)
    payload: Mapped[dict] = mapped_column(JSON, default={})
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    relationship: Mapped["Relationship"] = relationship(back_populates="events")


class Inbox(Base):
    __tablename__ = "inbox"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    relationship_id: Mapped[str] = mapped_column(ForeignKey("relationships.id"))

    message_id: Mapped[str] = mapped_column(String, unique=True, index=True)
    sender_external_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    sender_email: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    subject: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    body: Mapped[Optional[str]] = mapped_column(String, nullable=True)

    processed_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    event_id: Mapped[Optional[str]] = mapped_column(ForeignKey("events.id"), nullable=True)


class Outbox(Base):
    __tablename__ = "outbox"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    relationship_id: Mapped[str] = mapped_column(ForeignKey("relationships.id"))
    event_id: Mapped[Optional[str]] = mapped_column(ForeignKey("events.id"), nullable=True)

    action: Mapped[str] = mapped_column(String)
    channel: Mapped[str] = mapped_column(String, default="email")
    sent_at: Mapped[datetime] = mapped_column(DateTime)

    # Outcome tracking
    delivered: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    opened_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    replied_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    reply_sentiment: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    outcome_payload: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    intent_type: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    rapport_eligible: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)


class ContactWindow(Base):
    """Tracks per-person optimal contact times learned from response patterns."""
    __tablename__ = "contact_windows"
    __table_args__ = (UniqueConstraint("person_id", "day_of_week", "hour_utc", name="uq_contact_window"),)

    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    person_id: Mapped[str] = mapped_column(ForeignKey("persons.id"))

    day_of_week: Mapped[int] = mapped_column(Integer)  # 0=Monday
    hour_utc: Mapped[int] = mapped_column(Integer)      # 0-23
    response_count: Mapped[int] = mapped_column(Integer, default=0)
    avg_response_time_hours: Mapped[float] = mapped_column(Float, default=0.0)


class ConversationThread(Base):
    __tablename__ = "conversation_threads"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    relationship_id: Mapped[str] = mapped_column(ForeignKey("relationships.id"))
    subject: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime)
    last_message_at: Mapped[datetime] = mapped_column(DateTime)
    message_count: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String, default="active")  # active, resolved, stale


class WebhookConfig(Base):
    __tablename__ = "webhook_configs"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    agent_id: Mapped[str] = mapped_column(String, index=True)
    url: Mapped[str] = mapped_column(String)
    events: Mapped[dict] = mapped_column(JSON, default=["decision_ready"])
    secret: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
