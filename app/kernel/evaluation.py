from __future__ import annotations

from statistics import median
from typing import Any, Dict, List, Tuple

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


def _segment_of(record: ReplayDecisionRecord, segment_key: str) -> str:
    facts = record.state_snapshot.get("facts", {}) if isinstance(record.state_snapshot, dict) else {}
    value = facts.get(segment_key)
    return str(value) if value is not None else "unknown"


def compute_segmented_scorecards(
    records: List[ReplayDecisionRecord],
    *,
    segment_key: str = "stage",
) -> Dict[str, Dict[str, Any]]:
    groups: Dict[str, List[ReplayDecisionRecord]] = {}
    for record in records:
        groups.setdefault(_segment_of(record, segment_key), []).append(record)
    return {segment: compute_scorecard(items) for segment, items in groups.items()}


def compare_records_by_segment(
    baseline_records: List[ReplayDecisionRecord],
    candidate_records: List[ReplayDecisionRecord],
    *,
    segment_key: str = "stage",
) -> Dict[str, Any]:
    baseline = compute_segmented_scorecards(baseline_records, segment_key=segment_key)
    candidate = compute_segmented_scorecards(candidate_records, segment_key=segment_key)
    segments = sorted(set(baseline.keys()) | set(candidate.keys()))
    by_segment: Dict[str, Any] = {}

    total_baseline = len(baseline_records)
    total_candidate = len(candidate_records)

    for segment in segments:
        b = baseline.get(segment, {"total_decisions": 0, "send_decisions": 0, "window_metrics": {w: {} for w in WINDOWS}})
        c = candidate.get(segment, {"total_decisions": 0, "send_decisions": 0, "window_metrics": {w: {} for w in WINDOWS}})
        by_segment[segment] = compare_scorecards(b, c)
        by_segment[segment]["coverage"] = {
            "baseline_total_decisions": b.get("total_decisions", 0),
            "candidate_total_decisions": c.get("total_decisions", 0),
            "baseline_share": (b.get("total_decisions", 0) / total_baseline) if total_baseline else 0.0,
            "candidate_share": (c.get("total_decisions", 0) / total_candidate) if total_candidate else 0.0,
        }

    return {
        "segment_key": segment_key,
        "segments": by_segment,
        "coverage_summary": {
            "baseline_total_decisions": total_baseline,
            "candidate_total_decisions": total_candidate,
            "segments_count": len(segments),
        },
    }


def evaluate_promotion(
    comparison: Dict[str, Any],
    *,
    required_windows: Tuple[str, ...] = WINDOWS,
    min_evaluated_decisions: int = 30,
    max_negative_signal_rate_delta: float = 0.0,
    min_progression_rate_delta: float = 0.02,
    min_latency_improvement_hours: float = 1.0,
) -> Dict[str, Any]:
    failures: List[str] = []
    improvements: List[str] = []
    per_window: Dict[str, Any] = {}

    for window in required_windows:
        data = comparison["window_deltas"].get(window, {})
        eval_meta = data.get("evaluated_decisions", {})
        metrics = data.get("metrics", {})
        candidate_eval = eval_meta.get("candidate")

        window_failures: List[str] = []
        window_improvements: List[str] = []

        if not isinstance(candidate_eval, int) or candidate_eval < min_evaluated_decisions:
            window_failures.append(f"{window}:insufficient_evaluated_decisions")

        compliance_delta = metrics.get("compliance_incidents", {}).get("delta")
        if compliance_delta is not None and compliance_delta > 0:
            window_failures.append(f"{window}:compliance_worsened")

        negative_delta = metrics.get("negative_signal_rate", {}).get("delta")
        if negative_delta is not None and negative_delta > max_negative_signal_rate_delta:
            window_failures.append(f"{window}:negative_signal_worsened")

        progression_delta = metrics.get("progression_rate", {}).get("delta")
        if progression_delta is not None and progression_delta >= min_progression_rate_delta:
            window_improvements.append(f"{window}:progression_improved")

        latency_delta = metrics.get("median_response_latency_hours", {}).get("delta")
        if latency_delta is not None and latency_delta <= -min_latency_improvement_hours:
            window_improvements.append(f"{window}:latency_improved")

        failures.extend(window_failures)
        improvements.extend(window_improvements)
        per_window[window] = {
            "failures": window_failures,
            "improvements": window_improvements,
        }

    severity = "none"
    if failures:
        decision = "REJECT"
        severity = "hard"
    elif improvements:
        decision = "PROMOTE"
    else:
        decision = "HOLD_BASELINE"

    return {
        "decision": decision,
        "failures": failures,
        "improvements": improvements,
        "thresholds": {
            "required_windows": list(required_windows),
            "min_evaluated_decisions": min_evaluated_decisions,
            "max_negative_signal_rate_delta": max_negative_signal_rate_delta,
            "min_progression_rate_delta": min_progression_rate_delta,
            "min_latency_improvement_hours": min_latency_improvement_hours,
        },
        "per_window": per_window,
        "severity": severity,
    }


def evaluate_segmented_promotion(
    segmented_comparison: Dict[str, Any],
    *,
    required_segments: Tuple[str, ...] | None = None,
    required_windows: Tuple[str, ...] = WINDOWS,
    min_evaluated_decisions: int = 30,
    min_evaluated_decisions_by_segment: Dict[str, int] | None = None,
    max_negative_signal_rate_delta: float = 0.0,
    min_progression_rate_delta: float = 0.02,
    min_latency_improvement_hours: float = 1.0,
) -> Dict[str, Any]:
    segment_results: Dict[str, Any] = {}
    segment_failures: List[str] = []
    segment_improvements: List[str] = []
    segment_reject_severities: Dict[str, str] = {}
    segments = segmented_comparison.get("segments", {})

    for segment, comparison in segments.items():
        segment_min = (
            min_evaluated_decisions_by_segment.get(segment, min_evaluated_decisions)
            if min_evaluated_decisions_by_segment
            else min_evaluated_decisions
        )
        result = evaluate_promotion(
            comparison,
            required_windows=required_windows,
            min_evaluated_decisions=segment_min,
            max_negative_signal_rate_delta=max_negative_signal_rate_delta,
            min_progression_rate_delta=min_progression_rate_delta,
            min_latency_improvement_hours=min_latency_improvement_hours,
        )
        segment_results[segment] = result
        if result["decision"] == "REJECT":
            segment_failures.append(segment)
            segment_reject_severities[segment] = result.get("severity", "hard")
        if result["decision"] == "PROMOTE":
            segment_improvements.append(segment)

    missing_required = []
    if required_segments:
        missing_required = [s for s in required_segments if s not in segments]
        segment_failures.extend([f"missing:{s}" for s in missing_required])

    if segment_failures:
        decision = "REJECT"
    elif segment_improvements:
        decision = "PROMOTE"
    else:
        decision = "HOLD_BASELINE"

    return {
        "decision": decision,
        "segment_key": segmented_comparison.get("segment_key", "stage"),
        "segment_results": segment_results,
        "segment_failures": segment_failures,
        "segment_reject_severities": segment_reject_severities,
        "segment_improvements": segment_improvements,
        "missing_required_segments": missing_required,
    }
