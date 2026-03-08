from __future__ import annotations

import hashlib
import json
from typing import Any, Dict

from app.kernel.contracts import RelationshipFacts, RelationshipInferred, RelationshipState
from app.models.core import Relationship


def build_relationship_state(rel: Relationship) -> RelationshipState:
    """Adapter from DB relationship model to strict decision-state contract."""
    return RelationshipState(
        relationship_id=str(rel.id or "unknown"),
        person_id=str(rel.person_id) if rel.person_id else None,
        facts=RelationshipFacts(
            last_contact_at=rel.last_contact_at,
            last_inbound_at=rel.last_inbound_at,
            last_outbound_at=rel.last_outbound_at,
            debt_created_at=rel.debt_created_at,
            active=bool(rel.active),
            dependency_blocked=bool(rel.dependency_blocked),
            stage=rel.stage or "onboarded",
        ),
        inferred=RelationshipInferred(
            trust_score=rel.trust_score,
            tension_score=rel.interaction_tension,
            reply_debt=rel.intent_debt,
            engagement_score=getattr(rel, "engagement_score", 50.0) or 50.0,
            churn_risk=getattr(rel, "churn_risk", 0.0) or 0.0,
        ),
    )


def snapshot_state(state: RelationshipState) -> Dict[str, Any]:
    """Stable, JSON-serializable state payload for replay/debugging."""
    return state.model_dump(mode="json")


def snapshot_hash(state: RelationshipState) -> str:
    """Deterministic hash of the state snapshot consumed by policy."""
    payload = json.dumps(snapshot_state(state), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
