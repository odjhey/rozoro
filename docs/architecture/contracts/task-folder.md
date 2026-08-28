---
name: contract_task_folder
description: "The durable task folder tasks/<key>/: identity, brief, handoff protocol, session link, ack cursors — what survives teardown and why."
type: contract
tags: [architecture, contracts, tasks]
status: current
generated: "Claude Fable 5, 2026-08-28"
created_at: 2026-08-28T00:00:00+08:00
---

# Task folder

Part of the [contracts index](./README.md). `tasks/<task-key>/` is the durable record of one delegated unit of work. It is created at reservation time and **survives teardown**; live hosting state lives separately under `state/` (see [home layout](./home-layout.md)).

## Files

| File | Format | Contract |
|---|---|---|
| `identity.json` | `{"schema":1, "task_key", "display_name", "cwd", "herdr_agent_name"}` | Written atomically at reservation; the `mkdir` of the folder is the collision arbiter for the key. |
| `brief.md` | `rozoro-task: <ID>` ⏎ `task-folder: <FOLDER>` ⏎ blank ⏎ `<BODY verbatim>` | The task input. The first line is the **load-bearing marker**: session discovery greps for it and the Pi extension regexes it. Never overwritten. |
| `handoff.md` | append-only `## turn <n>` blocks | The crew's outbound report log; see [handoff](./handoff.md). Created empty at render so a watcher can tail it from turn zero. |
| `handoff-protocol.md` | rendered `templates/handoff.md` with `{{ID}}`/`{{FOLDER}}` | The protocol text given to the crew. Idempotent render. |
| `sysprompt.md` | `rozoro-task: <ID>` + handoff protocol + optional `## Crew rules` | System-prompt overhead for harnesses with a system-prompt channel (Claude, Pi); keeps protocol out of the verbatim task prompt. |
| `session.json` | see below | The **session link**: everything needed to reopen the exact native conversation. |
| `.acked-blocks-v2` | integer | Canonical acknowledged-block cursor (block index). Authoritative when present. |
| `.acked-blocks` | integer | Legacy cursor (H2-heading index), maintained for migration; mapped through each block's `legacy_index`. |
| `claude-event-settings.json` (+ `.capability.json`) | hooks overlay + capability proof | Task-local Claude hook wiring; see [harness adapters](./harness-adapters.md). Never mutates user or project Claude config. |

## `session.json`

```json
{
  "id": "<task-key>",
  "harness": "claude|codex|copilot|pi",
  "cwd": "<abs path>",
  "session_id": "<native uuid>",
  "resume": "<exact resume command>",
  "session_path": "<transcript path, when discovered>",
  "profile": { "harness": "...", "model": "...", "effort": "...", "permission_mode": "...", "fast": false },
  "dispatcher": { "driver_id": "...", "watchtower_name": "...", "preset": "...", "preset_version": "...", "preset_sha256": "...", "policy_sha256": "..." }
}
```

- `session_id` is discovered by the `rozoro-task:` marker (or preallocated, per harness) — never by "newest file", which breaks when crews share a cwd.
- `profile` makes resume reapply the durable model/effort/permission/fast tier.
- `dispatcher` is **observational attribution** (which watchtower, preset, and composed policy dispatched this task); it must never block spawn or link.

## Invariants

- **Task existence is the folder; task liveness is `state/<key>.meta`.** Reap/teardown removes liveness only.
- The brief body is the operator's words, verbatim. Protocol overhead never contaminates it.
- `handoff.md` is append-only; acknowledgement advances cursor files, never rewrites the log.
- The same display name may exist many times (across time or repositories); the ULID-suffixed key keeps every instance distinct, with one Herdr-safe transport identity each.
- Unsafe display names cannot escape the task root (component validation; tested).
