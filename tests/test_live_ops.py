from app.kernel.live_ops import build_live_ops_report, render_live_ops_markdown


def test_build_live_ops_report_core_fields():
    state = {
        "state": "RUNNING",
        "history": [
            {"from_state": "READY", "to_state": "RUNNING", "actor_id": "ops", "reason": "launch", "ts_utc": "2026-03-08T10:00:00+00:00"},
            {"from_state": "RUNNING", "to_state": "PAUSED", "actor_id": "ops", "reason": "pause", "ts_utc": "2026-03-08T11:00:00+00:00"},
        ],
    }
    launch = {
        "launched_at_utc": "2026-03-08T10:00:00+00:00",
        "launched_by": "ops",
        "cohort": "10pct",
        "experiment_arm": "candidate",
        "package_hash": "pkg-hash",
        "policy_version": "v1.2",
        "parameter_set_version": "pset-1",
        "corpus_id": "corpus-1",
    }
    evals = [
        {
            "decision": "PAUSE",
            "severity": "soft",
            "resolved": False,
            "evaluated_at_utc": "2026-03-08T10:30:00+00:00",
            "signal": {
                "metric_name": "latency",
                "metric_window": "24h",
                "observed_value": 5.0,
                "threshold_value": 3.0,
                "threshold_direction": "upper",
                "cohort": "10pct",
                "experiment_arm": "candidate",
                "segment": "warm",
            },
        }
    ]

    report = build_live_ops_report(
        state_doc=state,
        launch_gate=launch,
        guardrail_evaluations=evals,
        live_metrics=[{"window": "24h", "scope": "10pct/candidate/warm", "reply_rate": 0.6, "progression_rate": 0.3, "negative_signal_rate": 0.08, "unresolved_reply_debt_rate": 0.2, "median_response_latency_hours": 6.0}],
    )

    assert report["experiment_state"] == "RUNNING"
    assert report["launch_provenance"]["package_hash"] == "pkg-hash"
    assert report["unresolved_breaches"]["count"] == 1
    assert report["active_guardrail_signals"][0]["decision"] == "PAUSE"


def test_render_live_ops_markdown_sections():
    report = {
        "experiment_state": "RUNNING",
        "launch_provenance": {
            "package_hash": "pkg",
            "launched_at_utc": "2026-03-08T10:00:00+00:00",
            "launched_by": "ops",
            "cohort": "10pct",
            "experiment_arm": "candidate",
            "policy_version": "v1.2",
            "parameter_set_version": "pset-1",
        },
        "aggregate_control_recommendation": {"decision": "PAUSE", "severity": "soft", "reasons": ["pause_present"]},
        "unresolved_breaches": {"count": 1, "stale_after_hours": 72},
        "active_guardrail_signals": [],
        "pause_rollback_history": [],
        "core_live_metrics": [],
    }
    md = render_live_ops_markdown(report)
    assert "# Live Ops Report" in md
    assert "## Guardrails" in md
    assert "## Active Signals" in md
    assert "## Core Metrics" in md
