---
name: durable_tasks_context
description: "Durable Tasks bounded context — task identity, briefs, handoff reports, acknowledgement, session links, and the lineage read model."
type: bounded-context
tags: [ddd, tasks]
status: current
generated: "Claude Fable 5, 2026-08-28"
created_at: 2026-08-28T00:00:00+08:00
---

# Durable Tasks

**Core question:** what work exists, and what has been reported?

## Responsibility

Own the durable record of delegated work: task identity, the brief (input), the handoff log (output), acknowledgement cursors, and the session link that makes the exact conversation resumable. Everything here **survives host teardown**.

## Aggregate root: the task

Identity is the task key `<display>--<ULID26>`; the aggregate is the [task folder](../contracts/task-folder.md). Distinct from four other identities that must never be collapsed: pane, tab, Herdr agent name, native session.

```text
(none) ──start──▶ reserved ──render──▶ briefed ──spawn──▶ live
                                                            │ teardown/reap
                                                            ▼
   live ◀──resume (same conversation) / restart (new)── reaped (folder intact)
```

- `spawn` refuses an already-tracked task (never clobber a live record); `resume` also refuses one (the live agent owns the transport identity — the alternative is `send`).
- `restart` is teardown + fresh spawn: same key, **new** conversation.

## Owned state

- `tasks/<key>/` — identity, brief, handoff, protocol, sysprompt, `session.json`, ack cursors.
- The append-only **handoff** log and its grammar ([contract](../contracts/handoff.md)): turn blocks, five verdicts, FIFO open items.
- **Task ACK**: the acknowledged-block cursor, advanced explicitly by the watchtower/operator — never by delivery machinery.

## Invariants

- Task existence (folder) ≠ task liveness (`state/<key>.meta`). Teardown removes only liveness.
- The brief body is the operator's words, verbatim; protocol overhead travels out-of-band.
- The handoff is append-only; acknowledgement moves cursors, never rewrites history.
- `done` is a report, not acceptance; open verdicts surface until task-ACKed.
- The `rozoro-task:` marker is the discovery key linking brief → native session → transcript; it must remain the first line of every brief.

## Read model: lineage

`lineage` merges four stores into one ordered per-task view — inbound prompts (transcript), outbound reports (handoff), watchtower decisions (attention items), and turn boundaries (event log) — with honest timestamps (handoff blocks are anchored to turn.stop events and marked inferred) and a **drift** flag when `inbound == blocks == turns` fails. Strictly read-only; ambiguous task references are fatal, never guessed.

## Boundary rule

Durable Tasks owns records and their grammar. It does not own live hosting (Session Hosting), runtime truth (Lifecycle Evidence), interruption (Wake Delivery), or judgment about whether reported work is acceptable (operator, via Policy & Steering).
