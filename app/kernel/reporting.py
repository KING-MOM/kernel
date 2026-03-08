from __future__ import annotations

from typing import Any, Dict, List, Optional

REPORT_SCHEMA_VERSION = "1.0"


def build_governance_report(
    *,
    comparison: Dict[str, Any],
    promotion: Dict[str, Any],
    segmented_comparison: Optional[Dict[str, Any]] = None,
    segmented_promotion: Optional[Dict[str, Any]] = None,
    provenance: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    global_summary = {
        "decision": promotion.get("decision"),
        "severity": promotion.get("severity", "none"),
        "failures": promotion.get("failures", []),
        "improvements": promotion.get("improvements", []),
    }

    report: Dict[str, Any] = {
        "report_schema_version": REPORT_SCHEMA_VERSION,
        "provenance": provenance or {},
        "traffic_share_basis": "segment coverage share is computed from total_decisions per corpus (not evaluated_decisions)",
        "global": {
            "summary": global_summary,
            "window_deltas": comparison.get("window_deltas", {}),
        },
    }

    if segmented_comparison and segmented_promotion:
        segments = segmented_comparison.get("segments", {})
        segment_rows: List[Dict[str, Any]] = []
        for segment in sorted(segments.keys()):
            segment_cmp = segments[segment]
            seg_result = segmented_promotion.get("segment_results", {}).get(segment, {})
            coverage = segment_cmp.get("coverage", {})
            segment_rows.append(
                {
                    "segment": segment,
                    "decision": seg_result.get("decision"),
                    "severity": seg_result.get("severity", "none"),
                    "failures": seg_result.get("failures", []),
                    "improvements": seg_result.get("improvements", []),
                    "baseline_share": coverage.get("baseline_share"),
                    "candidate_share": coverage.get("candidate_share"),
                    "baseline_total_decisions": coverage.get("baseline_total_decisions"),
                    "candidate_total_decisions": coverage.get("candidate_total_decisions"),
                }
            )

        report["segmented"] = {
            "decision": segmented_promotion.get("decision"),
            "segment_key": segmented_promotion.get("segment_key", segmented_comparison.get("segment_key")),
            "segment_failures": segmented_promotion.get("segment_failures", []),
            "segment_improvements": segmented_promotion.get("segment_improvements", []),
            "segment_rows": segment_rows,
            "coverage_summary": segmented_comparison.get("coverage_summary", {}),
        }

    return report


def render_markdown_report(report: Dict[str, Any]) -> str:
    lines: List[str] = []
    global_summary = report.get("global", {}).get("summary", {})
    lines.append("# Offline Governance Report")
    lines.append("")
    lines.append(f"- Report schema version: `{report.get('report_schema_version', 'unknown')}`")
    lines.append(f"- Global decision: `{global_summary.get('decision', 'UNKNOWN')}`")
    lines.append(f"- Global severity: `{global_summary.get('severity', 'none')}`")
    lines.append(f"- Share basis: {report.get('traffic_share_basis', '')}")
    provenance = report.get("provenance", {})
    if provenance:
        lines.append(f"- Policy version: `{provenance.get('policy_version', 'unknown')}`")
        lines.append(f"- Parameter set version: `{provenance.get('parameter_set_version', 'unknown')}`")
        lines.append(f"- Corpus id: `{provenance.get('corpus_id', 'unknown')}`")
        lines.append(f"- Baseline decisions: `{provenance.get('baseline_total_decisions', 'unknown')}`")
        lines.append(f"- Candidate decisions: `{provenance.get('candidate_total_decisions', 'unknown')}`")
    lines.append("")

    failures = global_summary.get("failures", [])
    improvements = global_summary.get("improvements", [])
    lines.append("## Global Signals")
    lines.append(f"- Failures: {', '.join(failures) if failures else 'none'}")
    lines.append(f"- Improvements: {', '.join(improvements) if improvements else 'none'}")
    lines.append("")

    segmented = report.get("segmented")
    if segmented:
        lines.append("## Segment Review")
        lines.append(f"- Segment key: `{segmented.get('segment_key', 'unknown')}`")
        lines.append(f"- Segmented decision: `{segmented.get('decision', 'UNKNOWN')}`")
        lines.append("")
        lines.append("| Segment | Decision | Severity | Baseline Share | Candidate Share | Baseline N | Candidate N |")
        lines.append("| --- | --- | --- | ---: | ---: | ---: | ---: |")
        for row in segmented.get("segment_rows", []):
            lines.append(
                f"| {row.get('segment')} | {row.get('decision')} | {row.get('severity')} | "
                f"{(row.get('baseline_share') or 0):.3f} | {(row.get('candidate_share') or 0):.3f} | "
                f"{row.get('baseline_total_decisions') or 0} | {row.get('candidate_total_decisions') or 0} |"
            )
        lines.append("")

    return "\n".join(lines)
