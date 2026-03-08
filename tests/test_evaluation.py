from datetime import datetime, timedelta

from app.config import Settings
from app.kernel.evaluation import compare_records, compare_scorecards, compute_scorecard, evaluate_promotion
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


def test_compare_scorecards_window_deltas():
    baseline = {
        "total_decisions": 10,
        "send_decisions": 6,
        "window_metrics": {
            "24h": {
                "evaluated_decisions": 6,
                "reply_rate": 0.5,
                "progression_rate": 0.3,
                "negative_signal_rate": 0.2,
                "unresolved_reply_debt_rate": 0.4,
                "compliance_incidents": 2,
                "median_response_latency_hours": 10.0,
            },
            "72h": {
                "evaluated_decisions": 6,
                "reply_rate": 0.6,
                "progression_rate": 0.35,
                "negative_signal_rate": 0.2,
                "unresolved_reply_debt_rate": 0.3,
                "compliance_incidents": 1,
                "median_response_latency_hours": 12.0,
            },
            "7d": {
                "evaluated_decisions": 6,
                "reply_rate": 0.7,
                "progression_rate": 0.4,
                "negative_signal_rate": 0.25,
                "unresolved_reply_debt_rate": 0.25,
                "compliance_incidents": 1,
                "median_response_latency_hours": 18.0,
            },
        },
    }
    candidate = {
        "total_decisions": 10,
        "send_decisions": 6,
        "window_metrics": {
            "24h": {
                "evaluated_decisions": 6,
                "reply_rate": 0.7,
                "progression_rate": 0.5,
                "negative_signal_rate": 0.1,
                "unresolved_reply_debt_rate": 0.2,
                "compliance_incidents": 1,
                "median_response_latency_hours": 8.0,
            },
            "72h": {
                "evaluated_decisions": 6,
                "reply_rate": 0.75,
                "progression_rate": 0.45,
                "negative_signal_rate": 0.12,
                "unresolved_reply_debt_rate": 0.2,
                "compliance_incidents": 1,
                "median_response_latency_hours": 9.0,
            },
            "7d": {
                "evaluated_decisions": 6,
                "reply_rate": 0.8,
                "progression_rate": 0.55,
                "negative_signal_rate": 0.2,
                "unresolved_reply_debt_rate": 0.15,
                "compliance_incidents": 0,
                "median_response_latency_hours": 14.0,
            },
        },
    }

    diff = compare_scorecards(baseline, candidate)
    d24 = diff["window_deltas"]["24h"]["metrics"]
    assert d24["reply_rate"]["delta"] == 0.2
    assert d24["progression_rate"]["delta"] == 0.2
    assert d24["negative_signal_rate"]["delta"] == -0.1
    assert d24["unresolved_reply_debt_rate"]["delta"] == -0.2
    assert d24["compliance_incidents"]["delta"] == -1
    assert d24["median_response_latency_hours"]["delta"] == -2.0


def test_compare_records_end_to_end():
    t0 = datetime(2026, 1, 2, 9, 0, 0)
    timeline = [
        ReplayTimelineItem(ts=t0, kind="event", event_type="message_received"),
        ReplayTimelineItem(ts=t0 + timedelta(minutes=1), kind="decision"),
    ]

    baseline = replay_timeline(_make_rel(id="rel-base"), timeline)
    candidate = replay_timeline(_make_rel(id="rel-cand"), timeline)

    annotate_attribution(
        baseline[0],
        "24h",
        reply=False,
        progression=False,
        negative_signal=True,
        compliance_incident=False,
        response_latency_hours=None,
        reply_debt_resolved=False,
    )
    annotate_attribution(
        candidate[0],
        "24h",
        reply=True,
        progression=True,
        negative_signal=False,
        compliance_incident=False,
        response_latency_hours=3.0,
        reply_debt_resolved=True,
    )

    result = compare_records(baseline, candidate)
    d24 = result["window_deltas"]["24h"]["metrics"]
    assert d24["reply_rate"]["delta"] == 1.0
    assert d24["progression_rate"]["delta"] == 1.0
    assert d24["negative_signal_rate"]["delta"] == -1.0
    assert d24["unresolved_reply_debt_rate"]["delta"] == -1.0


def _base_comparison() -> dict:
    return {
        "window_deltas": {
            "24h": {
                "evaluated_decisions": {"baseline": 40, "candidate": 40, "delta": 0},
                "metrics": {
                    "progression_rate": {"baseline": 0.3, "candidate": 0.35, "delta": 0.05},
                    "negative_signal_rate": {"baseline": 0.1, "candidate": 0.1, "delta": 0.0},
                    "compliance_incidents": {"baseline": 1, "candidate": 1, "delta": 0},
                    "median_response_latency_hours": {"baseline": 12.0, "candidate": 10.0, "delta": -2.0},
                },
            },
            "72h": {
                "evaluated_decisions": {"baseline": 40, "candidate": 40, "delta": 0},
                "metrics": {
                    "progression_rate": {"baseline": 0.35, "candidate": 0.37, "delta": 0.02},
                    "negative_signal_rate": {"baseline": 0.12, "candidate": 0.11, "delta": -0.01},
                    "compliance_incidents": {"baseline": 1, "candidate": 1, "delta": 0},
                    "median_response_latency_hours": {"baseline": 15.0, "candidate": 14.0, "delta": -1.0},
                },
            },
            "7d": {
                "evaluated_decisions": {"baseline": 40, "candidate": 40, "delta": 0},
                "metrics": {
                    "progression_rate": {"baseline": 0.4, "candidate": 0.42, "delta": 0.02},
                    "negative_signal_rate": {"baseline": 0.15, "candidate": 0.15, "delta": 0.0},
                    "compliance_incidents": {"baseline": 1, "candidate": 1, "delta": 0},
                    "median_response_latency_hours": {"baseline": 20.0, "candidate": 18.5, "delta": -1.5},
                },
            },
        }
    }


def test_evaluate_promotion_promote():
    comparison = _base_comparison()
    result = evaluate_promotion(comparison)
    assert result["decision"] == "PROMOTE"
    assert not result["failures"]
    assert result["improvements"]


def test_evaluate_promotion_reject_on_guardrail():
    comparison = _base_comparison()
    comparison["window_deltas"]["24h"]["metrics"]["negative_signal_rate"]["delta"] = 0.05
    result = evaluate_promotion(comparison)
    assert result["decision"] == "REJECT"
    assert any("negative_signal_worsened" in f for f in result["failures"])


def test_evaluate_promotion_hold_baseline_on_tie():
    comparison = _base_comparison()
    for w in ("24h", "72h", "7d"):
        comparison["window_deltas"][w]["metrics"]["progression_rate"]["delta"] = 0.0
        comparison["window_deltas"][w]["metrics"]["median_response_latency_hours"]["delta"] = 0.0
    result = evaluate_promotion(comparison)
    assert result["decision"] == "HOLD_BASELINE"
    assert not result["failures"]
    assert not result["improvements"]
