---
name: v2_session_hosting_context
description: "Session Hosting bounded context — spawning, resuming, steering, and reaping live agent sessions on the Herdr terminal backend."
type: bounded-context
tags: [ddd, hosting, herdr]
status: v2-draft
generated: "Claude Fable 5, 2026-08-28"
created_at: 2026-08-28T00:00:00+08:00
---

> **v2 working copy** — forked from [`docs/architecture/bounded-contexts/session-hosting.md`](../../docs/architecture/bounded-contexts/session-hosting.md) at `b044dbe`. Iterate here; the v2 effort never edits the live architecture docs.

# Session Hosting

**Core question:** where is this agent running right now?

## Responsibility

Own the mapping from a durable task to a live host: one task = one Herdr tab = one pane = one agent process. Create it (`spawn`), reopen it (`resume`), steer it (`send`/`control`), and remove it (`teardown`) — without ever touching the durable record or the repository.

## Owned state

- `state/<key>.meta` — the host binding: pane, tab, workspace, cwd, harness/profile fields, preallocated session, event-bus flag, dispatcher attribution. KEY=VALUE, last-write-wins, explicitly **not yet a stable public API**.
- The home mutation lock (taken only by `spawn`/`resume`; readers never lock).
- Transient legacy watcher state (`state/<key>.status`, `.runtime.json`).

## Key behaviors

- **Two planes** ([CLI contract](../contracts/cli.md)): `send` is data the model reads; `control` is a closed executed verb list. A lifecycle command must never arrive as interpretable chat.
- **Validation before mutation**: profile, capability, and preset checks all fail before the first Herdr call.
- **Environment pinning**: the crew's `ROZORO_HOME` is injected at `tab create` (the only injection point — Herdr's server forks the pane process), so spawned crews always join the spawning home's event bus.
- **Verified postconditions**: control verbs re-read pane state (`agent wait`, status polls) rather than trusting exit codes; transient `agent_pane_busy` is retried, `agent_not_ready` is polled but never re-started.
- **Harness translation** is delegated to the [harness adapters](../contracts/harness-adapters.md); Herdr interaction to the [Herdr port](../contracts/herdr-port.md).

## Invariants

- Teardown is **VCS-agnostic and byte-exact** on the cwd; it deletes live state only.
- The pane is the addressing authority for a live agent; the task key never is.
- Codex/Copilot crews are unconditionally autonomous (`yolo` normalized after preset resolution).
- Task prompts pass verbatim; system-prompt overhead is kept out of them.
- Resume reopens the **exact** native conversation and reapplies the durable profile; a still-tracked task cannot be resumed or respawned.

## Boundary rule

Session Hosting owns *where* an agent lives and *how* it is steered. It does not own task truth (Durable Tasks), semantic runtime state (Lifecycle Evidence — Herdr `idle` is hosting truth, never quiescence), or the decision to interrupt anyone (Wake Delivery).
