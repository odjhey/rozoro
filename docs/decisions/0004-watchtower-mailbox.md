# ADR-0004: Add a first-class Watchtower Mailbox

review: approved
date: 2026-08-22

## Context

The shipped event bus now preserves generation membership by task and actionable reason, plus immutable task snapshots. That is sufficient for exact delivery/reconciliation of a coalesced wake, but the generation remains the unit of acknowledgement.

At the target fleet size of roughly 10–12+ concurrent crews, several independent tasks can report within one wake generation. The operator may want to handle only some of them first while preserving the rest as explicit pending attention.

A generation-centric model alone cannot cleanly answer:

- Which exact attention reason has already been handled?
- Which items should remain pending after a partial pass?
- Which later task state superseded an older reason?
- How can one wake batch represent many independently actionable records without relying on watchtower conversation memory?

## Options

1. **Keep generation-only reconciliation.** Use generation membership plus current projections and require the watchtower to remember partial handling itself.
2. **Add a first-class Watchtower Mailbox.** Create stable task-scoped attention records; let generations batch their delivery while item state remains independently trackable.
3. **Use multiple watchtowers to partition attention.** Avoid per-item state by distributing tasks across coordinators, at the cost of routing/ownership complexity.

## Choice

Add a durable **Watchtower Mailbox** as an additive layer above the shipped Event Log, projections, and generation delivery ledger.

A mailbox item represents one factual reason a specific task deserves watchtower attention. It has its own stable identity and independent handled/superseded state.

Conceptually:

```text
mailbox_item_id
watchtower_id
task_id
kind / actionable_reason
source_event_seq or projection_generation
technical_severity
created_at
observed_at?
handled_at?
superseded_by?
```

A notification generation may reference/batch many mailbox items. The generation remains useful for delivery retry, registration epochs, coalescing, and exact wake reconciliation, but **it does not replace mailbox item identity**.

## Consequences

- One watchtower can process a burst partially without losing the unhandled remainder.
- Technical severity can be used for grouping/presentation while business priority remains operator-owned.
- Reconciliation should eventually return pending mailbox items with current projections, not require reconstructing attention solely from generation membership.
- Mailbox item handling must remain distinct from task open-item resolution.
- Supersession can remove stale attention from the active view without deleting historical evidence.
- The schema/model gains another durable concept; this cost is accepted because target concurrency makes attribution and partial handling first-class requirements.
- Existing `pending_generations`, generation snapshots, delivery offers, and ACK semantics remain valid infrastructure and should not be discarded merely to introduce the mailbox.
