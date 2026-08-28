---
name: contract_harness_adapters
description: "Per-harness adapter contracts: launch argument mapping, lifecycle-event production (hooks/extension), capability gating, session discovery, and exact resume for Claude, Codex, Pi, and Copilot."
type: contract
tags: [architecture, contracts, ports, harness]
status: current
generated: "Claude Fable 5, 2026-08-28"
created_at: 2026-08-28T00:00:00+08:00
---

# Harness adapters

Part of the [contracts index](./README.md). Each harness (Claude, Codex, Pi, Copilot) is integrated through an anti-corruption layer with four responsibilities: **launch mapping**, **lifecycle production**, **session discovery**, and **exact resume**. Capability differences are surfaced honestly — evidence a harness cannot certify is reported `unknown`, never inferred.

## Shared rules

- Task prompts pass verbatim; Rozoro overhead (handoff protocol, task marker) travels via system-prompt channels where the harness has one (Claude, Pi), or above an explicit delimiter where it does not.
- Hooks/extensions publish **only opaque lifecycle identifiers** — never prompt, transcript, command, or assistant content — and must never alter harness behavior (hook exit is unconditionally 0; hard timeout ≤0.75 s).
- Every producer uses the durable spool-then-socket path (reserve → send → delete on matching ACK).
- Codex and Copilot crews are unconditionally autonomous: permission mode is normalized to `yolo` **after** preset/flag resolution, so a personal preset cannot weaken that contract.

## Claude

- **Launch**: `--model`, `--session-id <preallocated uuid>`, `--effort`, `--permission-mode`, `--append-system-prompt-file <sysprompt.md>`, `--settings <task-local overlay>`.
- **Capability gate**: Claude Code `>=2.1.240 <2.2.0`, enforced independently in shell and in the settings writer, and re-verified at hook runtime against a **capability proof** (`{version, binary: realpath, identity: [st_dev, st_ino]}`, 0600) pinning the exact certified binary. Fails closed before any settings write or launch.
- **Lifecycle production** (`hooks/claude-rozoro-event.py`, registered via a private settings overlay for six hook events — user/project Claude config is never touched):
  - `SessionStart → session.register`; `UserPromptSubmit → turn.start (turn_id = prompt_id)`; `SubagentStart → background.start (job_kind "subagent")`; `SessionEnd → session.end`.
  - `SubagentStop → nothing`, deliberately: a stop edge cannot certify that no other owned work exists; positive evidence is retained until the next authoritative `Stop`.
  - `Stop →` ordered pair `[turn.stop, background.snapshot]`: the `background_tasks` payload is accepted as authoritative only when strictly valid, yielding `background.snapshot(active_count)` and a certified `background_active`; otherwise `background_active = null` (unknown, never inferred clear).
- **Session discovery**: `~/.claude/projects/<slugged cwd>/*.jsonl` grepped for the `rozoro-task:` marker. **Resume**: `claude --resume <uuid>` + durable profile.

## Codex

- **Launch**: always `--yolo`; `--model`, `--config model_reasoning_effort=<e>`, `--config service_tier=priority` (fast tier); hooks passed as `--config hooks.<Event>=[…]` literals plus `--dangerously-bypass-hook-trust`.
- **Lifecycle production** (`hooks/codex-rozoro-event.py`, four events, crew-only): `SessionStart/UserPromptSubmit/Stop/SessionEnd`; `Stop` always emits `background_active = null` — Codex provides no authoritative all-clear snapshot. No capability proof or version gate (a known asymmetry; see [rewrite seams](../rewrite-seams.md)).
- **Session discovery**: `$CODEX_HOME/sessions/**/*.jsonl`; first line must be `session_meta` with matching `cwd`; the marker must appear inside a real user message. **Resume**: `codex resume <uuid> --yolo` + durable profile (legacy descriptors resume without injecting model/effort/tier).
- **Wake backend**: a Codex-backed watchtower is woken via `codex queue --thread <id>`; registration probes `codex queue --help` as a runtime capability, not a version string.

## Pi

- **Launch**: always `--extension .pi/extensions/rozoro-watchtower.ts`; `--model`, `--thinking <effort>`, `--approve`, `--append-system-prompt <file>`, `--session-id <preallocated uuid>`.
- **Lifecycle production** (the extension, both crew and watchtower modes): `agent_start → turn.start`, `agent_settled → turn.stop` with **`background_active: false`** — Pi has no background axis, so a settled turn certifiably leaves nothing outstanding. Watchtower mode additionally registers, activates authority, and actuates wakes as `pi.sendMessage({customType: "rozoro-event"}, {triggerTurn: true, deliverAs: "followUp"})`.
- Mode detection: `ROZORO_WATCHTOWER=1` or the system prompt containing the core-policy marker; crew mode matches `^rozoro-task: <id>$`.
- **Session discovery**: Pi session dir, header `type: session` + matching cwd, preferring the preallocated UUID. **Resume**: `pi --session <uuid>`.

## Copilot

- **Launch**: always `--no-auto-update --autopilot --yolo --no-ask-user`; `--model`, `--effort`, `--session-id <preallocated uuid>`. Capabilities are verified by parsing `copilot --help` for the exact flag set; drift fails before any Herdr mutation.
- **Lifecycle production**: none — Copilot has no hook surface; it is watched only via Herdr status (legacy path) and reported conservatively.
- **Session discovery**: never scans private storage; the preallocated UUID is authoritative. **Resume**: `copilot --resume=<uuid>`.

## Capability summary

| | Claude | Codex | Pi | Copilot |
|---|---|---|---|---|
| Event-bus producer | yes (hooks) | yes (hooks) | yes (extension) | no |
| Background axis certified | snapshot-based | never (`null`) | trivially (`false`) | n/a |
| Version/capability gate | strict window + binary proof | queue probe | none | help-parse probe |
| Watchtower harness | yes (preset-only, policy-blind) | wake backend only | yes (mission-composed) | no |
| Session preallocation | yes | discovered by marker | yes | yes (authoritative) |
