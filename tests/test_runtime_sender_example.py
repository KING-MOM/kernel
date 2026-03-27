from __future__ import annotations

import json
import subprocess


def test_runtime_sender_example_returns_contract_json() -> None:
    payload = {
        "agent_id": "runtime-agent",
        "person_id": "person:+5215554540593",
        "channel": "whatsapp",
        "target": "+5215554540593",
        "message": "Hola Fernando",
        "action": "SEND_FULFILLMENT",
        "reason": "Pay debt",
        "ts": "2026-03-27T12:00:00Z",
        "parent_message_id": None,
    }

    result = subprocess.run(
        ["python3", "scripts/runtime_sender_example.py"],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        check=True,
        cwd="/Users/mau/Documents/New project/kernel",
    )

    data = json.loads(result.stdout)
    assert data["message_id"].startswith("example-")
    assert data["delivered"] is True
    assert data["runtime"] == "example"
    assert data["echo"]["person_id"] == "person:+5215554540593"
