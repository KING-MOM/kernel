from __future__ import annotations

from statistics import median
from typing import Any, Dict, List

from app.kernel.replay import ReplayDecisionRecord

SEND_PREFIX = "SEND_"
WINDOWS = ("24h", "72h", "7d")


def _is_send_decision(record: ReplayDecisionRecord) -> bool:
    return record.decision.action_type.value.startswith(SEND_PREFIX)


def _window_bool(payload: Dict[str, Any], key: str) -> bool:
    return bool(payload.get(key, False))


def _window_latency(payload: Dict[str, Any]) -> float | None:
    value = payload.get("response_latency_hours")
    return float(value) if isinstance(value, (int, float)) else None


def compute_scorecard(records: List[ReplayDecisionRecord]) -> Dict[str, Any]:
    send_records = [r for r in records if _is_send_decision(r)]
    by_window: Dict[str, Dict[str, Any]] = {}

    for window in WINDOWS:
        evaluated = []
        for record in send_records:
            payload = record.attribution.get(window, {})
            if payload.get("status") == "observed":
                evaluated.append(payload)

        count = len(evaluated)
        replies = sum(1 for p in evaluated if _window_bool(p, "reply"))
        progression = sum(1 for p in evaluated if _window_bool(p, "progression"))
        negative = sum(1 for p in evaluated if _window_bool(p, "negative_signal"))
        compliance = sum(1 for p in evaluated if _window_bool(p, "compliance_incident"))
        unresolved = sum(1 for p in evaluated if p.get("reply_debt_resolved") is False)
        latencies = [lat for p in evaluated if (lat := _window_latency(p)) is not None]

        by_window[window] = {
            "evaluated_decisions": count,
            "reply_rate": (replies / count) if count else None,
            "progression_rate": (progression / count) if count else None,
            "negative_signal_rate": (negative / count) if count else None,
            "unresolved_reply_debt_rate": (unresolved / count) if count else None,
            "compliance_incidents": compliance,
            "median_response_latency_hours": median(latencies) if latencies else None,
        }

    return {
        "total_decisions": len(records),
        "send_decisions": len(send_records),
        "window_metrics": by_window,
    }


def _delta(candidate: float | int | None, baseline: float | int | None) -> float | int | None:
    if candidate is None or baseline is None:
        return None
    value = candidate - baseline
    if isinstance(value, float):
        return round(value, 6)
    return value


def compare_scorecards(
    baseline_scorecard: Dict[str, Any],
    candidate_scorecard: Dict[str, Any],
) -> Dict[str, Any]:
    by_window: Dict[str, Dict[str, Any]] = {}
    metric_keys = (
        "reply_rate",
        "progression_rate",
        "negative_signal_rate",
        "unresolved_reply_debt_rate",
        "compliance_incidents",
        "median_response_latency_hours",
    )

    for window in WINDOWS:
        base = baseline_scorecard["window_metrics"].get(window, {})
        cand = candidate_scorecard["window_metrics"].get(window, {})
        metrics: Dict[str, Any] = {}
        for key in metric_keys:
            metrics[key] = {
                "baseline": base.get(key),
                "candidate": cand.get(key),
                "delta": _delta(cand.get(key), base.get(key)),
            }
        by_window[window] = {
            "evaluated_decisions": {
                "baseline": base.get("evaluated_decisions"),
                "candidate": cand.get("evaluated_decisions"),
                "delta": _delta(cand.get("evaluated_decisions"), base.get("evaluated_decisions")),
            },
            "metrics": metrics,
        }

    return {
        "summary": {
            "baseline_total_decisions": baseline_scorecard.get("total_decisions"),
            "candidate_total_decisions": candidate_scorecard.get("total_decisions"),
            "baseline_send_decisions": baseline_scorecard.get("send_decisions"),
            "candidate_send_decisions": candidate_scorecard.get("send_decisions"),
        },
        "window_deltas": by_window,
    }


def compare_records(
    baseline_records: List[ReplayDecisionRecord],
    candidate_records: List[ReplayDecisionRecord],
) -> Dict[str, Any]:
    baseline = compute_scorecard(baseline_records)
    candidate = compute_scorecard(candidate_records)
    return compare_scorecards(baseline, candidate)
