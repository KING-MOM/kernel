---
name: kernel
description: Relationship physics engine — decides when an AI agent should proactively reach out to people based on trust, tension, engagement, and temporal patterns.
homepage: https://github.com/KING-MOM/kernel
user-invocable: false
metadata: {"openclaw":{"emoji":"🦞","os":["darwin","linux"],"requires":{"env":["KERNEL_API_URL"],"anyBins":["python3","python"]},"primaryEnv":"KERNEL_API_KEY"}}
---

# Kernel — Relationship Physics Engine

Use this skill to manage when your agent should proactively reach out to people. Kernel tracks trust, engagement, and response patterns to surface the right action at the right time.

## Core concepts

- **Intent debt**: Someone messaged you — you owe them a response
- **Interaction tension**: Increases with outbound messages, decays over time
- **Engagement score**: 0–100 composite from recency, trust, reciprocity
- **Churn risk**: 0–1 probability the relationship goes dormant
- **Golden hours**: Learned optimal contact windows per person (requires ≥3 samples)
- **Sweep**: Call on a cron schedule to get all relationships ready for action

## Setup

```bash
export KERNEL_API_URL=http://localhost:8080
export KERNEL_API_KEY=your-key   # optional but recommended
```

## Commands

Run via the CLI wrapper: `python scripts/openclaw_kernel_tool.py <command>`

### `sweep` — Proactive heartbeat
Returns all relationships where the agent should act right now.
```bash
python scripts/openclaw_kernel_tool.py sweep --agent-id <id> --ts 2026-03-07T10:00:00Z
```
Response includes: `action`, `reason`, `confidence`, `engagement_score`, `churn_risk` per relationship.

### `decide` — Single-person decision
```bash
python scripts/openclaw_kernel_tool.py decide --agent-id <id> --person-id <pid> --ts 2026-03-07T10:00:00Z
```

### `decide-batch` — Multi-person decision
```bash
python scripts/openclaw_kernel_tool.py decide-batch --agent-id <id> --person-ids pid1 pid2 --ts 2026-03-07T10:00:00Z
```

### `inbound` — Record incoming message
```bash
python scripts/openclaw_kernel_tool.py inbound \
  --agent-id <id> --person-id <pid> --message-id <mid> \
  --email user@example.com --ts 2026-03-07T10:00:00Z
```

### `outbound` — Record sent message
Returns `outbox_id` — save it to report outcomes later.
```bash
python scripts/openclaw_kernel_tool.py outbound \
  --agent-id <id> --person-id <pid> --action SEND_FULFILLMENT \
  --reason "Paying debt" --message-id <mid> --ts 2026-03-07T10:00:00Z
```

### `outcome` — Report what happened after sending
```bash
python scripts/openclaw_kernel_tool.py outcome \
  --outbox-id <oid> --replied-at 2026-03-07T11:30:00Z
```

### `stats` — Dashboard
```bash
python scripts/openclaw_kernel_tool.py stats --agent-id <id>
```

### `persons` / `relationships` — Browse data
```bash
python scripts/openclaw_kernel_tool.py persons --agent-id <id>
python scripts/openclaw_kernel_tool.py relationships --agent-id <id> --sort-by churn_risk
```

## Actions returned by decide/sweep

| Action | Meaning |
|--------|---------|
| `SEND_FULFILLMENT` | Reply to a pending message |
| `SEND_WITH_APOLOGY` | Reply to an overdue message (>3 days) |
| `SEND_NUDGE` | Proactive follow-up (high urgency or long silence) |
| `SEND_GENTLE_PING` | Light check-in (dormant re-engagement or 12+ day silence) |
| `INTERNAL_ALERT` | Blocked by dependency — needs human input |
| `WAIT` | Tension high or cooldown active — do not send |
| `NO_ACTION` | Idle or churned — nothing to do |

## Recommended OpenClaw integration

```python
# In your agent's cron job or heartbeat:
import subprocess, json

result = subprocess.run(
    ["python", "scripts/openclaw_kernel_tool.py", "sweep",
     "--agent-id", AGENT_ID, "--ts", datetime.utcnow().isoformat() + "Z"],
    capture_output=True, text=True
)
sweep = json.loads(result.stdout)

for decision in sweep["decisions"]:
    if decision["action"].startswith("SEND_"):
        # Hand off to your messaging agent
        your_agent.send(person_id=decision["person_id"], action=decision["action"])
```
