# Product architecture

Rozoro is intentionally small, but the product needs several different kinds of truth. The architecture separates those truths so terms such as `idle`, `done`, `priority`, `task`, `session`, and `notification` do not collapse into one state machine. Where a capability is not yet shipped, these docs describe the contract without assuming Rozoro must own the implementation.

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
Harness/session runtime       │
  │ structured lifecycle facts│
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
- harness lifecycle truth;
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

## 3. Harness/session runtime

**Purpose:** provide structured lifecycle evidence that can be normalized into conservative task/session semantics.

The product semantics require:

- harness session identity;
- foreground activity;
- owned background activity where the lifecycle source can certify it;
- derived availability such as `busy`, `waiting-background`, `quiescent`, or `unknown`;
- explicit capability/confidence boundaries.

Structured harness evidence outranks terminal idleness for semantic completion. If the available source cannot certify a fact, prefer `unknown` to inference.

Today Pi and Claude have Rozoro-specific semantic paths. ACP/acpx and upstream harness contracts are under evaluation before more adapter surface is added. The contract matters; ownership of the adapter/runtime layer is not settled.

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

Target capability:

- stable task-scoped attention-item identity with independent handled and superseded state.

This capability is often called the **Watchtower Mailbox** in the product model. That name does not imply that Rozoro must build another mailbox subsystem; ACP/acpx and off-the-shelf local-first tools should be evaluated against the contract first.

A generation is a **delivery batch**. It must not become the durable identity of an operator work item.

## 5. Terminal hosting

**Purpose:** provide the execution substrate on which harness sessions live.

Herdr owns today:

- tabs, panes, workspaces, and process/session hosting;
- host-level liveness;
- addressing and supported actuation operations.

Herdr does not establish:

- semantic turn completion;
- repository-task verdicts;
- watchtower priority;
- attention-item or delivery semantics.

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
- Target attention-item handling is not task resolution.
- Host teardown does not delete durable task identity/history.
- Harness-native subagents remain inside their parent crew unless a separate crew task is deliberately created.
