#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict

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


def _send_via_openclaw(channel: str, target: str, message: str, dry_run: bool) -> Dict[str, Any]:
    cmd = [
        "openclaw",
        "message",
        "send",
        "--channel",
        channel,
        "--target",
        target,
        "--message",
        message,
        "--json",
    ]
    if dry_run:
        cmd.append("--dry-run")
    result = subprocess.run(cmd, check=True, capture_output=True, text=True)
    stdout = result.stdout.strip()
    if not stdout:
        raise RuntimeError("openclaw send returned empty output")
    return json.loads(stdout)


def _message_id_from_send_result(channel: str, send_result: Dict[str, Any]) -> str:
    message_id = (
        send_result.get("payload", {})
        .get("result", {})
        .get("messageId")
    )
    if not message_id:
        raise RuntimeError("send result missing payload.result.messageId")
    return f"{channel}:{message_id}"


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


def main() -> int:
    parser = argparse.ArgumentParser(description="Send through OpenClaw and persist Kernel outbound + bridge attribution.")
    parser.add_argument("--agent-id", required=True)
    parser.add_argument("--channel", required=True)
    parser.add_argument("--target", required=True, help="Rail-native destination (for example +521... for WhatsApp).")
    parser.add_argument("--message", required=True)
    parser.add_argument("--action", required=True, help="Kernel action to record, for example SEND_FULFILLMENT.")
    parser.add_argument("--reason", required=True, help="Kernel reason to record.")
    parser.add_argument("--ts", required=True, help="ISO8601 timestamp for Kernel outbound.")
    parser.add_argument("--person-id", help="Canonical Kernel person id. Defaults from channel+target.")
    parser.add_argument("--parent-message-id")
    parser.add_argument("--kernel-url", default=_default_kernel_url())
    parser.add_argument("--kernel-api-key", default=os.getenv("KERNEL_API_KEY"))
    parser.add_argument("--bridge-state-path", default=str(_default_bridge_state_path()))
    parser.add_argument("--no-delivered", action="store_true", help="Skip immediate delivered outcome write.")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    person_id = args.person_id or _canonical_person_id(args.channel, args.target)
    bridge_state_path = Path(args.bridge_state_path)
    client = KernelClient(base_url=args.kernel_url, api_key=args.kernel_api_key)

    send_result = _send_via_openclaw(args.channel, args.target, args.message, args.dry_run)
    if args.dry_run:
        print(
            json.dumps(
                {
                    "mode": "dry_run",
                    "person_id": person_id,
                    "send_result": send_result,
                },
                indent=2,
            )
        )
        return 0

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

    mark_delivered = not args.no_delivered
    if mark_delivered:
        client.outcome(outbox_id=outbox_id, delivered=True)

    _record_bridge_history(bridge_state_path, person_id, outbox_id, mark_delivered)

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
