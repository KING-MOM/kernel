from __future__ import annotations

from scripts.runtime_sender_http import _extract_path


def test_extract_path_reads_top_level_value() -> None:
    assert _extract_path({"message_id": "abc123"}, "message_id") == "abc123"


def test_extract_path_reads_nested_value() -> None:
    data = {"payload": {"result": {"messageId": "abc123"}}}
    assert _extract_path(data, "payload.result.messageId") == "abc123"


def test_extract_path_returns_none_for_missing_path() -> None:
    assert _extract_path({"payload": {}}, "payload.result.messageId") is None
