from __future__ import annotations

import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

POST_RUN_BUNDLE_SCHEMA_VERSION = "1.0"


def _json_dump(obj: Dict[str, Any], path: Path) -> None:
    path.write_text(json.dumps(obj, indent=2, sort_keys=True, ensure_ascii=True) + "\n")


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_post_run_bundle(
    *,
    out_dir: Path,
    report_json: Dict[str, Any],
    report_markdown: str,
    artifact_paths: Dict[str, Path],
) -> Dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)

    written: Dict[str, Path] = {}
    for name, src in sorted(artifact_paths.items()):
        if src is None:
            continue
        dest = out_dir / src.name
        shutil.copy2(src, dest)
        written[name] = dest

    report_json_path = out_dir / "live_ops_report.json"
    report_md_path = out_dir / "live_ops_report.md"
    _json_dump(report_json, report_json_path)
    report_md_path.write_text(report_markdown)
    written["live_ops_report_json"] = report_json_path
    written["live_ops_report_md"] = report_md_path

    files: Dict[str, Dict[str, Any]] = {}
    for key in sorted(written.keys()):
        p = written[key]
        files[key] = {
            "name": p.name,
            "sha256": _sha256_file(p),
            "bytes": p.stat().st_size,
        }

    package_hash_payload = "".join(f"{k}:{v['sha256']}" for k, v in sorted(files.items()))
    package_hash = hashlib.sha256(package_hash_payload.encode("utf-8")).hexdigest()

    launch = report_json.get("launch_provenance", {})
    manifest = {
        "post_run_bundle_schema_version": POST_RUN_BUNDLE_SCHEMA_VERSION,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "package_hash": package_hash,
        "experiment_state": report_json.get("experiment_state"),
        "launch_provenance": {
            "package_hash": launch.get("package_hash"),
            "policy_version": launch.get("policy_version"),
            "parameter_set_version": launch.get("parameter_set_version"),
            "corpus_id": launch.get("corpus_id"),
            "cohort": launch.get("cohort"),
            "experiment_arm": launch.get("experiment_arm"),
        },
        "files": files,
    }
    manifest_path = out_dir / "post_run_manifest.json"
    _json_dump(manifest, manifest_path)
    manifest["manifest_path"] = str(manifest_path)
    return manifest
