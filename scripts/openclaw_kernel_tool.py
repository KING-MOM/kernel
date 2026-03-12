#!/usr/bin/env python3
"""OpenClaw Kernel tool wrapper — CLI for interacting with the Kernel API."""
import argparse
import json
import os
import sys
import warnings
from typing import Any, Dict, List, Optional

warnings.filterwarnings(
    "ignore",
    message=r".*urllib3 v2 only supports OpenSSL 1\.1\.1\+.*",
    category=Warning,
)

import requests

DEFAULT_URL = "http://localhost:8088"

# OpenClaw skill manifest for auto-discovery
MANIFEST = {
    "name": "kernel",
    "description": "Relationship physics engine — decides when to proactively reach out to people",
    "version": "0.2.0",
    "commands": [
        {"name": "sweep", "description": "Get all relationships ready for action right now"},
        {"name": "decide", "description": "Check if agent should contact a specific person"},
        {"name": "decide-batch", "description": "Check multiple people at once"},
        {"name": "inbound", "description": "Record an incoming message"},
        {"name": "outbound", "description": "Record a sent message"},
        {"name": "outcome", "description": "Record message outcome (replied, opened)"},
        {"name": "stats", "description": "Get agent dashboard stats"},
        {"name": "persons", "description": "List all tracked persons"},
        {"name": "relationships", "description": "List all relationships with filtering"},
    ],
}


def get_base_url() -> str:
    return os.getenv("KERNEL_API_URL", DEFAULT_URL).rstrip("/")


def get_api_key() -> Optional[str]:
    return os.getenv("KERNEL_API_KEY")


def request_json(method: str, path: str, payload: Optional[Dict[str, Any]] = None, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    url = f"{get_base_url()}{path}"
    headers = {"Content-Type": "application/json"}
    api_key = get_api_key()
    if api_key:
        headers["X-API-Key"] = api_key

    resp = requests.request(method, url, headers=headers, json=payload, params=params, timeout=15)
    if not resp.ok:
        raise SystemExit(f"Kernel API error {resp.status_code}: {resp.text}")
    return resp.json()


def cmd_manifest(args: argparse.Namespace) -> None:
    print(json.dumps(MANIFEST, indent=2))


def cmd_inbound(args: argparse.Namespace) -> None:
    payload = {
        "agent_id": args.agent_id,
        "person_id": args.person_id,
        "email": args.email,
        "name": args.name,
        "timezone": args.timezone,
        "message_id": args.message_id,
        "subject": args.subject,
        "snippet": args.snippet,
        "channel": args.channel,
        "ts": args.ts,
    }
    data = request_json("POST", "/v1/relationships/events/inbound", payload)
    print(json.dumps(data))


def cmd_outbound(args: argparse.Namespace) -> None:
    payload = {
        "agent_id": args.agent_id,
        "person_id": args.person_id,
        "email": args.email,
        "name": args.name,
        "timezone": args.timezone,
        "message_id": args.message_id,
        "action": args.action,
        "reason": args.reason,
        "parent_message_id": args.parent_message_id,
        "channel": args.channel,
        "ts": args.ts,
    }
    data = request_json("POST", "/v1/relationships/events/outbound", payload)
    print(json.dumps(data))


def cmd_decide(args: argparse.Namespace) -> None:
    payload = {
        "agent_id": args.agent_id,
        "person_id": args.person_id,
        "ts": args.ts,
    }
    data = request_json("POST", "/v1/relationships/decide", payload)
    print(json.dumps(data, indent=2))


def cmd_decide_batch(args: argparse.Namespace) -> None:
    payload = {
        "agent_id": args.agent_id,
        "person_ids": args.person_ids,
        "ts": args.ts,
    }
    data = request_json("POST", "/v1/relationships/decide/batch", payload)
    print(json.dumps(data, indent=2))


def cmd_sweep(args: argparse.Namespace) -> None:
    payload = {
        "agent_id": args.agent_id,
        "ts": args.ts,
        "max_results": args.max_results,
    }
    data = request_json("POST", "/v1/relationships/sweep", payload)
    print(json.dumps(data, indent=2))


def cmd_outcome(args: argparse.Namespace) -> None:
    payload = {"outbox_id": args.outbox_id}
    if args.delivered is not None:
        payload["delivered"] = args.delivered
    if args.replied_at:
        payload["replied_at"] = args.replied_at
    if args.reply_sentiment is not None:
        payload["reply_sentiment"] = args.reply_sentiment
    data = request_json("POST", "/v1/relationships/events/outcome", payload)
    print(json.dumps(data))


def cmd_stats(args: argparse.Namespace) -> None:
    data = request_json("GET", "/v1/stats", params={"agent_id": args.agent_id})
    print(json.dumps(data, indent=2))


def cmd_persons(args: argparse.Namespace) -> None:
    params = {"agent_id": args.agent_id, "skip": args.skip, "limit": args.limit}
    data = request_json("GET", "/v1/persons", params=params)
    print(json.dumps(data, indent=2))


def cmd_relationships(args: argparse.Namespace) -> None:
    params = {"agent_id": args.agent_id, "skip": args.skip, "limit": args.limit}
    if args.stage:
        params["stage"] = args.stage
    if args.sort_by:
        params["sort_by"] = args.sort_by
    data = request_json("GET", "/v1/relationships", params=params)
    print(json.dumps(data, indent=2))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="OpenClaw Kernel tool wrapper")
    sub = parser.add_subparsers(dest="command", required=True)

    # manifest
    manifest = sub.add_parser("manifest", help="Print skill manifest JSON")
    manifest.set_defaults(func=cmd_manifest)

    # inbound
    inbound = sub.add_parser("inbound")
    inbound.add_argument("--agent-id", required=True)
    inbound.add_argument("--person-id", required=True)
    inbound.add_argument("--message-id", required=True)
    inbound.add_argument("--ts", required=True)
    inbound.add_argument("--email")
    inbound.add_argument("--name")
    inbound.add_argument("--timezone")
    inbound.add_argument("--subject")
    inbound.add_argument("--snippet")
    inbound.add_argument("--channel", default="email")
    inbound.set_defaults(func=cmd_inbound)

    # outbound
    outbound = sub.add_parser("outbound")
    outbound.add_argument("--agent-id", required=True)
    outbound.add_argument("--person-id", required=True)
    outbound.add_argument("--message-id", required=True)
    outbound.add_argument("--action", required=True)
    outbound.add_argument("--reason", required=True)
    outbound.add_argument("--ts", required=True)
    outbound.add_argument("--email")
    outbound.add_argument("--name")
    outbound.add_argument("--timezone")
    outbound.add_argument("--parent-message-id")
    outbound.add_argument("--channel", default="email")
    outbound.set_defaults(func=cmd_outbound)

    # decide
    decide = sub.add_parser("decide")
    decide.add_argument("--agent-id", required=True)
    decide.add_argument("--person-id", required=True)
    decide.add_argument("--ts", required=True)
    decide.set_defaults(func=cmd_decide)

    # decide-batch
    decide_batch = sub.add_parser("decide-batch")
    decide_batch.add_argument("--agent-id", required=True)
    decide_batch.add_argument("--person-ids", required=True, nargs="+")
    decide_batch.add_argument("--ts", required=True)
    decide_batch.set_defaults(func=cmd_decide_batch)

    # sweep
    sweep = sub.add_parser("sweep", help="Find all relationships ready for action")
    sweep.add_argument("--agent-id", required=True)
    sweep.add_argument("--ts", required=True)
    sweep.add_argument("--max-results", type=int, default=50)
    sweep.set_defaults(func=cmd_sweep)

    # outcome
    outcome = sub.add_parser("outcome", help="Record message outcome")
    outcome.add_argument("--outbox-id", required=True)
    outcome.add_argument("--delivered", type=bool)
    outcome.add_argument("--replied-at")
    outcome.add_argument("--reply-sentiment", type=float)
    outcome.set_defaults(func=cmd_outcome)

    # stats
    stats = sub.add_parser("stats", help="Get agent stats")
    stats.add_argument("--agent-id", required=True)
    stats.set_defaults(func=cmd_stats)

    # persons
    persons = sub.add_parser("persons", help="List persons")
    persons.add_argument("--agent-id", required=True)
    persons.add_argument("--skip", type=int, default=0)
    persons.add_argument("--limit", type=int, default=50)
    persons.set_defaults(func=cmd_persons)

    # relationships
    rels = sub.add_parser("relationships", help="List relationships")
    rels.add_argument("--agent-id", required=True)
    rels.add_argument("--stage")
    rels.add_argument("--sort-by", default="engagement_score")
    rels.add_argument("--skip", type=int, default=0)
    rels.add_argument("--limit", type=int, default=50)
    rels.set_defaults(func=cmd_relationships)

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
