# Kernel API

Relationship physics engine for AI agents. Decides **when** to proactively reach out to people based on trust, tension, engagement, and temporal patterns. Designed to sit next to OpenClaw.

## Quick Start

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8080
```

## Docker

```bash
docker-compose up --build
```

Kernel available at `http://localhost:8088`.

## Core Concepts

- **Intent Debt**: Someone messaged you — you owe them a response
- **Interaction Tension**: Increases with outbound messages, decays over time
- **Trust Score**: Builds with each interaction (0.0 - 1.0)
- **Engagement Score**: Composite metric (0 - 100) from recency, reciprocity, trust
- **Churn Risk**: Probability of relationship going dormant (0.0 - 1.0)
- **Golden Hours**: Learned optimal contact windows per person
- **Lifecycle Stages**: onboarded → warm → engaged → value_delivered → dormant → churned

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

## Auth

Set `KERNEL_API_KEY` env var. Requests must include `X-API-Key` header.

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

## Tests

```bash
pytest -v  # 73 tests
```
