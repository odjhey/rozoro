# Current vs target

Last reconciled with `master`: 2026-08-24.

PR #46 originally described several event-bus capabilities as target architecture. Since then, the event-bus stack shipped through the implementation sequence culminating in the production cutover. This page prevents the product model from becoming stale by separating **shipped substrate** from **remaining target behavior**.

## Shipped substrate

| Area | Current state |
|---|---|
| Durable task identity | `start` reserves durable task folders; brief/handoff/session linkage survive live host teardown. |
| Exact resume | Supported harnesses persist native session linkage and can reopen the exact conversation. |
| Resident coordination | `rozorod` is the resident local event-bus authority for managed Pi and supported Claude paths. |
| Durable Event Log | Normalized accepted lifecycle events are committed to owner-private SQLite before producer acknowledgement. |
| Session projection | Foreground/background/availability and registration state are durably reduced from lifecycle evidence. |
| Task projection | Availability plus report/action state is durably projected per task. |
| Harness-native semantics | Pi and Claude have semantic adapter paths; Herdr is also reconciled defensively for membership/liveness rather than treated as completion truth. |
| Delivery ledger | Watchtower registrations, epochs, generations, offers, delivery confirmation, reconcile, and generation ACK are durable. |
| Coalescing | Actionable changes can be batched into wake generations so bursts do not cause one prompt per event. |
| Generation membership | A generation retains the affected task IDs, actionable reasons, and immutable projection snapshots needed for exact reconciliation. |
| ACK separation | `reconcile` ACKs a delivered generation; task `ack` resolves surfaced handoff/open-item state separately. |
| Production cutover | The legacy watcher is diagnostic/compatibility only for daemon-managed Pi and supported Claude operation. |

The current implementation therefore already satisfies much of the original #46 event/projection/notification architecture. Those concepts should now be documented as **foundations**, not aspirational features.

## Remaining target behavior

### 1. First-class Watchtower Mailbox

The shipped delivery ledger is still generation-centric. `pending_generation_tasks` preserves task attribution inside a generation, but the watchtower ultimately reconciles/ACKs the generation as a unit.

The target mailbox adds:

- a stable identity for each task-scoped attention reason;
- independent observed/handled state;
- partial handling when many crews report together;
- explicit supersession without deleting history;
- generations that reference mailbox items for delivery batching rather than serving as the item identity themselves.

This is an additive refinement of the shipped event/projection/generation stack, not a replacement for it.

### 2. Fleet-scale attention UX

One primary watchtower should remain usable around 10–12+ parallel tasks. The system should make it cheap to ask questions such as:

- What needs operator attention now?
- Which items are urgent technically, and which are merely ready?
- Which items have I already handled this turn?
- Which lower-priority items are still pending?
- Which task state changed since the previous observation?

The product must preserve factual ordering and attribution without silently converting technical severity into business priority.

### 3. Harness parity where evidence exists

Pi and Claude currently have the strongest semantic event-bus integration. Codex/Copilot lifecycle parity should be added only when their native lifecycle evidence can support the same conservative contracts. Unknown/uncertified state is preferable to guessing from terminal idleness.

### 4. Keep workflow policy above the core

The operator/watchtower may run rich patterns such as planner → coder ↔ reviewer ↔ tester, but Rozoro core should not hard-code those repository/workflow policies. Role prompts, skills, task decomposition, review loops, and any future work-graph layer consume Rozoro's primitives; they do not redefine its task/session/event semantics.

## Compatibility rule

Future implementation work should preserve these already-shipped contracts unless an ADR deliberately changes them:

```text
Event durability
  != notification delivery
  != generation reconciliation/ACK
  != mailbox-item handling (target)
  != task open-item resolution
  != operator acceptance
```

When implementation and target docs differ, update this page and add or revise an ADR instead of allowing the mismatch to remain implicit.
