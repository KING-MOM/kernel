from typing import Optional
from functools import lru_cache
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "sqlite:///./kernel.db"
    kernel_api_key: Optional[str] = None
    log_level: str = "INFO"
    log_format: str = "json"
    version: str = "0.2.0"
    policy_version: str = "v1.1"
    parameter_set_version: str = "baseline-2026-03-08"

    # Physics defaults (overridable per-agent via PhysicsConfig in Phase 2)
    lambda_decay: float = 0.15
    max_tension: float = 0.85
    min_cooldown_hours: float = 24.0
    debt_override_min_trust: float = 0.8
    debt_override_min_engagement: float = 85.0
    debt_override_max_tension: float = 0.5
    trust_increment_inbound: float = 0.1
    trust_increment_outbound: float = 0.05
    tension_increment_outbound: float = 0.4

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


@lru_cache
def get_settings() -> Settings:
    return Settings()
