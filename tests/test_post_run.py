import json
from pathlib import Path

from app.kernel.post_run import write_post_run_bundle


def test_write_post_run_bundle(tmp_path: Path):
    state_file = tmp_path / "experiment_state.json"
    launch_file = tmp_path / "launch_gate.json"
    evals_file = tmp_path / "guardrail_evals.json"
    state_file.write_text("{}\n")
    launch_file.write_text('{"package_hash":"pkg-1"}\n')
    evals_file.write_text("[]\n")

    report_json = {
        "experiment_state": "COMPLETED",
        "launch_provenance": {
            "package_hash": "pkg-1",
            "policy_version": "v1.2",
            "parameter_set_version": "pset-1",
            "corpus_id": "corpus-a",
            "cohort": "10pct",
            "experiment_arm": "candidate",
        },
    }
    report_md = "# Live Ops Report\n"

    manifest = write_post_run_bundle(
        out_dir=tmp_path / "bundle",
        report_json=report_json,
        report_markdown=report_md,
        artifact_paths={
            "state_file": state_file,
            "launch_gate": launch_file,
            "guardrail_evals": evals_file,
        },
    )

    manifest_path = Path(manifest["manifest_path"])
    assert manifest_path.exists()
    persisted = json.loads(manifest_path.read_text())
    assert persisted["post_run_bundle_schema_version"] == "1.0"
    assert persisted["package_hash"] == manifest["package_hash"]
    assert "live_ops_report_json" in persisted["files"]
    assert "launch_gate" in persisted["files"]
