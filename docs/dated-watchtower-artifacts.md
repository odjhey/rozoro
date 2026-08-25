# Dated Watchtower artifacts

Rozoro ships two project skills for operator-owned, point-in-time records:

- `/skill:watchtower-policy-snapshot` captures the Watchtower policy source used by the checkout.
- `/skill:watchtower-progress-report` summarizes current durable task-folder evidence conservatively.

They are workflow policy above Rozoro core. Neither skill changes tasks, runtime state, acknowledgements, repositories, or delivery state.

## Location and naming

Both skills default to the durable, checkout-independent data root:

```text
$ROZORO_HOME/artifacts/
├── watchtower-policy-snapshots/YYYY-MM-DD/YYYYMMDDTHHMMSS.ffffffZ-<nonce>/
└── watchtower-progress-reports/YYYY-MM-DD/YYYYMMDDTHHMMSS.ffffffZ-<nonce>/
```

`ROZORO_HOME` defaults to `~/.rozoro`, matching task storage. Dates and timestamps are UTC; `Z` is explicit, fractional seconds preserve ordering, and a random nonce makes concurrent runs collision-safe. Creation uses a new directory and exclusive file writes, so no run overwrites another. There is deliberately no mutable `latest` link.

Directories are mode `0700` and files are mode `0600`. Existing symlink destinations are rejected. Runs are preserved indefinitely by default. Retention is an operator decision: remove only a named run directory after review; the skills never prune history.

## Policy snapshot schema

The authoritative captured bytes come directly from `templates/watchtower.md`. This is the source passed by the Pi and Claude Watchtower launchers, rather than a duplicate summary maintained in the skill.

A run contains:

```text
watchtower-policy.md  # byte-for-byte policy snapshot
metadata.json         # schema, UTC time, hashes, Git provenance, privacy boundary
```

Example metadata shape:

```json
{
  "schema": "rozoro.watchtower-policy-snapshot/v1",
  "artifact_type": "watchtower-policy-snapshot",
  "created_at": "2026-08-24T03:25:36.123456Z",
  "run_id": "20260824T032536.123456Z-a1b2c3d4",
  "source": {
    "repository_relative_path": "templates/watchtower.md",
    "role": "launch-time Watchtower system prompt",
    "sha256": "…",
    "bytes": 1234,
    "git_commit": "…",
    "git_blob_at_commit": "…",
    "git_blob_current": "…",
    "matches_git_commit": true
  },
  "files": {
    "watchtower-policy.md": {"sha256": "…", "bytes": 1234}
  },
  "retention": "preserve-until-explicit-operator-deletion"
}
```

`matches_git_commit: false` is valid provenance: it means the snapshot captured current working-tree policy bytes that differ from `HEAD`. No absolute checkout path is stored.

## Progress report schema

A progress-report run contains:

```text
report.md      # operator-readable categories and evidence caveats
evidence.json  # machine-readable task classifications and per-handoff digests
metadata.json  # schema, UTC time, file hashes, privacy/retention boundary
```

All three files use schema `rozoro.watchtower-progress-report/v1`. `evidence.json` records, per safe task directory:

- task key;
- whether identity/session JSON is missing, valid, malformed, or unsafe (never its contents);
- handoff byte count and SHA-256;
- canonical block, acknowledgement, unresolved-item, and latest-verdict structure;
- structural open-item flags without free-form question text;
- zero or more conservative classifications.

Classification values are:

| Value | Meaning |
|---|---|
| `reported-active-runtime-unverified` | Latest canonical report says `waiting`; current activity is not certified. |
| `blocker-or-failure` | Canonical current/unresolved evidence reports `blocked` or `failed`. |
| `human-decision-needed` | Canonical current/unresolved evidence requests action or input. |
| `reported-done-unverified` | Latest canonical report says `done`; correctness and acceptance are not established. |
| `unknown-or-malformed` | Evidence is absent, unsafe, unreadable, malformed, or noncanonical. |

One task can have multiple classifications (for example, a newer report plus an older unacknowledged blocker). A task with malformed handoff protocol is not promoted to an outcome category from guessed prose.

The report has explicit sections for verified durable facts, reported active work, blockers/failures, human decisions, reported done, and unknown/malformed state. “Verified” applies only to file/parser facts. Task-folder evidence has no acceptance marker, so `done`, terminal idleness, or age never becomes accepted work.

## Evidence and privacy boundary

The report scan is point-in-time best effort, not a transaction across task folders. Per-handoff digests identify the bytes observed immediately before parsing; a task may change while the scan is in progress. The default artifact excludes:

- brief and free-form handoff prose;
- cwd values and repository contents;
- session identifiers or transcript/session contents;
- environment variables and credentials;
- daemon databases and live Herdr/harness state.

The task key and structural task status are intentionally included because the report must remain actionable and discoverable. If an operator needs the exact question behind a `human-decision-needed` entry, inspect that task's durable `handoff.md` in its owner-private source location rather than broadening every report's data surface.

## Direct invocation

The skills normally invoke their bundled scripts. They can also be run directly from the checkout:

```bash
python3 .agents/skills/watchtower-policy-snapshot/scripts/snapshot.py
python3 .agents/skills/watchtower-progress-report/scripts/report.py
```

Each command prints only its newly created run directory. Both are safe to run in either order and do not depend on a target repository.
