# Kernel Math and Hypotheses (v1)

This document is the persistent technical reference for Kernel's core hypotheses and equations.

## 1. Causal Chain (Invariant)

\[
\text{Observed Events} \rightarrow \text{Inferred State} \rightarrow \text{Constraint Gate} \rightarrow \text{Policy} \rightarrow \text{Action + next\_decision\_at}
\]

## 2. Objective Hypothesis

Kernel optimizes long-run relationship progress under safety constraints.

\[
\max_{\pi} \; \mathbb{E}_{\pi}\left[\sum_{t=0}^{T} \gamma^t\left(R_{t+1} - \lambda P_{soft}(S_t, A_t)\right)\right]
\]

subject to hard legality constraints:

\[
C_{hard}(S_t, A_t) = 1
\]

Where:
- \(R\): progression reward
- \(P_{soft}\): soft penalty (tension, repeated pressure, poor timing)
- \(\lambda\): soft-penalty weight
- \(\gamma\): discount factor

## 3. Hard Constraints vs Soft Penalties

Hard constraints (pre-policy gate) are non-overridable, e.g. opt-out, cooldown floor, critical tension block, compliance block.

Soft penalties are scored trade-offs inside policy, e.g. rising tension below hard ceiling, weak recent engagement.

## 4. Core State Equations (Current v1)

### 4.1 Tension decay

\[
\text{days\_passed} = \frac{t_{now} - t_{last\_contact}}{86400}
\]

\[
\text{tension}_{t} = \text{tension}_{t-1} \cdot e^{-\lambda_{decay} \cdot \text{days\_passed}}
\]

### 4.2 Event reaction updates

Inbound received:

\[
\text{tension} \leftarrow 0, \quad \text{reply\_debt} \leftarrow 1, \quad
\text{trust} \leftarrow \min(1,\; \text{trust} + \Delta_{inbound})
\]

Outbound sent:

\[
\text{tension} \leftarrow \min(1,\; \text{tension} + \Delta_{outbound}), \quad \text{reply\_debt} \leftarrow 0, \quad
\text{trust} \leftarrow \min(1,\; \text{trust} + \Delta_{outbound\_trust})
\]

### 4.3 Engagement score

\[
\text{engagement} = 0.3\cdot\text{recency} + 0.3\cdot\text{trust} + 0.2\cdot\text{activity} + 0.2\cdot(100-\text{debt\_penalty})
\]

with recency modeled by exponential decay from last contact.

### 4.4 Urgency score

\[
\text{urgency} = \max(\text{debt\_urgency},\; \text{silence\_urgency},\; \text{churn-amplified terms})
\]

Debt urgency ramps over unresolved debt age; silence urgency increases after cadence threshold.

## 5. Decision Contract

Policy emits a structured decision:

\[
\text{DecisionResult} = (\text{action\_type},\; \text{pressure\_class},\; \text{reason\_codes},\; \text{score\_breakdown},\; \text{next\_decision\_at})
\]

## 6. Runtime Guardrail Signal Model

Canonical runtime signal includes:
- experiment binding: \(experiment\_id\)
- package binding: \(package\_hash\)
- optional scope keys: \(cohort, arm, segment\)
- metric and window: \(metric\_name, metric\_window\)
- observed, threshold, direction: \((x, \theta, dir)\)

Threshold breach test:

\[
\text{breach}=
\begin{cases}
x > \theta & \text{if } dir=\text{upper}\\
x < \theta & \text{if } dir=\text{lower}
\end{cases}
\]

Single-signal evaluator maps to:
- `NONE`
- `PAUSE`
- `ROLLBACK_CANDIDATE`

## 7. Unresolved Semantics (Single Source of Truth)

An evaluation is unresolved iff:
1. decision is actionable (`PAUSE` or `ROLLBACK_CANDIDATE`)
2. `resolved != true`
3. age is within stale window (default 72h)

## 8. Multi-signal Aggregation Policy (v1)

Given unresolved evaluations in scope:
1. any `ROLLBACK_CANDIDATE` => aggregate `ROLLBACK_CANDIDATE`
2. else if unresolved `PAUSE` count for a metric exceeds threshold => escalate to `ROLLBACK_CANDIDATE`
3. else if any unresolved `PAUSE` => aggregate `PAUSE`
4. else => `NONE`

Default pause escalation threshold: 3.
Optional per-metric override: \(\tau_{metric}\), fallback to global \(\tau\).

## 9. Operational Hypotheses

1. Safety-first gating reduces harmful outreach without collapsing useful progression.
2. Replay + attribution windows produce more reliable policy comparison than ad hoc metric reads.
3. Scope-aware aggregation (experiment/package/cohort/arm/segment) reduces false confidence from pooled averages.
4. Deterministic artifacts (hash-bound) reduce ambiguity in launch/review/rollback decisions.

## 10. Change Policy

Any change to equations or semantics in this document should be mirrored in:
- tests
- rollout/governance docs
- parameter changelog (project-level ops registry)
