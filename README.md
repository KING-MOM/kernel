# Kernel API

Relationship physics engine for AI agents. Decides **when** to proactively reach out to people based on trust, tension, engagement, and temporal patterns. Kernel is runtime-agnostic and can sit next to OpenClaw or any other agent runtime.

## Quick Start

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8088
```

## Docker

```bash
docker-compose up --build
```

Kernel available at `http://localhost:8088`.

Supported transport channels in the current API:
- `email`
- `sms`
- `whatsapp`
- `voice_call`
- `telegram`

Check health:

```bash
curl -s http://localhost:8088/health
```

## Core Concepts

- **Intent Debt**: Someone messaged you — you owe them a response
- **Interaction Tension**: Increases with outbound messages, decays over time
- **Trust Score**: Builds with each interaction (0.0 - 1.0)
- **Engagement Score**: Composite metric (0 - 100) from recency, reciprocity, trust
- **Churn Risk**: Probability of relationship going dormant (0.0 - 1.0)
- **Golden Hours**: Learned optimal contact windows per person
- **Lifecycle Stages**: onboarded → warm → engaged → value_delivered → dormant → churned

## Theory

- Math + hypotheses (objective functions, constraints, decay, aggregation):
  - [docs/KERNEL_MATH_AND_HYPOTHESES.md](/Users/mau/Documents/New project/kernel/docs/KERNEL_MATH_AND_HYPOTHESES.md)
- Multichannel persistence and cross-rail identity model:
  - [docs/MULTICHANNEL_PERSISTENCE_MODEL.md](/Users/mau/Documents/New project/kernel/docs/MULTICHANNEL_PERSISTENCE_MODEL.md)
- Live rollout control policy:
  - [docs/LIVE_ROLLOUT_CONTROLS.md](/Users/mau/Documents/New project/kernel/docs/LIVE_ROLLOUT_CONTROLS.md)
- Ops execution artifacts:
  - [docs/OPS_RUNBOOK_V1.md](/Users/mau/Documents/New project/kernel/docs/OPS_RUNBOOK_V1.md)
  - [docs/FIRST_CONTROLLED_PROD_RUN.md](/Users/mau/Documents/New project/kernel/docs/FIRST_CONTROLLED_PROD_RUN.md)
  - [docs/POST_RUN_BUNDLE_PIPELINE.md](/Users/mau/Documents/New project/kernel/docs/POST_RUN_BUNDLE_PIPELINE.md)

## API (v1)

### Write Endpoints

| Endpoint | Purpose |
|----------|---------|
| `POST /v1/relationships/events/inbound` | Record incoming message |
| `POST /v1/relationships/events/outbound` | Record sent message (returns `outbox_id`) |
| `POST /v1/relationships/events/outcome` | Record delivery/reply outcome |
| `POST /v1/relationships/decide` | Get action for one person |
| `POST /v1/relationships/decide/batch` | Get actions for multiple people |
| `POST /v1/relationships/sweep` | Get all relationships ready for action |

### Read Endpoints

| Endpoint | Purpose |
|----------|---------|
| `GET /v1/persons?agent_id=...` | List persons (paginated) |
| `GET /v1/persons/{external_id}?agent_id=...` | Get person details |
| `GET /v1/relationships?agent_id=...` | List relationships (filter, sort, paginate) |
| `GET /v1/relationships/{id}` | Get relationship state |
| `GET /v1/relationships/{id}/events` | Event history |
| `GET /v1/stats?agent_id=...` | Dashboard stats |

### Decide Response (enriched)

```json
{
  "action": "SEND_FULFILLMENT",
  "reason": "Paying debt",
  "confidence": 0.9,
  "relationship_stage": "warm",
  "engagement_score": 72.5,
  "churn_risk": 0.1,
  "next_decision_at": "2026-03-06T12:00:00Z",
  "golden_hours": [{"day_of_week": 0, "hour_utc": 10}]
}
```

### Sweep (proactive heartbeat)

Call on a cron schedule to find relationships needing action:

```bash
curl -X POST http://localhost:8088/v1/relationships/sweep \
  -H "Content-Type: application/json" \
  -d '{"agent_id": "openclaw-main", "ts": "2026-03-05T19:00:00Z"}'
```

## OpenClaw Tool Wrapper

```bash
export KERNEL_API_URL=http://localhost:8088
python scripts/openclaw_kernel_tool.py sweep --agent-id openclaw-main --ts 2026-03-05T19:00:00Z
python scripts/openclaw_kernel_tool.py stats --agent-id openclaw-main
python scripts/openclaw_kernel_tool.py manifest  # Print OpenClaw skill manifest
```

Inbound/outbound events can carry an explicit channel. Example voice call logging:

```bash
python scripts/openclaw_kernel_tool.py inbound \
  --agent-id openclaw-main \
  --person-id call:+15551234567 \
  --message-id call-001 \
  --channel voice_call \
  --ts 2026-03-07T19:00:00Z
```

## Agent SDK Usage

Kernel is ready to be used by other agents as a relationship SDK/service.

Blessed integration surfaces:
- HTTP API
- CLI wrapper
- Python client: [app/kernel/client.py](/Users/mau/Documents/New project/kernel/app/kernel/client.py)

Integrator guide:
- [docs/AGENT_SDK_INTEGRATION.md](/Users/mau/Documents/New project/kernel/docs/AGENT_SDK_INTEGRATION.md)
- [docs/MULTICHANNEL_PERSISTENCE_MODEL.md](/Users/mau/Documents/New project/kernel/docs/MULTICHANNEL_PERSISTENCE_MODEL.md)

Minimal Python example:

```python
from app.kernel.client import KernelClient

client = KernelClient(base_url="http://127.0.0.1:8088")

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

Reference execution adapter for OpenClaw rails + Kernel attribution:

```bash
python scripts/openclaw_execute_send.py \
  --agent-id openclaw-main \
  --channel whatsapp \
  --target +5215560663926 \
  --message "German, una disculpa por dejar esto colgado." \
  --action SEND_FULFILLMENT \
  --reason "Kernel controlled execution" \
  --ts 2026-03-27T12:00:00Z
```

For other runtimes, implement the same execution bridge contract:

1. send through the real rail
2. record Kernel outbound with the real message id
3. keep local attribution state for `outbox_id`
4. record delivery/reply outcomes back into Kernel

Primary generic runtime adapter:

```bash
python scripts/runtime_execute_send.py \
  --agent-id runtime-agent \
  --channel whatsapp \
  --target +5215554540593 \
  --message "Hola Fernando" \
  --action SEND_FULFILLMENT \
  --reason "Kernel controlled execution" \
  --ts 2026-03-27T12:00:00Z \
  --sender-cmd -- python /path/to/runtime_sender.py
```

`scripts/claude_execute_send.py` remains available as a compatibility wrapper if a Claude-based runtime wants a named entrypoint, but `scripts/runtime_execute_send.py` is the main generic path.

Template sender for local/runtime integration testing:

- [scripts/runtime_sender_example.py](/Users/mau/Documents/New project/kernel/scripts/runtime_sender_example.py)

## First End-to-End Sweep Test

Start from a clean local DB and run one inbound + sweep cycle:

```bash
rm -f kernel.db
uvicorn app.main:app --host 0.0.0.0 --port 8088
```

In another terminal:

```bash
export KERNEL_API_URL=http://localhost:8088

# If KERNEL_API_KEY is configured on the server, set the same value here.
# export KERNEL_API_KEY=your-secret-key-here

python scripts/openclaw_kernel_tool.py inbound \
  --agent-id openclaw-main \
  --person-id person-001 \
  --message-id msg-001 \
  --email person@example.com \
  --ts 2026-03-07T19:00:00Z

python scripts/openclaw_kernel_tool.py sweep \
  --agent-id openclaw-main \
  --ts 2026-03-07T19:05:00Z
```

## Auth

`KERNEL_API_KEY` is optional.
- If unset, API routes are open locally.
- If set, requests must include matching `X-API-Key` header (the wrapper reads `KERNEL_API_KEY` from env).

## Configuration

All physics constants configurable via environment variables:

```bash
LAMBDA_DECAY=0.15          # Tension decay rate
MAX_TENSION=0.85           # Maximum tension threshold
MIN_COOLDOWN_HOURS=24.0    # Minimum hours between outbound messages
LOG_LEVEL=INFO
LOG_FORMAT=json            # json or text
```

Per-agent overrides via the `PhysicsConfig` table.

Project-wide persistent parameter ops (outside this repo):
- `../ops/KERNEL_PARAMETER_SYSTEM.md`
- `../ops/KERNEL_PARAMETER_REGISTRY.md`
- `../ops/KERNEL_PARAMETER_CHANGELOG.md`
- `../ops/KERNEL_EXPERIMENT_QUEUE.md`

## Tests

```bash
python -m pytest -v
```
