# Product architecture

Rozoro is intentionally small, but it owns several different kinds of truth. The architecture separates those truths so terms such as `idle`, `done`, `priority`, `task`, `session`, and `notification` do not collapse into one state machine.

## Context map

```text
Operator
  │ intent / business priority / acceptance
  ▼
Watchtower orchestration
  │ dispatch / steer / reconcile / present facts
  ▼
Task lifecycle ────────────────┐
  │ task identity / brief     │
  │ handoff / exact resume    │
  ▼                           │
Harness runtime               │
  │ native lifecycle facts   │
  ▼                           │
Observation + delivery        │
  │ events → projections      │
  │ → attention → generations│
  ▼                           │
Watchtower                    │
                              │
Terminal hosting (Herdr) ─────┘
  tabs / panes / liveness / actuation

External target repository
  owns implementation, testing, review, PR and merge policy
```

## 1. Watchtower orchestration

**Purpose:** coordinate many independent crews on behalf of the operator.

Owns:

- task decomposition and dispatch choices;
- choosing which existing crew context to steer next;
- reconciling factual state from Rozoro;
- presenting pending attention to the operator;
- executing operator-selected order of work;
- deciding when a task should be resumed or reaped, subject to safety checks.

Does not own:

- business priority independent of the operator;
- repository correctness;
- harness-native lifecycle truth;
- durable event/delivery mechanics.

The watchtower may embody workflow policy in its prompt/skills, but that policy is not a Rozoro core state machine.

## 2. Task lifecycle

**Purpose:** preserve one durable identity for delegated work across turns, process restarts, teardown, and exact resume.

Owns:

- immutable task key and display name;
- durable brief;
- append-only handoff/report history;
- task open-item state and task-level ACK/resolution;
- exact native session linkage used for resume;
- distinction between live hosting and durable task existence.

A task is not a pane. A pane is one current host binding for a task/session.

## 3. Harness runtime

**Purpose:** translate harness-specific lifecycle evidence into conservative Rozoro semantics.

Owns:

- harness session identity;
- foreground activity;
- owned background activity where the harness can certify it;
- derived availability such as `busy`, `waiting-background`, `quiescent`, or `unknown`;
- adapter capability/confidence boundaries.

Harness-native evidence outranks terminal idleness for semantic completion. If a harness cannot certify a fact, Rozoro should prefer `unknown` to inference.

## 4. Observation, attention, and delivery

**Purpose:** durably record lifecycle facts, reduce current truth, identify actionable task changes, and deliver wakeups efficiently.

Already shipped:

- durable Event Log;
- session/task projections;
- ordering/deduplication;
- actionable generation membership and immutable snapshots;
- watchtower registration/epoch state;
- coalesced notification generations;
- delivery confirmation and exact generation reconciliation/ACK;
- crash/reconnect recovery.

Target refinement:

- first-class Watchtower Mailbox items with stable per-attention identity and independent handled state.

A generation is therefore a **delivery batch**. It must not become the durable identity of an operator work item.

## 5. Terminal hosting

**Purpose:** provide the execution substrate on which harness sessions live.

Herdr owns:

- tabs, panes, workspaces, and process/session hosting;
- host-level liveness;
- addressing and supported actuation operations.

Herdr does not own:

- semantic turn completion;
- repository-task verdicts;
- watchtower priority;
- mailbox/delivery state.

## 6. External repository domain

The target repository remains deliberately outside Rozoro's product model. Crew sessions load that repository's own instructions and own:

- code investigation and implementation;
- worktrees/branches;
- testing strategy;
- review behavior;
- PR creation/update;
- CI interpretation;
- merge authority and delivery policy.

Rozoro may transport prompts and lifecycle facts around that work, but it should not encode a generic model of those repository concerns.

## Invariants

- Task verdict and runtime availability are independent facts.
- Herdr `idle` is not equivalent to Rozoro `quiescent`.
- Crew `done` is not operator acceptance.
- Technical severity is not business priority.
- Event durability is not notification delivery.
- Notification delivery is not generation ACK.
- Generation ACK is not task open-item resolution.
- Target mailbox-item handling is not task resolution.
- Host teardown does not delete durable task identity/history.
- Harness-native subagents remain inside their parent crew unless a separate crew task is deliberately created.
