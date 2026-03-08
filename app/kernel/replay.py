from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional

from app.config import Settings, get_settings
from app.kernel.constraints import ConstraintGate
from app.kernel.contracts import ActionType, DecisionResult
from app.kernel.reducers import build_relationship_state, snapshot_hash, snapshot_state
from app.kernel.time_math import build_temporal_context, temporal_context_dict
from app.models.core import Relationship
from app.models.physics import decide_action_with_context, decay_tension, react_to_event


@dataclass(frozen=True)
class ReplayTimelineItem:
    ts: datetime
    kind: str  # "event" or "decision"
    event_type: Optional[str] = None  # for kind="event": "message_received"/"message_sent"
    metadata: Optional[Dict[str, Any]] = None


@dataclass
class ReplayDecisionRecord:
    ts: datetime
    state_hash: str
    state_snapshot: Dict[str, Any]
    allowed_actions: List[str]
    blocked_actions: List[str]
    constraint_reasons: List[str]
    policy_version: str
    parameter_set_version: str
    temporal_context: Dict[str, Any]
    attribution: Dict[str, Dict[str, Any]]
    decision: DecisionResult


def make_default_attribution() -> Dict[str, Dict[str, Any]]:
    return {
        "24h": {
            "window_hours": 24,
            "status": "pending",
            "outcome_label": None,
            "reply": False,
            "progression": False,
            "negative_signal": False,
            "compliance_incident": False,
            "response_latency_hours": None,
            "reply_debt_resolved": None,
        },
        "72h": {
            "window_hours": 72,
            "status": "pending",
            "outcome_label": None,
            "reply": False,
            "progression": False,
            "negative_signal": False,
            "compliance_incident": False,
            "response_latency_hours": None,
            "reply_debt_resolved": None,
        },
        "7d": {
            "window_hours": 168,
            "status": "pending",
            "outcome_label": None,
            "reply": False,
            "progression": False,
            "negative_signal": False,
            "compliance_incident": False,
            "response_latency_hours": None,
            "reply_debt_resolved": None,
        },
    }


def annotate_attribution(
    record: ReplayDecisionRecord,
    window: str,
    *,
    status: str = "observed",
    outcome_label: Optional[str] = None,
    reply: Optional[bool] = None,
    progression: Optional[bool] = None,
    negative_signal: Optional[bool] = None,
    compliance_incident: Optional[bool] = None,
    response_latency_hours: Optional[float] = None,
    reply_debt_resolved: Optional[bool] = None,
) -> None:
    if window not in record.attribution:
        raise ValueError(f"Unknown attribution window: {window}")
    payload = record.attribution[window]
    payload["status"] = status
    if outcome_label is not None:
        payload["outcome_label"] = outcome_label
    if reply is not None:
        payload["reply"] = reply
    if progression is not None:
        payload["progression"] = progression
    if negative_signal is not None:
        payload["negative_signal"] = negative_signal
    if compliance_incident is not None:
        payload["compliance_incident"] = compliance_incident
    if response_latency_hours is not None:
        payload["response_latency_hours"] = response_latency_hours
    if reply_debt_resolved is not None:
        payload["reply_debt_resolved"] = reply_debt_resolved


def _clone_relationship(rel: Relationship) -> Relationship:
    return Relationship(
        id=rel.id,
        person_id=rel.person_id,
        stage=rel.stage,
        trust_score=rel.trust_score,
        interaction_tension=rel.interaction_tension,
        intent_debt=rel.intent_debt,
        last_contact_at=rel.last_contact_at,
        last_inbound_at=rel.last_inbound_at,
        last_outbound_at=rel.last_outbound_at,
        debt_created_at=rel.debt_created_at,
        dependency_blocked=rel.dependency_blocked,
        active=rel.active,
        engagement_score=getattr(rel, "engagement_score", 50.0),
        churn_risk=getattr(rel, "churn_risk", 0.0),
        relationship_type=getattr(rel, "relationship_type", "general"),
        priority=getattr(rel, "priority", 5),
        cadence_days=getattr(rel, "cadence_days", 7.0),
        next_decision_at=getattr(rel, "next_decision_at", None),
    )


def replay_timeline(
    initial_relationship: Relationship,
    timeline: List[ReplayTimelineItem],
    settings: Optional[Settings] = None,
) -> List[ReplayDecisionRecord]:
    """Deterministically replay events + decision points for a single relationship."""
    s = settings or get_settings()
    gate = ConstraintGate(s)
    rel = _clone_relationship(initial_relationship)
    records: List[ReplayDecisionRecord] = []
    default_policy_version = getattr(s, "policy_version", "v1.1")
    default_parameter_set_version = getattr(s, "parameter_set_version", "baseline-2026-03-08")

    for item in sorted(timeline, key=lambda x: x.ts):
        if item.kind == "event":
            if not item.event_type:
                raise ValueError("ReplayTimelineItem(kind='event') requires event_type")
            react_to_event(rel, item.event_type, item.ts, settings=s)
            continue

        if item.kind != "decision":
            raise ValueError(f"Unsupported replay kind: {item.kind}")

        rel.interaction_tension = decay_tension(rel, item.ts, settings=s)
        state = build_relationship_state(rel)
        constraints = gate.evaluate(state, item.ts)
        decision = decide_action_with_context(rel, item.ts, settings=s)
        temporal = build_temporal_context(item.ts, timezone=state.facts.contact_timezone)

        records.append(
            ReplayDecisionRecord(
                ts=item.ts,
                state_hash=snapshot_hash(state),
                state_snapshot=snapshot_state(state),
                allowed_actions=[a.value for a in constraints.allowed_actions],
                blocked_actions=[a.value for a in constraints.blocked_actions],
                constraint_reasons=[r.value for r in constraints.reasons],
                policy_version=decision.policy_version or default_policy_version,
                parameter_set_version=decision.parameter_set_version or default_parameter_set_version,
                temporal_context=temporal_context_dict(temporal),
                attribution=make_default_attribution(),
                decision=decision,
            )
        )

        if decision.action_type in {
            ActionType.send_fulfillment,
            ActionType.send_nudge,
            ActionType.send_gentle_ping,
            ActionType.send_with_apology,
        }:
            # Optional convenience to model immediate outbound after a send decision.
            react_to_event(rel, "message_sent", item.ts, settings=s)

    return records
