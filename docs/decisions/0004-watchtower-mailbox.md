# ADR-0004: Require first-class watchtower attention identity

review: approved
date: 2026-08-22

## Context

The shipped event bus preserves generation membership by task and actionable reason, plus immutable task snapshots. That is enough for exact delivery/reconciliation of a coalesced wake, but the generation remains the unit of acknowledgement.

At the target fleet size of roughly 10–12+ concurrent crews, several independent tasks can report within one wake generation. The operator may want to handle only some of them first while preserving the rest as explicit pending attention.

A generation-centric model alone cannot cleanly answer:

- Which exact attention reason has already been handled?
- Which items should remain pending after a partial pass?
- Which later task state superseded an older reason?
- How can one wake batch represent many independently actionable records without relying on watchtower conversation memory?

At the same time, ACP/acpx and other existing session/runtime tooling are now under evaluation. We should not turn a product requirement into a commitment to another Rozoro-owned subsystem before that evaluation is complete.

## Options

1. **Keep generation-only reconciliation.** Use generation membership plus current projections and require the watchtower to remember partial handling itself.
2. **Require stable task-scoped attention identity.** Preserve independent handled/superseded state and let delivery batches reference those items, while leaving the implementation boundary open.
3. **Build a Rozoro-owned Watchtower Mailbox now.** Commit immediately to a new durable subsystem and schema.
4. **Use multiple watchtowers to partition attention.** Avoid per-item state by distributing tasks across coordinators, at the cost of routing/ownership complexity.

## Choice

Require the **mailbox capability**, not a specific Rozoro-owned mailbox implementation.

The product needs a stable identity for each task-scoped reason that deserves watchtower attention, with independent handled and superseded state. A notification generation may batch many such items for delivery, but the generation must not become the durable identity of the operator work item.

Conceptually, the capability needs to carry information equivalent to:

```text
attention_item_id
watchtower_id or consumer scope
task_id
kind / actionable_reason
source_event_seq or projection_generation
technical_severity
created_at
observed_at?
handled_at?
superseded_by?
```

Where that capability lives remains open. It may be implemented by Rozoro, by an adapter over an existing local-first tool, by an ACP/acpx-adjacent component, or by another dependency that satisfies the contract. The ACP/acpx spike should test this explicitly before we add new substrate.

## Consequences

- One watchtower can process a burst partially without losing the unhandled remainder.
- Technical severity can be used for grouping/presentation while business priority remains operator-owned.
- Reconciliation eventually needs access to pending attention items plus current projections; it should not depend on conversational memory.
- Attention-item handling remains distinct from task open-item resolution.
- Supersession can remove stale attention from the active view without deleting historical evidence.
- Existing `pending_generations`, generation snapshots, delivery offers, and ACK semantics remain valid infrastructure during the evaluation.
- No new Rozoro-owned mailbox schema is approved by this ADR. Ownership and implementation stay open until the ACP/acpx and off-the-shelf evaluation produces evidence.
