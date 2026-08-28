---
name: bounded_contexts_index
description: "Index of Rozoro's bounded contexts: durable tasks, session hosting, lifecycle evidence, wake delivery, registration & authority, policy & steering."
type: index
tags: [architecture, ddd, bounded-contexts]
status: current
generated: "Claude Fable 5, 2026-08-28"
created_at: 2026-08-28T00:00:00+08:00
---

# Bounded contexts

Rozoro decomposes into six bounded contexts. Each file states the context's core question, what it owns, its invariants, and its boundary rule. The [context map](../product-architecture.md#context-map) shows how they relate.

- [Durable Tasks](./durable-tasks.md) — *what work exists, and what has been reported?*
- [Session Hosting](./session-hosting.md) — *where is this agent running right now?*
- [Lifecycle Evidence](./lifecycle-evidence.md) — *what is certifiably true about each session now?*
- [Wake Delivery](./wake-delivery.md) — *when and how may the watchtower be interrupted?*
- [Registration & Authority](./registration-and-authority.md) — *which resident session may be woken, under which recorded policy?*
- [Policy & Steering](./policy-and-steering.md) — *how should the fleet be run, and what did the watchtower decide?*

Two domains are deliberately **outside** Rozoro:

- **The repository domain** — worktrees, branches, PRs, CI, merge authority, testing policy. Rozoro never invokes git; teardown leaves every cwd byte untouched (ADR-0005).
- **Harness-native orchestration** — subagents and background work inside a crew's own harness belong to the crew, not to Rozoro.
