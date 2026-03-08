import json
from pathlib import Path

import pytest

from app.kernel.reporting import build_governance_report, render_markdown_report
from app.kernel.review_workflow import write_review_package


def _base_inputs():
    comparison = {
        "summary": {"baseline_total_decisions": 100, "candidate_total_decisions": 110},
        "window_deltas": {"24h": {}, "72h": {}, "7d": {}},
    }
    promotion = {"decision": "PROMOTE", "severity": "none", "failures": [], "improvements": ["24h"]}
    segmented_comparison = {
        "segment_key": "stage",
        "segments": {},
        "coverage_summary": {"baseline_total_decisions": 100, "candidate_total_decisions": 110, "segments_count": 0},
    }
    segmented_promotion = {
        "decision": "PROMOTE",
        "segment_key": "stage",
        "segment_results": {},
        "segment_failures": [],
        "segment_improvements": [],
    }
    provenance = {
        "policy_version": "v1.2",
        "parameter_set_version": "pset-1",
        "corpus_id": "corpus-abc",
    }
    report = build_governance_report(
        comparison=comparison,
        promotion=promotion,
        segmented_comparison=segmented_comparison,
        segmented_promotion=segmented_promotion,
        provenance=provenance,
    )
    md = render_markdown_report(report)
    return comparison, promotion, segmented_comparison, segmented_promotion, report, md


def test_write_review_package_generates_manifest_and_files(tmp_path: Path):
    comparison, promotion, segmented_comparison, segmented_promotion, report, md = _base_inputs()

    manifest = write_review_package(
        out_dir=tmp_path,
        report=report,
        report_markdown=md,
        comparison=comparison,
        promotion=promotion,
        segmented_comparison=segmented_comparison,
        segmented_promotion=segmented_promotion,
    )

    assert manifest["review_package_schema_version"] == "1.0"
    assert manifest["review_workflow_version"] == "1.0"
    assert manifest["report_schema_version"] == "1.0"
    assert manifest["package_hash"]
    assert (tmp_path / "manifest.json").exists()
    assert (tmp_path / "report.md").exists()
    assert (tmp_path / "report.json").exists()

    persisted = json.loads((tmp_path / "manifest.json").read_text())
    assert persisted["package_hash"] == manifest["package_hash"]
    assert "comparison_json" in persisted["files"]
    # Ensure deterministic JSON formatting has trailing newline.
    assert (tmp_path / "manifest.json").read_text().endswith("\n")


def test_write_review_package_requires_provenance(tmp_path: Path):
    comparison, promotion, segmented_comparison, segmented_promotion, report, md = _base_inputs()
    report["provenance"] = {"policy_version": "v1.2"}  # missing required fields

    with pytest.raises(ValueError):
        write_review_package(
            out_dir=tmp_path,
            report=report,
            report_markdown=md,
            comparison=comparison,
            promotion=promotion,
            segmented_comparison=segmented_comparison,
            segmented_promotion=segmented_promotion,
        )
