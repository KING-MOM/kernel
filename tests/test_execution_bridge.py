from __future__ import annotations

import json
from pathlib import Path

from scripts.openclaw_execute_send import (
    _canonical_person_id,
    _load_bridge_state,
    _message_id_from_send_result,
    _record_bridge_history,
)


def test_canonical_person_id_maps_supported_channels() -> None:
    assert _canonical_person_id("whatsapp", "+5215554540593") == "person:+5215554540593"
    assert _canonical_person_id("voice_call", "+5215554540593") == "person:+5215554540593"
    assert _canonical_person_id("telegram", "user-123") == "telegram:user-123"


def test_load_bridge_state_recovers_from_invalid_json(tmp_path: Path) -> None:
    state_path = tmp_path / "kernel-bridge-state.json"
    state_path.write_text("{not-json")

    state = _load_bridge_state(state_path)

    assert state == {"pendingByKey": {}, "personHistory": {}}


def test_record_bridge_history_truncates_to_latest_entries(tmp_path: Path) -> None:
    state_path = tmp_path / "kernel-bridge-state.json"
    person_id = "person:+5215554540593"
    seed = {
        "pendingByKey": {},
        "personHistory": {
            person_id: [
                {
                    "outboxId": f"old-{idx}",
                    "createdAt": idx,
                    "deliveredAt": None,
                    "repliedAt": None,
                }
                for idx in range(205)
            ]
        },
    }
    state_path.write_text(json.dumps(seed))

    _record_bridge_history(state_path, person_id, "newest", mark_delivered=True)

    state = json.loads(state_path.read_text())
    history = state["personHistory"][person_id]
    assert len(history) == 200
    assert history[0]["outboxId"] == "old-6"
    assert history[-1]["outboxId"] == "newest"
    assert history[-1]["deliveredAt"] is not None


def test_message_id_from_send_result_uses_provider_message_id() -> None:
    send_result = {"payload": {"result": {"messageId": "abc123"}}}

    assert _message_id_from_send_result("whatsapp", send_result) == "whatsapp:abc123"
