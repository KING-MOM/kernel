# Kernel Agent SDK Integration

Kernel is the relationship service for agents. Other agents should treat it as the source of truth for:

- when a relationship is due for action
- whether current contact pressure is healthy
- whether there is reply debt
- what action class is currently appropriate

## Blessed integration pattern

Use Kernel in this order:

1. Canonicalize identity before Kernel
2. Log real inbound/outbound/outcome events
3. Ask Kernel for `decide` or `sweep`
4. Execute through the real rail
5. Record delivery/reply outcomes back into Kernel

Do not bypass steps 2 or 5. That is how relationship state and outcome attribution drift.

## Canonical identity contract

Agents should always send:

- `person_id = person:+E164`

Examples:

- `person:+5215520453254`
- `person:+5215560663926`

Do not send transport-specific identities like:

- `whatsapp:+...`
- `voice:+...`

Channel belongs in event metadata, not in the person identity.

## Supported channels

- `whatsapp`
- `voice_call`
- `telegram`
- `sms`
- `email`

If a rail is not actually active in production, do not treat it as a meaningful preferred channel even if historical events still carry that label.

## Python SDK

Kernel ships a small Python client:

```python
from app.kernel.client import KernelClient

client = KernelClient(base_url="http://127.0.0.1:8088", api_key=None)

client.inbound(
    agent_id="openclaw-main",
    person_id="person:+5215560663926",
    message_id="whatsapp:abc123",
    snippet="Si hablar por telefono",
    channel="whatsapp",
    ts="2026-03-20T16:16:18Z",
)

decision = client.decide(
    agent_id="openclaw-main",
    person_id="person:+5215560663926",
    ts="2026-03-20T16:17:00Z",
)
```

## HTTP API

Primary endpoints:

- `POST /v1/relationships/events/inbound`
- `POST /v1/relationships/events/outbound`
- `POST /v1/relationships/events/outcome`
- `POST /v1/relationships/decide`
- `POST /v1/relationships/decide/batch`
- `POST /v1/relationships/sweep`

## CLI fallback

For shell-based agents or cron workers:

```bash
python scripts/openclaw_kernel_tool.py inbound ...
python scripts/openclaw_kernel_tool.py outbound ...
python scripts/openclaw_kernel_tool.py outcome ...
python scripts/openclaw_kernel_tool.py decide ...
python scripts/openclaw_kernel_tool.py sweep ...
```

## Controlled execution guidance

For new agents, start with:

- `SEND_FULFILLMENT`
- `SEND_WITH_APOLOGY`

Avoid full autonomous proactive outreach until the integration is stable.

Recommended rules:

1. never act on `OWNER_EXCLUDED`
2. never send if Kernel returns `WAIT`
3. never send from raw UUIDs; only use canonical `person:+...`
4. always write outbound before expecting reply attribution
5. always write outcome after delivery/reply if you execute outside the standard bridge

## Outcome attribution warning

If you send through a rail directly without the normal OpenClaw bridge bookkeeping, replies may update relationship state but fail to attach to the correct `outbox_id`.

So for any custom execution path:

1. send via real rail
2. record Kernel outbound immediately
3. keep bridge state or equivalent `outbox_id -> person` mapping
4. record Kernel outcome when reply arrives

## What Kernel is and is not

Kernel is:

- relationship timing
- contact-pressure management
- debt/tension/trust state
- decision recommendation

Kernel is not:

- content generation
- rail transport
- identity-resolution authority for transport-specific IDs
- full CRM memory for transcripts and call details

Use external memory layers for:

- call transcripts
- structured call logs
- contact operational state

Then feed distilled events and outcomes into Kernel.
