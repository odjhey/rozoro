---
name: wake_delivery_context
description: "Wake Delivery bounded context — generations, coalescing, delivery offers, the live gate, reconcile, and the generation ACK ladder."
type: bounded-context
tags: [ddd, delivery, notifications]
status: current
generated: "Claude Fable 5, 2026-08-28"
created_at: 2026-08-28T00:00:00+08:00
---

# Wake Delivery

**Core question:** when and how may the watchtower be interrupted?

## Responsibility

Convert actionable projection changes into **at-most-one outstanding, content-free nudge** per driver, and account for its delivery and reconciliation without ever losing a fact or injecting content into a resident conversation.

## The acknowledgement ladder (ADR-0003)

Seven layers stay separate; each arrow is a distinct state with its own record:

```text
event persisted → projection changed → generation membership frozen
  → delivery offer (per registration epoch) → notification delivered
  → generation reconciled/ACKed → task open item ACKed → operator acceptance
```

## Owned state and mechanics

- **Generations**: monotonic delivery batches. Every bump freezes membership *and* a complete snapshot of task projections, so a later generation cannot leak into an earlier one's reconcile view. Twenty actionable events remain twenty facts — coalescing (default window 350 ms) reduces wakes, never facts.
- **Cursor invariant**: `0 ≤ acked ≤ delivered ≤ latest`, enforced by DB CHECK constraints (and mirrored by the legacy ledger's `should_deliver ⟺ generation > ack ∧ delivered ≤ ack`).
- **The nudge** is the fixed string `Rozoro notification pending; run ./bin/rozoro reconcile.` — prose-free by wire contract; task data can never become injected instructions.
- **Live gate**: a wake reaches a resident driver only when its availability is `quiescent` (busy/waiting-background never inject); delivery is confirmed only **after** the backend succeeds; refusal or disconnect leaves the offer unconfirmed for redelivery. Per-backend actuators: Herdr prompt (Pi extension follow-up / Claude poller), `codex queue`.
- **Reconcile**: serves the changed-task delta by default (`--full` for everything; ADR-0010 — motivated by ~76% non-actionable noise), renders only frozen snapshot fields, and ACKs **exactly** the snapshotted generation — an edge landing mid-reconcile stays pending and re-nudges. An empty snapshot is never ACKed; an unconfirmed offer is never manufactured into delivery; a caller-visible render failure leaves the generation unacked for duplicate retry.

## Invariants

- At-least-once delivery: the generation persists **before** the backend call — a duplicate fixed nudge is acceptable; a lost actionable edge is not.
- Delivery batches are not work items: generation ACK never resolves task open items; per-task attribution survives coalescing.
- An older in-flight delivery success can never mark a newer generation delivered.
- N+1 isolation: reconciling generation N never leaks mutable state or generation N+1 content.

## Legacy ledger (fenced)

The file-based wake ledger (`pending.json`/`ack` + edge-id idempotent bumps) is the pre-daemon implementation of the same algebra. It is diagnostic-only, serialized behind the authority lock, and hard-refuses once a driver holds event-bus authority; a dirty ledger blocks cutover until drained.

## Boundary rule

Wake Delivery owns interruption accounting. It does not decide what is actionable (Lifecycle Evidence's projection does), whom to wake (Registration & Authority owns the target), or what the watchtower does upon waking (Policy & Steering).
