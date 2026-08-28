---
name: watchtower-progress-report
description: Generate and persist a conservative dated fleet progress report artifact from durable Rozoro task folders. Use when the operator explicitly asks to generate, create, save, or persist a durable fleet report, including an artifact about blockers, input requests, malformed state, or reported completion. Do not use for conversational “where are we?”, “get me up to speed”, “gmuts”, “current status”, or “what next?” requests; those belong to get-me-up-to-speed.
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

The script reads safe regular evidence under the one shared home namespace's `tasks` directory (first nonempty public `ROZORO_HOME`, legacy `RZR_HOME`, then `$HOME/.rozoro`) with no-follow descriptor-relative access and Rozoro's canonical handoff parser captured from the validated checkout that owns this skill, then prints the new run directory. All selected and explicit roots receive leading `~`/supported `~user` expansion and one lexical absolute normalization. A compatibility `--repo-root` value is accepted only when it identifies that same directory inode; another checkout cannot supply executable parser code. A missing, unreadable, unowned, or symlink-traversed task root fails closed rather than producing a clean empty report.

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
