> **STATUS: pending dispatch** — item 2 of [#114](https://github.com/odjhey/rozoro/issues/114); unblocks item 3.

# Crew brief: clear the ruff + shellcheck baseline (unblocks the no-mistakes lint gate)

**Repo:** /Users/odz/proj/rozoro · **Task kind:** Coder (mechanical/behavior-preserving)
**Branch:** one branch, one PR. Do not touch AGENTS.md or `.no-mistakes.yaml`.

## Intent

Bring the repo to zero findings under the agreed lint tooling so `commands.lint`
can be wired into the no-mistakes gate (a deliberately deferred decision — the
gate stays unwired until this baseline is clean). Ruleset is already curated in
`ruff.toml` (E9, F, B, BLE, PLW15); do not change the ruleset.

## Current baseline (measured 2026-08-26)

`uvx ruff check .` → **44 errors**:
- 20 × BLE001 blind-except
- 7 × PLW1510 subprocess.run without explicit `check=`
- 6 × B023 function-uses-loop-variable
- 6 × B904 raise-without-from inside except
- 4 × F401 unused-import (auto-fixable)
- 1 × PLW1509 Popen preexec_fn

`find bin hooks tests -name "*.sh" | xargs shellcheck -x` → **30 findings**:
- 20 × SC1091 (sourced file not followed) — fix with `# shellcheck source=…`
  directives pointing at `bin/rzr-lib.sh` (or the actual sourced path), not by
  disabling the check globally
- 5 × SC2015 (`A && B || C` pitfall), 2 × SC2054, 2 × SC2034, 1 × each
  SC2329/SC2251/SC2181/SC2086

## Rules of engagement

- **Behavior-preserving.** This repo is a running daemon + orchestrator; several
  broad `except Exception` catches in `lib/rozoro_monitor/` and the ledger helpers
  are deliberate fail-safe/fail-closed choices. For those, prefer a targeted
  `# noqa: BLE001` with a one-clause justification comment over narrowing the
  catch and changing failure semantics. Genuinely lazy catches get real fixes.
- PLW1510: add explicit `check=True`/`check=False` matching current behavior —
  never introduce a new raise path where the code previously ignored failure.
- B023 (loop-variable capture) is a real defect class: inspect each site; fix with
  default-arg binding or extraction, and note in the PR whether any was a live bug.
- B904: `raise … from exc` (or `from None` where chaining is deliberately hidden).
- F401: `uvx ruff check . --fix` handles these; verify nothing re-exported
  intentionally (check `__init__.py` usage before deleting).
- SC2015: restructure to explicit `if/then` only where the `A && B || C` really
  can misfire; otherwise leave and justify with a directive comment.
- Validate with the full suite: `tests/run.sh` (bats + pytest) must stay green.
- NOTE: `bin/rzr-pi-watchtower.sh` is byte-hash-pinned by the
  watchtower-policy-snapshot skill. If shellcheck flags it, DO NOT edit it in this
  task — report the finding in the handoff instead and exclude it with a
  file-level directive is also not allowed (that edits bytes). Simply leave it and
  list it as deferred; likewise any file the snapshot skill hashes.

## Acceptance

- `uvx ruff check .` → 0 findings (noqa'd lines each carry a why-comment).
- `find bin hooks tests -name "*.sh" | xargs shellcheck -x` → 0 findings
  (excluding any hash-pinned launcher, which must be reported-deferred, not edited).
- `tests/run.sh` green.
- PR opened with a per-rule summary and the list of intentional noqa/directives.
