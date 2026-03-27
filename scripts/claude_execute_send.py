#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.kernel.client import KernelClient
from app.kernel.identities import canonical_person_external_id


def _default_kernel_url() -> str:
    return os.getenv("KERNEL_API_URL", "http://127.0.0.1:8088")


def _default_bridge_state_path() -> Path:
    return Path.home() / ".openclaw" / "workspace" / "memory" / "kernel-bridge-state.json"


def _load_bridge_state(path: Path) -> Dict[str, Any]:
    try:
        data = json.loads(path.read_text())
        if not isinstance(data, dict):
            raise ValueError("invalid bridge state")
        return {
            "pendingByKey": data.get("pendingByKey") if isinstance(data.get("pendingByKey"), dict) else {},
            "personHistory": data.get("personHistory") if isinstance(data.get("personHistory"), dict) else {},
        }
    except Exception:
        return {"pendingByKey": {}, "personHistory": {}}


def _write_bridge_state(path: Path, state: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, separators=(",", ":")))


def _canonical_person_id(channel: str, target: str) -> str:
    if channel == "whatsapp":
        return canonical_person_external_id(f"whatsapp:{target}")
    if channel == "voice_call":
        return canonical_person_external_id(f"voice:{target}")
    return f"{channel}:{target}"


def _record_bridge_history(path: Path, person_id: str, outbox_id: str, mark_delivered: bool) -> None:
    state = _load_bridge_state(path)
    history = state["personHistory"].setdefault(person_id, [])
    now_ms = int(time.time() * 1000)
    history.append(
        {
            "outboxId": outbox_id,
            "createdAt": now_ms,
            "deliveredAt": now_ms if mark_delivered else None,
            "repliedAt": None,
        }
    )
    state["personHistory"][person_id] = history[-200:]
    _write_bridge_state(path, state)


def _sender_payload(args: argparse.Namespace, person_id: str) -> Dict[str, Any]:
    return {
        "agent_id": args.agent_id,
        "person_id": person_id,
        "channel": args.channel,
        "target": args.target,
        "message": args.message,
        "action": args.action,
        "reason": args.reason,
        "ts": args.ts,
        "parent_message_id": args.parent_message_id,
    }


def _run_sender(sender_cmd: List[str], payload: Dict[str, Any]) -> Dict[str, Any]:
    if not sender_cmd:
        raise RuntimeError("sender command is required")
    result = subprocess.run(
        sender_cmd,
        input=json.dumps(payload),
        check=True,
        capture_output=True,
        text=True,
    )
    stdout = result.stdout.strip()
    if not stdout:
        raise RuntimeError("sender command returned empty output")
    data = json.loads(stdout)
    if not isinstance(data, dict):
        raise RuntimeError("sender command returned non-object JSON")
    return data


def _message_id_from_send_result(channel: str, send_result: Dict[str, Any]) -> str:
    message_id = send_result.get("message_id")
    if not message_id:
        raise RuntimeError("sender result missing message_id")
    return f"{channel}:{message_id}"


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Claude/runtime execution bridge: send through a runtime-specific sender command and persist Kernel outbound + attribution."
    )
    parser.add_argument("--agent-id", required=True)
    parser.add_argument("--channel", required=True)
    parser.add_argument("--target", required=True)
    parser.add_argument("--message", required=True)
    parser.add_argument("--action", required=True)
    parser.add_argument("--reason", required=True)
    parser.add_argument("--ts", required=True)
    parser.add_argument("--person-id")
    parser.add_argument("--parent-message-id")
    parser.add_argument("--kernel-url", default=_default_kernel_url())
    parser.add_argument("--kernel-api-key", default=os.getenv("KERNEL_API_KEY"))
    parser.add_argument("--bridge-state-path", default=str(_default_bridge_state_path()))
    parser.add_argument("--no-delivered", action="store_true")
    parser.add_argument(
        "--sender-cmd",
        nargs=argparse.REMAINDER,
        required=True,
        help="Command that reads a JSON payload from stdin and returns JSON with at least {'message_id': '...'} on stdout.",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    sender_cmd = args.sender_cmd
    if sender_cmd and sender_cmd[0] == "--":
        sender_cmd = sender_cmd[1:]

    person_id = args.person_id or _canonical_person_id(args.channel, args.target)
    bridge_state_path = Path(args.bridge_state_path)
    client = KernelClient(base_url=args.kernel_url, api_key=args.kernel_api_key)

    payload = _sender_payload(args, person_id)
    send_result = _run_sender(sender_cmd, payload)
    kernel_message_id = _message_id_from_send_result(args.channel, send_result)

    outbound = client.outbound(
        agent_id=args.agent_id,
        person_id=person_id,
        message_id=kernel_message_id,
        action=args.action,
        reason=args.reason,
        parent_message_id=args.parent_message_id,
        channel=args.channel,
        ts=args.ts,
    )
    outbox_id = outbound.get("outbox_id")
    if not outbox_id:
        raise RuntimeError("kernel outbound did not return outbox_id")

    delivered = bool(send_result.get("delivered", not args.no_delivered))
    if delivered:
        client.outcome(outbox_id=outbox_id, delivered=True)

    _record_bridge_history(bridge_state_path, person_id, outbox_id, delivered)

    print(
        json.dumps(
            {
                "mode": "sent",
                "person_id": person_id,
                "outbox_id": outbox_id,
                "message_id": kernel_message_id,
                "bridge_state_path": str(bridge_state_path),
                "send_result": send_result,
                "kernel_outbound": outbound,
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
