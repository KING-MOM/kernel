from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict


REVIEW_PACKAGE_SCHEMA_VERSION = "1.0"
REVIEW_WORKFLOW_VERSION = "1.0"
REQUIRED_PROVENANCE_FIELDS = ("policy_version", "parameter_set_version", "corpus_id")


def validate_provenance(provenance: Dict[str, Any]) -> None:
    missing = [field for field in REQUIRED_PROVENANCE_FIELDS if not provenance.get(field)]
    if missing:
        raise ValueError(f"Missing required provenance fields: {', '.join(missing)}")


def _json_dump(obj: Dict[str, Any], path: Path) -> None:
    # Deterministic JSON: stable key order, stable indentation, trailing newline.
    path.write_text(json.dumps(obj, indent=2, sort_keys=True, ensure_ascii=True) + "\n")


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256_file(path: Path) -> str:
    return _sha256_bytes(path.read_bytes())


def write_review_package(
    *,
    out_dir: Path,
    report: Dict[str, Any],
    report_markdown: str,
    comparison: Dict[str, Any],
    promotion: Dict[str, Any],
    segmented_comparison: Dict[str, Any] | None = None,
    segmented_promotion: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    provenance = report.get("provenance", {})
    validate_provenance(provenance)

    out_dir.mkdir(parents=True, exist_ok=True)

    files: Dict[str, Path] = {
        "comparison_json": out_dir / "comparison.json",
        "promotion_json": out_dir / "promotion.json",
        "report_json": out_dir / "report.json",
        "report_md": out_dir / "report.md",
    }
    if segmented_comparison is not None:
        files["segmented_comparison_json"] = out_dir / "segmented_comparison.json"
    if segmented_promotion is not None:
        files["segmented_promotion_json"] = out_dir / "segmented_promotion.json"

    _json_dump(comparison, files["comparison_json"])
    _json_dump(promotion, files["promotion_json"])
    if segmented_comparison is not None:
        _json_dump(segmented_comparison, files["segmented_comparison_json"])
    if segmented_promotion is not None:
        _json_dump(segmented_promotion, files["segmented_promotion_json"])
    _json_dump(report, files["report_json"])
    files["report_md"].write_text(report_markdown)

    file_entries: Dict[str, Dict[str, Any]] = {}
    for key in sorted(files.keys()):
        path = files[key]
        file_entries[key] = {
            "name": path.name,
            "sha256": _sha256_file(path),
            "bytes": path.stat().st_size,
        }

    package_hash_payload = "".join(f"{k}:{v['sha256']}" for k, v in sorted(file_entries.items()))
    package_hash = _sha256_bytes(package_hash_payload.encode("utf-8"))

    manifest = {
        "review_package_schema_version": REVIEW_PACKAGE_SCHEMA_VERSION,
        "review_workflow_version": REVIEW_WORKFLOW_VERSION,
        "report_schema_version": report.get("report_schema_version", "unknown"),
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "provenance": provenance,
        "package_hash": package_hash,
        "files": file_entries,
    }

    manifest_path = out_dir / "manifest.json"
    _json_dump(manifest, manifest_path)
    manifest["manifest_path"] = str(manifest_path)
    return manifest
