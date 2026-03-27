# Multichannel Persistence Model

This document defines how agents should persist relationship data across channels when using Kernel.

The goal is simple:

- one human
- one canonical identity
- many transport rails
- one relationship state in Kernel
- rail-specific operational memory outside Kernel

## 1. Design principle

Kernel should model the relationship with the person, not the transport identifier.

So:

- `person:+5215554540593` is the relationship identity
- `whatsapp`, `voice_call`, `telegram`, `sms` are transport facts on events

Do not create separate Kernel identities for:

- `whatsapp:+...`
- `voice:+...`

Those are rail identifiers, not person identifiers.

## 2. Persistence layers

There are three persistence layers.

### Layer A. Kernel

Kernel stores the relationship system of record:

- `persons`
- `relationships`
- `events`
- `inbox`
- `outbox`
- `contact_windows`

Kernel is responsible for:

- trust
- tension
- reply debt
- engagement
- churn
- `next_decision_at`
- action recommendations

Kernel is not the right place for full transcripts or rich call memory.

### Layer B. Rail-specific memory

Each rail can keep operational memory outside Kernel.

Examples:

- WhatsApp memory JSON
- call logs
- channel-specific contact state
- temporary bridge state for reply attribution

This memory is useful for:

- transcript-level detail
- appointment metadata
- call summaries
- provider-specific identifiers
- transport execution bookkeeping

### Layer C. Canonical person-state memory

Optional but recommended:

- one `person-state` record per human

This layer sits above rails and below Kernel.

It is useful for:

- current cross-channel focus
- active threads
- open loops
- next best action
- operational summaries per person

## 3. Canonical identity contract

All agents should send Kernel:

- `person_id = person:+E164`

Examples:

- `person:+5215520453254`
- `person:+5215560663926`

Transport-specific identifiers may still exist in external memory, for example:

- `whatsapp:+5215560663926`
- `voice:+525560663926`

But those should not be used as the Kernel relationship identity.

## 4. Channel belongs on events

The same person can interact on many rails.

That means the event shape should carry the channel:

- `channel=whatsapp`
- `channel=voice_call`
- `channel=telegram`

The person remains the same.

## 5. What counts as relationship contact

All real contact counts in Kernel unless you explicitly separate it.

This includes:

- rapport-building outreach
- business coordination
- appointment confirmation
- call attempts
- call outcomes

Why:

- humans experience all of it as contact pressure or contact value
- so trust, tension, and recency should still update

But not all contact should count equally.

Use event metadata like:

- `business_context`
- `channel`
- voice outcome fields

so downstream logic can distinguish:

- rapport
- fulfillment
- transactional coordination
- call follow-up

## 6. Recommended write flow

For any rail:

1. canonicalize the person
2. persist rail-specific memory
3. emit Kernel event(s)
4. execute or record outcome
5. feed reply/delivery outcome back into Kernel

In shorthand:

`rail event -> rail memory -> Kernel event -> execution -> Kernel outcome`

## 7. Voice example

Voice needs more than Kernel alone.

Recommended structure:

- `call_log` per call
- `contact_state` per voice contact
- Kernel events derived from the call

Suggested flow:

`provider payload -> call_log -> voice contact_state -> Kernel outbound/inbound/outcome`

Kernel should receive distilled facts such as:

- `answered`
- `voicemail`
- `appointment_created`
- `callback_requested`
- `follow_up_required`
- `negative_signal`

The full transcript stays outside Kernel.

## 8. WhatsApp example

WhatsApp can keep:

- raw conversation memory
- session-specific state
- person-state summary

Kernel should receive:

- inbound messages
- outbound messages
- delivery/reply outcomes

Again:

- keep the person canonical
- keep the channel explicit

## 9. Outcome attribution requirement

Kernel tracks outbox outcomes by `outbox_id`.

If your execution path bypasses the normal bridge, replies may update relationship state but fail to attach to the correct outbox row.

So for any custom sender:

1. send via the real rail
2. write Kernel outbound immediately
3. keep a mapping from send execution to `outbox_id`
4. when reply arrives, write Kernel outcome back to that `outbox_id`

Without this, relationship state may still look roughly right, but attribution will be incomplete.

Recommended reference adapter:

- [scripts/runtime_execute_send.py](/Users/mau/Documents/New project/kernel/scripts/runtime_execute_send.py)
- [scripts/openclaw_execute_send.py](/Users/mau/Documents/New project/kernel/scripts/openclaw_execute_send.py)
- [scripts/claude_execute_send.py](/Users/mau/Documents/New project/kernel/scripts/claude_execute_send.py)

`runtime_execute_send.py` is the primary generic implementation of the execution bridge contract.
`openclaw_execute_send.py` is the OpenClaw-specific adapter.
`claude_execute_send.py` remains as a compatibility wrapper around the generic runtime bridge.

The execution bridge contract is:

1. send through the real runtime transport
2. record Kernel outbound immediately
3. keep local attribution state for `outbox_id`
4. feed delivery/reply outcomes back into Kernel

The generic runtime adapter:

1. calls a runtime-specific sender command over stdin/stdout
2. records Kernel outbound using the returned `message_id`
3. stores `personHistory` bridge state for later reply attribution
4. records delivery immediately when the sender confirms it

The OpenClaw reference adapter:

1. sends through OpenClaw
2. records Kernel outbound
3. marks delivered by default
4. stores `personHistory` bridge state for later reply attribution

## 10. What Kernel should and should not own

Kernel should own:

- relationship state
- recommendation timing
- send pressure logic
- structured event history

Kernel should not own:

- raw full transcripts
- provider-specific execution traces
- audio latency metrics
- all transport-side operational memory

## 11. Minimal implementation standard for new agents

If a new agent wants to use Kernel safely, it should do all of the following:

1. use `person:+...`
2. include real `channel` on events
3. log inbound
4. log outbound
5. log outcome
6. preserve `outbox_id` until reply/delivery is known
7. keep rich transport memory outside Kernel

That is the minimum standard for persistent multichannel relationship behavior.

## 12. Operational takeaway

Kernel persistence is not “store everything in one database.”

It is:

- centralize relationship truth in Kernel
- keep channel-specific operational truth outside Kernel
- connect them through canonical identity and structured outcomes

That is what makes multichannel persistence coherent instead of becoming one more pile of message logs.
