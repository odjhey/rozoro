---
name: v2_bounded_contexts_index
description: "Index of Rozoro's bounded contexts: durable tasks, session hosting, lifecycle evidence, wake delivery, registration & authority, policy & steering."
type: index
tags: [architecture, ddd, bounded-contexts]
status: v2-draft
generated: "Claude Fable 5, 2026-08-28"
created_at: 2026-08-28T00:00:00+08:00
---

> **v2 working copy** — forked from [`docs/architecture/bounded-contexts/README.md`](../../docs/architecture/bounded-contexts/README.md) at `b044dbe`. Iterate here; the v2 effort never edits the live architecture docs.

# Bounded contexts

Rozoro v2 decomposes into seven bounded contexts (six carried from v1, plus Work Graph). Each file states the context's core question, what it owns, its invariants, and its boundary rule. The [context map](../product-architecture.md#context-map) shows how they relate.

- [Durable Tasks](./durable-tasks.md) — *what work exists, and what has been reported?*
- [Work Graph](./work-graph.md) — *what work exists in relation to other work, and what is runnable now?* (v2 addition, proposal 0001)
- [Session Hosting](./session-hosting.md) — *where is this agent running right now?*
- [Lifecycle Evidence](./lifecycle-evidence.md) — *what is certifiably true about each session now?*
- [Wake Delivery](./wake-delivery.md) — *when and how may the watchtower be interrupted?*
- [Registration & Authority](./registration-and-authority.md) — *which resident session may be woken, under which recorded policy?*
- [Policy & Steering](./policy-and-steering.md) — *how should the fleet be run, and what did the watchtower decide?*

Two domains are deliberately **outside** Rozoro:

- **The repository domain** — worktrees, branches, PRs, CI, merge authority, testing policy. Rozoro never invokes git; teardown leaves every cwd byte untouched (ADR-0005).
- **Harness-native orchestration** — subagents and background work inside a crew's own harness belong to the crew, not to Rozoro.
