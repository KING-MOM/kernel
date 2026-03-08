from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict


REVIEW_STATUS_SCHEMA_VERSION = "1.0"
ALLOWED_REVIEW_STATUS = {"PENDING", "APPROVED", "REJECTED", "SUPERSEDED"}
RATIONALE_REQUIRED_STATUS = {"APPROVED", "REJECTED", "SUPERSEDED"}


def _json_dump(obj: Dict[str, Any], path: Path) -> None:
    path.write_text(json.dumps(obj, indent=2, sort_keys=True, ensure_ascii=True) + "\n")


def load_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text())


def build_review_status(
    *,
    manifest: Dict[str, Any],
    status: str,
    reviewer_id: str,
    rationale: str,
    reviewed_at_utc: str | None = None,
) -> Dict[str, Any]:
    normalized_status = status.upper().strip()
    if normalized_status not in ALLOWED_REVIEW_STATUS:
        raise ValueError(f"Invalid review status: {status}")
    if not reviewer_id.strip():
        raise ValueError("reviewer_id is required")
    if normalized_status in RATIONALE_REQUIRED_STATUS and not rationale.strip():
        raise ValueError(f"rationale is required for status {normalized_status}")

    if reviewed_at_utc is None:
        reviewed_at_utc = datetime.now(timezone.utc).isoformat()

    package_hash = manifest.get("package_hash")
    if not package_hash:
        raise ValueError("manifest missing package_hash")

    return {
        "review_status_schema_version": REVIEW_STATUS_SCHEMA_VERSION,
        "status": normalized_status,
        "reviewer_id": reviewer_id,
        "reviewed_at_utc": reviewed_at_utc,
        "rationale": rationale,
        "package_hash": package_hash,
        "review_workflow_version": manifest.get("review_workflow_version", "unknown"),
        "report_schema_version": manifest.get("report_schema_version", "unknown"),
        "provenance": manifest.get("provenance", {}),
    }


def write_review_status(
    *,
    manifest_path: Path,
    out_path: Path,
    status: str,
    reviewer_id: str,
    rationale: str,
) -> Dict[str, Any]:
    manifest = load_json(manifest_path)
    review = build_review_status(
        manifest=manifest,
        status=status,
        reviewer_id=reviewer_id,
        rationale=rationale,
    )
    _json_dump(review, out_path)
    return review


def check_promotion_authorization(*, manifest: Dict[str, Any], review_status: Dict[str, Any]) -> Dict[str, Any]:
    package_hash = manifest.get("package_hash")
    review_hash = review_status.get("package_hash")
    status = str(review_status.get("status", "")).upper().strip()
    rationale = str(review_status.get("rationale", "")).strip()

    if not package_hash:
        return {"authorized": False, "reason": "manifest_missing_package_hash"}
    if review_hash != package_hash:
        return {"authorized": False, "reason": "package_hash_mismatch"}
    if status not in ALLOWED_REVIEW_STATUS:
        return {"authorized": False, "reason": "invalid_review_status"}
    if status in RATIONALE_REQUIRED_STATUS and not rationale:
        return {"authorized": False, "reason": "missing_rationale"}
    if status != "APPROVED":
        return {"authorized": False, "reason": f"status_not_approved:{status}"}
    return {"authorized": True, "reason": "approved"}
