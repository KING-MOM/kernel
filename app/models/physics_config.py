from typing import Optional
from sqlalchemy import String, Float
from sqlalchemy.orm import Mapped, mapped_column, Session

from app.models.core import new_id
from app.db.database import Base
from app.config import get_settings


class PhysicsConfig(Base):
    __tablename__ = "physics_configs"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    agent_id: Mapped[str] = mapped_column(String, unique=True, index=True)

    lambda_decay: Mapped[float] = mapped_column(Float, default=0.15)
    max_tension: Mapped[float] = mapped_column(Float, default=0.85)
    min_cooldown_hours: Mapped[float] = mapped_column(Float, default=24.0)
    trust_increment_inbound: Mapped[float] = mapped_column(Float, default=0.1)
    trust_increment_outbound: Mapped[float] = mapped_column(Float, default=0.05)
    tension_increment_outbound: Mapped[float] = mapped_column(Float, default=0.4)

    # Scoring weights for engagement computation
    engagement_weight: Mapped[float] = mapped_column(Float, default=0.3)
    reciprocity_weight: Mapped[float] = mapped_column(Float, default=0.3)
    recency_weight: Mapped[float] = mapped_column(Float, default=0.2)
    trust_weight: Mapped[float] = mapped_column(Float, default=0.2)


def get_physics_config(db: Session, agent_id: str) -> PhysicsConfig:
    """Load agent-specific config or return defaults from Settings."""
    config = (
        db.query(PhysicsConfig)
        .filter(PhysicsConfig.agent_id == agent_id)
        .first()
    )
    if config:
        return config

    # Return a detached object with defaults from settings
    s = get_settings()
    return PhysicsConfig(
        agent_id=agent_id,
        lambda_decay=s.lambda_decay,
        max_tension=s.max_tension,
        min_cooldown_hours=s.min_cooldown_hours,
        trust_increment_inbound=s.trust_increment_inbound,
        trust_increment_outbound=s.trust_increment_outbound,
        tension_increment_outbound=s.tension_increment_outbound,
    )
