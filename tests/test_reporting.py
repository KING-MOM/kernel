from app.kernel.reporting import build_governance_report, render_markdown_report


def test_build_governance_report_with_segments():
    comparison = {"window_deltas": {"24h": {}, "72h": {}, "7d": {}}}
    promotion = {"decision": "PROMOTE", "severity": "none", "failures": [], "improvements": ["24h:progression_improved"]}
    segmented_comparison = {
        "segment_key": "stage",
        "segments": {
            "dormant": {
                "coverage": {
                    "baseline_share": 0.4,
                    "candidate_share": 0.45,
                    "baseline_total_decisions": 40,
                    "candidate_total_decisions": 45,
                }
            },
            "warm": {
                "coverage": {
                    "baseline_share": 0.6,
                    "candidate_share": 0.55,
                    "baseline_total_decisions": 60,
                    "candidate_total_decisions": 55,
                }
            }
        },
        "coverage_summary": {"baseline_total_decisions": 100, "candidate_total_decisions": 100, "segments_count": 1},
    }
    segmented_promotion = {
        "decision": "PROMOTE",
        "segment_key": "stage",
        "segment_results": {
            "warm": {"decision": "PROMOTE", "severity": "none", "failures": [], "improvements": ["24h"]},
            "dormant": {"decision": "HOLD_BASELINE", "severity": "none", "failures": [], "improvements": []},
        },
        "segment_failures": [],
        "segment_improvements": ["warm"],
    }

    report = build_governance_report(
        comparison=comparison,
        promotion=promotion,
        segmented_comparison=segmented_comparison,
        segmented_promotion=segmented_promotion,
        provenance={"policy_version": "v1.2", "parameter_set_version": "pset-1", "corpus_id": "corpus-abc"},
    )

    assert report["global"]["summary"]["decision"] == "PROMOTE"
    assert report["segmented"]["decision"] == "PROMOTE"
    # Sorted deterministically by segment name.
    assert [row["segment"] for row in report["segmented"]["segment_rows"]] == ["dormant", "warm"]
    assert "total_decisions" in report["traffic_share_basis"]
    assert report["report_schema_version"] == "1.0"
    assert report["provenance"]["policy_version"] == "v1.2"


def test_render_markdown_report_contains_key_sections():
    report = {
        "report_schema_version": "1.0",
        "traffic_share_basis": "segment coverage share is computed from total_decisions per corpus (not evaluated_decisions)",
        "provenance": {
            "policy_version": "v1.2",
            "parameter_set_version": "pset-1",
            "corpus_id": "corpus-xyz",
            "baseline_total_decisions": 100,
            "candidate_total_decisions": 120,
        },
        "global": {
            "summary": {
                "decision": "REJECT",
                "severity": "hard",
                "failures": ["24h:negative_signal_worsened"],
                "improvements": [],
            },
            "window_deltas": {},
        },
        "segmented": {
            "decision": "REJECT",
            "segment_key": "stage",
            "segment_rows": [
                {
                    "segment": "dormant",
                    "decision": "REJECT",
                    "severity": "hard",
                    "baseline_share": 0.2,
                    "candidate_share": 0.25,
                    "baseline_total_decisions": 20,
                    "candidate_total_decisions": 25,
                }
            ],
        },
    }

    md = render_markdown_report(report)
    assert "# Offline Governance Report" in md
    assert "Report schema version: `1.0`" in md
    assert "Global decision: `REJECT`" in md
    assert "Policy version: `v1.2`" in md
    assert "Corpus id: `corpus-xyz`" in md
    assert "Segment Review" in md
    assert "| Segment | Decision | Severity |" in md
