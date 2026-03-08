from datetime import datetime, timedelta

from app.config import Settings
from app.kernel.evaluation import compute_scorecard
from app.kernel.replay import ReplayTimelineItem, annotate_attribution, replay_timeline
from app.models.core import Relationship


def _make_rel(**kwargs) -> Relationship:
    base = {
        "id": "rel-eval-1",
        "person_id": "person-eval-1",
        "stage": "onboarded",
        "trust_score": 0.5,
        "interaction_tension": 0.0,
        "intent_debt": 0,
        "last_contact_at": datetime(2026, 1, 1, 10, 0, 0),
        "last_inbound_at": None,
        "last_outbound_at": None,
        "debt_created_at": None,
        "dependency_blocked": False,
        "active": True,
        "engagement_score": 50.0,
        "churn_risk": 0.0,
        "relationship_type": "general",
        "priority": 5,
        "cadence_days": 7.0,
        "next_decision_at": None,
    }
    base.update(kwargs)
    return Relationship(**base)


def test_compute_scorecard_by_window():
    rel = _make_rel()
    t0 = datetime(2026, 1, 2, 9, 0, 0)

    timeline = [
        ReplayTimelineItem(ts=t0, kind="event", event_type="message_received"),
        ReplayTimelineItem(ts=t0 + timedelta(minutes=1), kind="decision"),
    ]
    records = replay_timeline(rel, timeline, settings=Settings())
    assert len(records) == 1

    # Observed outcomes for each attribution window
    annotate_attribution(
        records[0],
        "24h",
        reply=True,
        progression=True,
        negative_signal=False,
        compliance_incident=False,
        response_latency_hours=2.0,
        reply_debt_resolved=True,
    )
    annotate_attribution(
        records[0],
        "72h",
        reply=True,
        progression=True,
        negative_signal=False,
        compliance_incident=False,
        response_latency_hours=5.0,
        reply_debt_resolved=True,
    )
    annotate_attribution(
        records[0],
        "7d",
        reply=True,
        progression=False,
        negative_signal=True,
        compliance_incident=False,
        response_latency_hours=36.0,
        reply_debt_resolved=False,
    )

    scorecard = compute_scorecard(records)

    assert scorecard["total_decisions"] == 1
    assert scorecard["send_decisions"] == 1

    m24 = scorecard["window_metrics"]["24h"]
    assert m24["reply_rate"] == 1.0
    assert m24["progression_rate"] == 1.0
    assert m24["negative_signal_rate"] == 0.0
    assert m24["unresolved_reply_debt_rate"] == 0.0
    assert m24["median_response_latency_hours"] == 2.0

    m7d = scorecard["window_metrics"]["7d"]
    assert m7d["reply_rate"] == 1.0
    assert m7d["progression_rate"] == 0.0
    assert m7d["negative_signal_rate"] == 1.0
    assert m7d["unresolved_reply_debt_rate"] == 1.0
    assert m7d["median_response_latency_hours"] == 36.0


def test_compute_scorecard_ignores_pending_windows():
    rel = _make_rel()
    t0 = datetime(2026, 1, 2, 9, 0, 0)
    timeline = [
        ReplayTimelineItem(ts=t0, kind="event", event_type="message_received"),
        ReplayTimelineItem(ts=t0 + timedelta(minutes=1), kind="decision"),
    ]
    records = replay_timeline(rel, timeline)

    scorecard = compute_scorecard(records)

    for window in ("24h", "72h", "7d"):
        assert scorecard["window_metrics"][window]["evaluated_decisions"] == 0
        assert scorecard["window_metrics"][window]["reply_rate"] is None
