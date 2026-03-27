#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
import uuid
from typing import Any, Dict


def _read_payload() -> Dict[str, Any]:
    raw = sys.stdin.read()
    if not raw.strip():
        raise SystemExit("runtime_sender_example.py expected JSON on stdin")
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise SystemExit("runtime_sender_example.py expected a JSON object")
    return data


def main() -> int:
    payload = _read_payload()

    # Replace this block with your real runtime send call.
    result = {
        "message_id": f"example-{uuid.uuid4()}",
        "delivered": True,
        "runtime": "example",
        "echo": {
            "agent_id": payload.get("agent_id"),
            "person_id": payload.get("person_id"),
            "channel": payload.get("channel"),
            "target": payload.get("target"),
        },
    }
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
