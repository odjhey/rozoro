---
name: contract_conventions
description: "Cross-contract conventions: identifiers, filesystem-safety discipline, atomicity, locking, JSON strictness, shell/runtime floors, and error shapes shared by every Rozoro contract."
type: contract
tags: [architecture, contracts, conventions]
status: current
generated: "Claude Fable 5, 2026-08-28"
created_at: 2026-08-28T00:00:00+08:00
---

# Contract conventions and shared primitives

Part of the [contracts index](./README.md). Every other contract file assumes these conventions. They are derived from the current implementation; where a convention is enforced by tests it is a hard contract, not a style preference.

## Identifiers

- **Task key**: `<display>--<ULID26>`. Display name ≤80 chars; full component ≤120 chars; charset `[A-Za-z0-9._-]`; never `.`/`..`. The ULID is Crockford base32 of `(ms<<80)|urandom(10)`; uniqueness is guaranteed by atomic `mkdir` of the task folder, not by the randomness.
- **Herdr agent name**: `rzr-` + first 28 hex chars of `sha256(task_key)` — Herdr caps agent names at 32 lowercase chars (`[a-z0-9_-]`).
- **Driver id**: `<backend>-<identity sanitized to [A-Za-z0-9._-]>` truncated to 120 (e.g. `herdr-w1_p1`); Claude watchtowers use `claude-<native-session-uuid>`. Stable across restarts.
- **Protocol IDs** (`event_id`, `session_id`, `turn_id`, `job_id`, `request_id`, `task_id`, `driver_id` on the wire): `^[A-Za-z0-9][A-Za-z0-9._:@+-]{0,127}$` — no whitespace, path separators, or control characters, because `event_id` becomes a spool filename. Path traversal is rejected at the protocol layer.
- **Timestamps**: ISO 8601 UTC (`2026-08-28T10:00:00Z`). Strict `^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$` where a format is validated (attention ledger).
- **Integers on the wire**: bounded by `MAX_INTEGER = 9_007_199_254_740_991` (JS `Number.MAX_SAFE_INTEGER`) — the narrowest bound across the Python daemon, the TypeScript/Bun Pi extension, JSON, and SQLite. Booleans are never accepted where integers are required (`True` is rejected).
- **Config strings** (preset fields, registration metadata): ≤120 chars, no `=`, no control chars (`ord < 32` or `127`) — `=` is banned because these values become `env KEY=VALUE` hook-command arguments.

## Filesystem-safety discipline

Every security-sensitive read or write follows the same pattern (implemented in `lib/rozoro_artifacts/safe_fs.py` and hand-rolled equivalents in `bin/rzr-lib.sh` / `bin/rzr-register.sh`):

- Walk each path component descriptor-relative with `O_NOFOLLOW|O_DIRECTORY`; re-`fstat` and compare `(st_dev, st_ino)` to detect swaps between `stat` and `open`.
- Require `st_uid == geteuid()`, `S_ISREG`/`S_ISDIR` as appropriate, `st_nlink == 1` (hardlinks rejected), and mode `0600` (files) / `0700` (dirs) — no group/other bits (`mode & 0o077 == 0`).
- A symlink — including a dangling one — is `unsafe`, never `missing`.
- Malformed evidence is surfaced by name and fails closed; it is never silently repaired, skipped, or counted.

The threat model is deliberately fenced (ADR-0011): there is **no forward-progress guarantee under same-UID sabotage**; reviews must not silently broaden that model.

## Atomicity and durability

- Files are committed by `mkstemp`/temp-write + atomic `rename`/`os.replace`, with `fsync` of the file and, for commit points, the parent directory.
- Append-only logs (`handoff.md`, `registrations.jsonl`, attention-item logs, `events`) are never rewritten; progress is tracked by **separate cursor files/columns**, not by mutating the log.
- Commit points precede derived writes: registration `target.json` commits before the history append; the event spool publishes before the producer-sequence cursor advances; a wake generation persists before the backend delivery call. In each case a crash produces a detectable, repairable gap or a harmless duplicate — never a silent loss.
- ACKs are issued only after durable commit (`ack` after SQLite `COMMIT`; spool entries removed only after a matching ACK).

## Locking

- **Home lock**: `state/.lock/` directory created by atomic `mkdir`, holder pid recorded; a dead-pid lock is reclaimed. Taken only by mutating verbs (`spawn`, `resume`); readers never take it.
- **flock-based locks**: producer spool (`spool/.lock`), per-session sequence files, per-driver registration (`.registration.lock`), legacy wake ledger (`pending.json.lock` under a shared `watchtowers/.authority.lock`), attention ledger (`attention.lock`), daemon ownership (`monitor.lock` holding `{pid, socket_dev, socket_ino}`).
- Lock helpers preserve the protected command's exit code and always release, including on failure.

## JSON strictness

- Wire frames: canonical encoding (`sort_keys`, compact separators, `allow_nan=False`), newline-terminated NDJSON, `MAX_FRAME_BYTES = 1 MiB` checked **before** parsing, in both directions.
- Decoding rejects duplicate object members at any depth, lone surrogates, and `NaN`/`Infinity` — closing parser-differential gaps between the Python daemon and the TS/Bun extension.
- **Wire schemas are closed**: unknown fields are rejected (`invalid-field`) so a misspelling cannot silently weaken semantics. **Config schemas are open**: presets tolerate unknown keys (forward compatibility) but reject malformed known keys. This asymmetry is deliberate.

## Runtime floors

- Shell: **bash 3.2** (stock macOS) — no `mapfile`, no associative arrays; parallel indexed arrays and disk state instead. CI runs `bash -n` on a real macOS host.
- Python: **≥3.11** for the monitor/daemon, gated before any side effect (3.9/3.10 must fail cleanly; CI proves it).
- Hard external dependencies: `herdr` (0.8.x), `jq`, `python3`. `git` is deliberately **not** a dependency of the core.
- Tests run in a pinned, network-less, read-only OCI container; digests are pinned per stage.

## Error conventions

- Shell: `rzr_die "msg"` → `rzr: msg` on stderr, exit 1; `set -euo pipefail` everywhere except `doctor` (reports all failures, then summarizes).
- Validation precedes mutation: every launcher/verb validates its full input before the first side effect ("fail before Herdr mutation" is a tested guarantee).
- Wire errors are typed frames with closed code sets and strict correlation: `frame.error` (uncorrelatable — carries no invented id), `event.error {event_id, code}`, `request.error {request_id, code}`. Codes: `invalid-json`, `frame-too-large`, `invalid-message`, `invalid-version`, `invalid-event`, `invalid-field`, `unsupported-type`, `read-timeout`, `server-busy`, `internal-error`.
- Exit codes carry meaning where documented: `link` exit 2 = "no session yet, retry"; `herdr-eventwait` 2/3/4 distinguish transport, ack, and stream failures; live tests exit 77 = skip.

## Compatibility posture

- New protocol fields are optional and additive; a new client omits them by default so it degrades to old-daemon behavior (e.g. reconcile `scope`).
- Legacy surfaces are kept alive but **fenced**, not removed: the legacy watcher/ledger requires `ROZORO_LEGACY_DIAGNOSTIC=1` and hard-refuses once the `.event-bus-authority` marker exists; the legacy ack cursor is mapped, with the v2 cursor canonical.
- Schema migrations refuse databases newer than the code, and refuse states they cannot truthfully backfill (a binary revert is not a database rollback).
