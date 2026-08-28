---
name: v2_contract_registration
description: "Watchtower registration: driver identity, the validated wake target (target.json + registrations.jsonl), policy attribution, and the event-bus authority marker."
type: contract
tags: [architecture, contracts, watchtower, registration]
status: v2-draft
generated: "Claude Fable 5, 2026-08-28"
created_at: 2026-08-28T00:00:00+08:00
---

> **v2 working copy** — forked from [`docs/architecture/contracts/registration.md`](../../docs/architecture/contracts/registration.md) at `b044dbe`. Iterate here; the v2 effort never edits the live architecture docs.

# Registration and authority

Part of the [contracts index](./README.md). Registration answers one question safely: **which live conversation may Rozoro wake, and how?** It exists because backend identity must never be guessed from a bare environment variable — a Claude process launched from a Codex shell inherits a stale `CODEX_THREAD_ID`; ambiguity is a hard error.

## Driver identity

`driver_id = "<backend>-<identity sanitized to [A-Za-z0-9._-]>"[:120]`

- Backends: `herdr` (identity = pane id, e.g. `herdr-w1_p1`) or `codex` (identity = thread id). Claude watchtowers override to `claude-<native-session-uuid>` so identity survives pane changes.
- Stable across restarts; the Pi extension asserts its derived id matches the launcher's.
- Resolution without an explicit `--driver` accepts **only a single registered match**: zero → "register first"; multiple → "ambiguous, pass --driver".

## The registration record

`watchtowers/<driver-id>/` (0700), serialized by a per-driver `.registration.lock`:

- **`target.json`** — the commit point (0600, temp + `os.replace` + dir fsync):

```json
{
  "schema": 1,
  "registration_id": "<32 hex>",
  "driver_id": "...", "harness": "claude|codex|copilot|pi",
  "backend": "herdr|codex", "identity": "...",
  "owner_pid": "<ppid>", "created": "<ISO8601Z>",
  "watchtower_name": "…",
  "preset": { "name": "…", "version": "…", "sha256": "…", "model": "…", "effort": "…", "policy_sha256": "…" },
  "policy_sha256": "…", "policy_core_sha256": "…",
  "policy_mission_name": "…", "policy_mission_source": "shipped|operator", "policy_mission_sha256": "…"
}
```

- **`registrations.jsonl`** — append-only history, written **after** the target commit. A later registration that finds the target ahead of history back-fills the missing record with `"recovered": true` before appending its own — the crash window is intentional and self-healing.

## Validation before write

- Attribution ingress (`ROZORO_WT_*` env) is validated **before the shared library is sourced**, so an invalid tuple is a pure no-write failure.
- The five policy fields are **all-or-none and Pi-only** (Claude watchtowers are policy-blind by construction); digests must be 64-hex; mission source ∈ `{shipped, operator}`.
- The declared harness is checked against the **live** Herdr pane (`agent get`): reported harness must match, pane must match, and the pane must be `interactive_ready` — except Pi panes registered with `--agent-session`, which are validated by exact session-path identity instead (such panes never report `interactive_ready`).
- `auto` backend picks codex only when the declared harness is codex **and** `codex queue` provably works.
- Registration is a security surface: traversal, symlinks, hardlinks, FIFO inputs, control characters, overflow versions, and rename-swap races are all rejected fail-closed (tested).

## Watchtower launch sequences

- **Pi**: resolve preset → resolve policy (core + exactly one mission, hashed) → export attribution → TOCTOU re-check ("policy changed during launch" dies) → `exec pi` with launcher-owned system prompts. Registration happens from inside the extension, retried until Herdr reports identity, then `authority-activate`.
- **Claude**: preset (harness `claude`) → capability gate → monitor start → identity triple (`native session`, fresh `incarnation`, driver `claude-<native>`) → settings overlay + capability proof → background child: pane-ready check → register → poller ready handshake (`poller-ready.<incarnation>`) → `authority-activate` → assert marker; foreground `exec claude`. Exact resume reuses the driver but mints a new incarnation, so a stale `SessionEnd` cannot poison the new registration.

## Event-bus authority

- `authority-activate` requires the daemon to report `authority == "active"` **and** the legacy ledger to be clean (`0 ≤ ack ≤ delivered ≤ generation`, strict closed schema, duplicate keys rejected); a dirty ledger must be drained by the prior release first.
- Activation writes `watchtowers/<driver>/.event-bus-authority` containing exactly `event-bus-v1\n` (O_EXCL, fsynced). From that moment **every legacy ledger writer hard-refuses** for this driver.
- `rollback --driver` reverses it transactionally: refused unless `generation == delivered == ack`; tombstones daemon authority first, then removes the marker under the authority lock.

## Attribution flow (observational)

Registration is also the source of dispatch attribution: `spawn` looks up the dispatching watchtower (explicit `ROZORO_WT_DRIVER` wins; otherwise identity-derived candidates accepted only when exactly one) and stamps `dispatcher_*` keys into task meta, later folded into `session.json.dispatcher`. Attribution is observational only — lookup or write failure must never block a spawn.
