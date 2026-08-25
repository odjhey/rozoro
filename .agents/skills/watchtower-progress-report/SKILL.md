---
name: watchtower-progress-report
description: Generate and persist a conservative dated “how are we doing so far” report from current durable Rozoro task folders. Use for operator fleet progress, status summaries, blockers, input requests, malformed state, or reported completion without inventing runtime activity or acceptance.
compatibility: Requires Python 3.11+, a Rozoro checkout, and local filesystem access.
metadata:
  artifact-schema: rozoro.watchtower-progress-report/v2
---

# Watchtower progress report

Generate the report from durable task evidence rather than conversational memory.

## Run

From this skill directory:

```bash
python3 scripts/report.py
```

The script reads safe regular evidence under `$ROZORO_HOME/tasks` (default `~/.rozoro/tasks`) with no-follow descriptor-relative access and Rozoro's canonical handoff parser, then prints the new run directory. A missing, unreadable, unowned, or symlink-traversed task root fails closed rather than producing a clean empty report.

Default destination:

```text
$ROZORO_HOME/artifacts/watchtower-progress-reports/YYYY-MM-DD/YYYYMMDDTHHMMSS.ffffffZ-<nonce>/
```

Every invocation creates a new UTC timestamp-plus-nonce directory. It emits `report.md`, `evidence.json`, and `metadata.json`.

## Interpretation rules

Preserve these distinctions when presenting the result:

- **Verified durable facts** are only facts established by the files and parser (counts, structure, digests, acknowledgement state).
- A valid `waiting` handoff is **reported active work, runtime unverified**; task folders cannot certify current jobs.
- `blocked`, `failed`, unresolved open items, and requests for input remain distinct report categories.
- Outcome categories require canonical, unacknowledged handoff evidence plus present, valid identity/session JSON and safe acknowledgement-file evidence. Malformed/unsafe auxiliary evidence gates every outcome.
- An acknowledged latest report is listed as **acknowledged, not a current outcome**; acknowledgement never implies correctness or acceptance.
- A valid unacknowledged `done` handoff is **reported done, unverified and unaccepted**. Elapsed time, terminal idleness, and `done` never imply operator acceptance.
- Missing, unsafe, unreadable, noncanonical, or malformed evidence belongs under **unknown or malformed**, not a guessed state. A symlink, including a dangling symlink, is unsafe rather than missing.

The default report deliberately omits free-form handoff/brief text, cwd values, session contents, environment, credentials, live runtime state, and daemon databases. To answer a listed human decision, inspect the named task's source `handoff.md` in the live operator context; do not copy its question into this durable report unless the operator explicitly requests a separately reviewed artifact.

## Return to the operator

Report the printed artifact directory, schema, task/category counts, and any unknown/malformed evidence. Keep the generated files unchanged so their metadata hashes remain meaningful.

## Retention and composition

Artifacts are owner-private, created through validated directory descriptors without following ancestor symlinks, and retained until explicit deletion of an exact run directory. There is no `latest` alias or automatic pruning. This skill is read-only with respect to task folders and composes safely with `watchtower-policy-snapshot`; run either or both, and report each immutable directory independently.
