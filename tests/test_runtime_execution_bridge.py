from __future__ import annotations

from scripts.runtime_execute_send import (
    _canonical_person_id,
    _message_id_from_send_result,
    _sender_payload,
)


class _Args:
    agent_id = "runtime-agent"
    channel = "whatsapp"
    target = "+5215554540593"
    message = "Hola"
    action = "SEND_FULFILLMENT"
    reason = "Pay debt"
    ts = "2026-03-27T12:00:00Z"
    parent_message_id = "whatsapp:parent-1"


def test_sender_payload_contains_bridge_fields() -> None:
    payload = _sender_payload(_Args(), "person:+5215554540593")

    assert payload == {
        "agent_id": "runtime-agent",
        "person_id": "person:+5215554540593",
        "channel": "whatsapp",
        "target": "+5215554540593",
        "message": "Hola",
        "action": "SEND_FULFILLMENT",
        "reason": "Pay debt",
        "ts": "2026-03-27T12:00:00Z",
        "parent_message_id": "whatsapp:parent-1",
    }


def test_message_id_from_sender_result_requires_message_id() -> None:
    assert _message_id_from_send_result("whatsapp", {"message_id": "abc123"}) == "whatsapp:abc123"


def test_canonical_person_id_for_runtime_bridge() -> None:
    assert _canonical_person_id("whatsapp", "+5215554540593") == "person:+5215554540593"
    assert _canonical_person_id("voice_call", "+5215554540593") == "person:+5215554540593"
