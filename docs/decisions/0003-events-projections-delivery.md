# ADR-0003: Events, projections, and delivery acknowledgements stay separate

review: approved
date: 2026-08-22

## Context

A coordinating system needs to answer several different questions under retries, reconnects, crashes, and bursty crew completion:

- What happened?
- What is true now?
- What changed enough to deserve attention?
- Was the watchtower wake actually delivered?
- Which delivery batch was reconciled?
- Did the underlying task issue get resolved?

Collapsing those questions into one `done`/`ack` bit makes recovery ambiguous and causes delivery mechanics to mutate domain truth.

## Options

1. **Single mutable task state with one ACK.** Small schema, but loses event history and conflates delivery with task resolution.
2. **Event Log + projections + separate delivery ledger.** More explicit state, but each operation has one clear meaning and can recover independently.
3. **External queue as the source of truth.** Pushes durability elsewhere and weakens local crash-safe ownership.

## Choice

Keep these layers distinct:

1. accepted normalized **events** are durably recorded;
2. deterministic **Session/Task Projections** represent current truth;
3. actionable changes create immutable **generation membership/snapshots** for delivery;
4. watchtower registration/epoch and delivery confirmation track whether a generation was offered successfully;
5. **reconcile/generation ACK** records consumption of that exact delivery batch;
6. **task open-item ACK/resolution** remains separate;
7. operator acceptance remains outside the delivery protocol.

The shipped `rozorod` event bus implements this separation and is the foundation for future attention UX.

## Consequences

- Retries and reconnects can be idempotent without pretending work was resolved.
- Notifications may be coalesced without losing the immutable tasks/reasons represented by a generation.
- Current state can be rebuilt/reduced independently from wake delivery.
- A generation is explicitly a **delivery batch**, not the durable identity of a watchtower work item.
- The target stable attention-item capability can sit above this substrate without replacing the Event Log, projections, or delivery protocol. Whether Rozoro owns that implementation remains open.

The intended non-equivalence is:

```text
event persisted
  != notification delivered
  != generation reconciled/ACKed
  != attention item handled (target)
  != task open item resolved
  != operator acceptance
```
