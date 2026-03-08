import json
from pathlib import Path

import pytest

from app.kernel.authorization import (
    build_review_status,
    check_promotion_authorization,
    write_review_status,
)


def _manifest(package_hash: str = "abc123"):
    return {
        "review_workflow_version": "1.0",
        "report_schema_version": "1.0",
        "package_hash": package_hash,
        "provenance": {
            "policy_version": "v1.2",
            "parameter_set_version": "pset-1",
            "corpus_id": "corpus-1",
        },
    }


def test_build_review_status_requires_rationale_for_approved():
    with pytest.raises(ValueError):
        build_review_status(
            manifest=_manifest(),
            status="APPROVED",
            reviewer_id="alice",
            rationale="",
        )


def test_check_promotion_authorization_approved_hash_match():
    manifest = _manifest("hash-x")
    review = build_review_status(
        manifest=manifest,
        status="APPROVED",
        reviewer_id="alice",
        rationale="metrics improved and guardrails passed",
    )
    result = check_promotion_authorization(manifest=manifest, review_status=review)
    assert result["authorized"] is True


def test_check_promotion_authorization_rejects_hash_mismatch():
    manifest = _manifest("hash-a")
    review = build_review_status(
        manifest=_manifest("hash-b"),
        status="APPROVED",
        reviewer_id="alice",
        rationale="ok",
    )
    result = check_promotion_authorization(manifest=manifest, review_status=review)
    assert result["authorized"] is False
    assert result["reason"] == "package_hash_mismatch"


def test_write_review_status_persists_deterministic_json(tmp_path: Path):
    manifest_path = tmp_path / "manifest.json"
    out_path = tmp_path / "review_status.json"
    manifest_path.write_text(json.dumps(_manifest(), sort_keys=True) + "\n")

    write_review_status(
        manifest_path=manifest_path,
        out_path=out_path,
        status="REJECTED",
        reviewer_id="bob",
        rationale="negative signal worsened in dormant segment",
    )
    payload = json.loads(out_path.read_text())
    assert payload["status"] == "REJECTED"
    assert payload["package_hash"] == "abc123"
    assert out_path.read_text().endswith("\n")
