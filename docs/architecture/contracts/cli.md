---
name: contract_cli
description: "The rozoro/rzr command surface as an inbound port: dispatcher, verb grammar, planes, guarantees, and exit conventions."
type: contract
tags: [architecture, contracts, cli]
status: current
generated: "Claude Fable 5, 2026-08-28"
created_at: 2026-08-28T00:00:00+08:00
---

# Application CLI

Part of the [contracts index](./README.md). The CLI is Rozoro's primary inbound port; both the operator and a resident watchtower drive the system through it.

## Dispatcher

`bin/rozoro` (with `bin/rzr` as a symlink) dispatches `rozoro <verb> …` to `bin/rzr-<verb>.sh` by name; every `rzr-*.sh` is automatically a verb (the shared library and shims are excluded). `rozoro monitor` and `rozoro lineage` reach Python tools through 4-line shims. Unknown verb → exit 1.

## Data plane vs control plane

The sharpest CLI contract: **`send` is data, `control` is commands.**

- `send <id> <text> [--wait]` delivers free text the model reads (`herdr agent prompt`). Any other flag dies with a pointer to `control`.
- `control <id> <interrupt|cancel|key <name>|stop|restart>` executes a **closed verb list** against the harness process (send-keys, teardown, respawn). A key name containing a space is refused with a pointer to `send`.

A lifecycle command must never arrive as chat the agent might interpret; the two verbs use distinct Herdr operations (tested).

## Lifecycle verbs

| Verb | Contract |
|---|---|
| `start <display-name> --body <file> --cwd <dir> [spawn flags…]` | The blessed composite: reserve task key → render brief/protocol → spawn → link (retried). `--no-agent` stops before linking. Repeated display names get distinct durable keys. |
| `spawn <id> --cwd <dir> [--crew P] [--label T] [--harness H] [--model M] [--effort E] [--fast\|--no-fast] [--permission-mode M] [--prompt TXT \| --brief FILE] [--no-agent]` | Creates one Herdr tab+pane, records the host binding, starts the agent, delivers the verbatim prompt. Refuses if the task is already tracked. Runs under the home lock. All validation precedes the first Herdr mutation. |
| `resume <id> [profile flags] [--prompt\|--brief]` | Reopens the **exact** native conversation from `session.json` into a new host binding. Refuses while the task is still tracked ("continue it with send"). Reapplies the durable profile per harness. |
| `teardown <id> [--keep-tab]` | Removes live hosting only: closes the tab, deletes `state/<id>.*`. Never touches `tasks/<id>/` or the cwd (VCS-agnostic, byte-untouched — tested). `--force` is a deprecated no-op. |
| `control <id> restart` | Teardown + fresh spawn from recorded meta + brief: same task key, **new** conversation, then re-link `--refresh`. |
| `rollback --driver <id>` | Disables daemon authority for a driver (tombstone + marker removal); refuses unless `generation == delivered == ack`. |

## Inspection verbs (read-only, filesystem-pure)

| Verb | Contract |
|---|---|
| `status <id> [--json]` | Composes the durable handoff parse with the daemon projection. Pure: reading status never writes (8-way concurrent-reader equivalence is tested). |
| `list` | One row per tracked task: ID, runtime, background, task status, turn, pane, tab, cwd. |
| `lineage [<task>] [--json] [--full] [--drift]` | Read-only merge of prompts, handoff blocks, attention decisions, and turn events. Accepts exact key, unique prefix, or unique substring; ambiguity is fatal. Inferred timestamps are marked. |
| `crew list\|show\|path` / `watchtower list\|show\|path\|registered` | Preset and registration inspection. |
| `lock status` / `doctor` | Home-lock inspection; environment preflight (no `-e`, reports all failures, exit 1 on any FAIL). |
| `handoff <id>` | Canonical handoff parse as JSON. |

## Event-bus verbs

| Verb | Contract |
|---|---|
| `monitor run\|start\|status [--json]\|stop\|reset --force` | Daemon lifecycle. `start` polls health (≤8 s); `stop` proves ownership before signaling; `status` exits 1 when down; `reset` removes the [coherent boundary](./home-layout.md#boundary-rules) only. Python ≥3.11 gated before side effects. |
| `reconcile [--driver <id>] [--json] [--full]` | Reads the changed-since-last-ACK snapshot (delta by default, `--full` for everything) and advances the generation ACK to **exactly** the snapshotted generation. Never ACKs an empty snapshot; never manufactures delivery for an unconfirmed offer. |
| `ack <id> [--through <n>]` | Advances the per-task block cursor (`.acked-blocks-v2`, legacy mirror maintained). Refuses to advance past the last block or from an unsafe cursor. |
| `register --harness <h> [--backend auto\|codex\|herdr] [--agent-session <abs>] [--driver-id <id>] [--quiet]` | Registers a validated wake-delivery target; see [registration](./registration.md). |
| `watch [--once] [--json] [ids…]` | Legacy diagnostic watcher; wake flags hard-refuse without `ROZORO_LEGACY_DIAGNOSTIC=1`. |

## Wiring verbs (used by composites; rarely called directly)

| Verb | Contract |
|---|---|
| `render <id> <body-file>` | Writes `brief.md` (marker + verbatim body; never overwrites), touches `handoff.md`, renders `handoff-protocol.md`. Prints the brief path. |
| `link <id> <cwd> [--refresh]` | Discovers the native session by the `rozoro-task:` marker (never "newest file") and writes `session.json`. Idempotent; exit 2 = not yet. |
| `pi-watchtower` / `claude-watchtower` | Resident watchtower launchers; see [policy composition](./policy-composition.md) and [registration](./registration.md). |

## Cross-cutting guarantees

- Validation and capability checks always precede mutation (unsupported harness version, missing Copilot flags, invalid presets all fail before any Herdr call).
- Task prompts pass through **verbatim**; Rozoro protocol overhead travels via system-prompt channels, never inside the prompt body.
- Help paths stop before executable source is loaded.
- Fuzzy task resolution never guesses: ambiguity is a hard error everywhere.
- Transient Herdr conditions (`agent_pane_busy`) are retried with backoff; `agent_not_ready` is never retried as a second `agent start` (it would collide with the live agent) — readiness is polled instead.
