#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any, Dict, Optional

import requests


def _read_payload() -> Dict[str, Any]:
    raw = sys.stdin.read()
    if not raw.strip():
        raise SystemExit("runtime_sender_http.py expected JSON on stdin")
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise SystemExit("runtime_sender_http.py expected a JSON object")
    return data


def _extract_path(data: Dict[str, Any], path: str) -> Optional[Any]:
    current: Any = data
    for part in path.split("."):
        if not isinstance(current, dict) or part not in current:
            return None
        current = current[part]
    return current


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Send a runtime payload to an HTTP endpoint and normalize the response to Kernel's sender contract."
    )
    parser.add_argument("--url", default=os.getenv("RUNTIME_SENDER_URL"))
    parser.add_argument("--api-key", default=os.getenv("RUNTIME_SENDER_API_KEY"))
    parser.add_argument("--message-id-path", default=os.getenv("RUNTIME_SENDER_MESSAGE_ID_PATH", "message_id"))
    parser.add_argument("--delivered-path", default=os.getenv("RUNTIME_SENDER_DELIVERED_PATH", "delivered"))
    parser.add_argument("--timeout", type=float, default=float(os.getenv("RUNTIME_SENDER_TIMEOUT", "15")))
    args = parser.parse_args()
    if not args.url:
        raise SystemExit("--url or RUNTIME_SENDER_URL is required")
    return args


def main() -> int:
    args = _parse_args()
    payload = _read_payload()

    headers = {"Content-Type": "application/json"}
    if args.api_key:
        headers["Authorization"] = f"Bearer {args.api_key}"

    response = requests.post(args.url, headers=headers, json=payload, timeout=args.timeout)
    response.raise_for_status()
    data = response.json()
    if not isinstance(data, dict):
        raise SystemExit("runtime sender endpoint must return a JSON object")

    message_id = _extract_path(data, args.message_id_path)
    if not message_id:
        raise SystemExit(f"message id not found at path: {args.message_id_path}")

    delivered = _extract_path(data, args.delivered_path)
    normalized = {
        "message_id": str(message_id),
        "delivered": bool(delivered) if delivered is not None else True,
        "runtime": "http",
        "raw_response": data,
    }
    print(json.dumps(normalized))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
