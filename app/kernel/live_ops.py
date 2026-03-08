from __future__ import annotations

from typing import Any, Dict, List, Optional

from app.kernel.rollout import aggregate_guardrail_evaluations

LIVE_OPS_REPORT_SCHEMA_VERSION = "1.0"


def _compact_eval(evaluation: Dict[str, Any]) -> Dict[str, Any]:
    signal = evaluation.get("signal", {})
    return {
        "evaluated_at_utc": evaluation.get("evaluated_at_utc"),
        "decision": evaluation.get("decision"),
        "severity": evaluation.get("severity"),
        "metric_name": signal.get("metric_name"),
        "metric_window": signal.get("metric_window"),
        "observed_value": signal.get("observed_value"),
        "threshold_value": signal.get("threshold_value"),
        "threshold_direction": signal.get("threshold_direction"),
        "cohort": signal.get("cohort"),
        "experiment_arm": signal.get("experiment_arm"),
        "segment": signal.get("segment"),
        "resolved": bool(evaluation.get("resolved", False)),
    }


def build_live_ops_report(
    *,
    state_doc: Dict[str, Any],
    launch_gate: Dict[str, Any],
    guardrail_evaluations: List[Dict[str, Any]],
    aggregate_result: Optional[Dict[str, Any]] = None,
    live_metrics: Optional[List[Dict[str, Any]]] = None,
    stale_after_hours: float = 72.0,
) -> Dict[str, Any]:
    aggregate = aggregate_result or aggregate_guardrail_evaluations(
        guardrail_evaluations,
        experiment_id=None,
        package_hash=launch_gate.get("package_hash"),
        stale_after_hours=stale_after_hours,
    )

    unresolved = [
        ev
        for ev in guardrail_evaluations
        if ev.get("decision") in {"PAUSE", "ROLLBACK_CANDIDATE"} and not bool(ev.get("resolved", False))
    ]
    unresolved_sorted = sorted(unresolved, key=lambda x: str(x.get("evaluated_at_utc", "")), reverse=True)

    history = list(state_doc.get("history", []))
    pause_rollback_history = [
        h
        for h in history
        if h.get("to_state") in {"PAUSED", "ROLLED_BACK"} or h.get("rollback_event") is not None
    ]

    return {
        "live_ops_report_schema_version": LIVE_OPS_REPORT_SCHEMA_VERSION,
        "experiment_state": state_doc.get("state"),
        "launch_provenance": {
            "launched_at_utc": launch_gate.get("launched_at_utc"),
            "launched_by": launch_gate.get("launched_by"),
            "cohort": launch_gate.get("cohort"),
            "experiment_arm": launch_gate.get("experiment_arm"),
            "package_hash": launch_gate.get("package_hash"),
            "policy_version": launch_gate.get("policy_version"),
            "parameter_set_version": launch_gate.get("parameter_set_version"),
            "corpus_id": launch_gate.get("corpus_id"),
        },
        "active_guardrail_signals": [_compact_eval(ev) for ev in unresolved_sorted],
        "aggregate_control_recommendation": aggregate,
        "unresolved_breaches": {
            "count": len(unresolved_sorted),
            "stale_after_hours": stale_after_hours,
        },
        "pause_rollback_history": pause_rollback_history,
        "core_live_metrics": live_metrics or [],
    }


def render_live_ops_markdown(report: Dict[str, Any]) -> str:
    lines: List[str] = []
    launch = report.get("launch_provenance", {})
    aggregate = report.get("aggregate_control_recommendation", {})
    lines.append("# Live Ops Report")
    lines.append("")
    lines.append(f"- State: `{report.get('experiment_state', 'UNKNOWN')}`")
    lines.append(f"- Package hash: `{launch.get('package_hash', 'unknown')}`")
    lines.append(f"- Launched: `{launch.get('launched_at_utc', 'unknown')}` by `{launch.get('launched_by', 'unknown')}`")
    lines.append(f"- Cohort/Arm: `{launch.get('cohort', 'unknown')}` / `{launch.get('experiment_arm', 'unknown')}`")
    lines.append(f"- Policy/Params: `{launch.get('policy_version', 'unknown')}` / `{launch.get('parameter_set_version', 'unknown')}`")
    lines.append("")

    lines.append("## Guardrails")
    lines.append(
        f"- Aggregate recommendation: `{aggregate.get('decision', 'NONE')}` (severity `{aggregate.get('severity', 'none')}`)"
    )
    lines.append(
        f"- Unresolved breaches: `{report.get('unresolved_breaches', {}).get('count', 0)}` (stale after `{report.get('unresolved_breaches', {}).get('stale_after_hours', 'n/a')}h`)"
    )
    reasons = aggregate.get("reasons", [])
    lines.append(f"- Aggregate reasons: {', '.join(reasons) if reasons else 'none'}")
    lines.append("")

    lines.append("## Active Signals")
    active = report.get("active_guardrail_signals", [])
    if not active:
        lines.append("- none")
    else:
        lines.append("| Time | Decision | Metric | Window | Observed | Threshold | Scope |")
        lines.append("| --- | --- | --- | --- | ---: | ---: | --- |")
        for ev in active[:20]:
            scope = "/".join(
                [
                    str(ev.get("cohort") or "-"),
                    str(ev.get("experiment_arm") or "-"),
                    str(ev.get("segment") or "-"),
                ]
            )
            lines.append(
                f"| {ev.get('evaluated_at_utc')} | {ev.get('decision')} | {ev.get('metric_name')} | {ev.get('metric_window')} | "
                f"{ev.get('observed_value')} | {ev.get('threshold_value')} | {scope} |"
            )
    lines.append("")

    lines.append("## Pause/Rollback History")
    prh = report.get("pause_rollback_history", [])
    if not prh:
        lines.append("- none")
    else:
        for entry in prh[-20:]:
            lines.append(
                f"- `{entry.get('ts_utc')}` {entry.get('from_state')} -> {entry.get('to_state')} by `{entry.get('actor_id')}`: {entry.get('reason')}"
            )
    lines.append("")

    lines.append("## Core Metrics")
    metrics = report.get("core_live_metrics", [])
    if not metrics:
        lines.append("- none")
    else:
        lines.append("| Window | Scope | Reply Rate | Progression | Negative Signal | Unresolved Debt | Latency (h) |")
        lines.append("| --- | --- | ---: | ---: | ---: | ---: | ---: |")
        for m in metrics:
            lines.append(
                f"| {m.get('window')} | {m.get('scope', 'global')} | {m.get('reply_rate')} | {m.get('progression_rate')} | "
                f"{m.get('negative_signal_rate')} | {m.get('unresolved_reply_debt_rate')} | {m.get('median_response_latency_hours')} |"
            )

    return "\n".join(lines)
