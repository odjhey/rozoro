# Dated Watchtower artifacts

Rozoro ships two project skills for operator-owned, point-in-time records:

- `/skill:watchtower-policy-snapshot` captures the checkout's explicit Pi Watchtower policy source and records per-harness coverage.
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

Directories are mode `0700` and files are mode `0600`. Every lexical path component is opened with directory-relative, no-follow operations; symlinked ancestors and destinations are rejected, and descendant creation stays bound to validated directory descriptors across pathname swaps. Runs are preserved indefinitely by default. Retention is an operator decision: remove only a named run directory after review; the skills never prune history.

## Policy snapshot schema

The captured bytes come directly from the `templates/watchtower.md` core plus every shipped `templates/missions/*.md` mission (ADR-0013). Validation first requires the Pi launcher bytes to match the schema-versioned shipped SHA-256 exactly, then shell tokenization enforces the top-level contract: an `args=(...)` array followed by the executable command `exec env ROZORO_WATCHTOWER=1 pi "${args[@]}" "$@"`. The consumed array must contain `--append-system-prompt` adjacent to `$ROOT/templates/watchtower.md` and `--append-system-prompt` adjacent to `$MISSION_FILE` as option/value pairs. Conditional/dead assignments, uncalled functions, overwritten or unused arrays, scalar/indexed assignments, `unset`, `eval`, source/dot, function and command-substitution mutation paths, any other byte-level launcher drift, echo/string decoys, and conditional/dead invocations do not count. Only syntactically complete top-level array assignment/append forms may establish or change the modeled policy array; recognized conditional appends may add runtime arguments but cannot establish policy coverage. The mission file itself is resolved at launch (shipped `templates/missions/<name>.md` or operator `$ROZORO_HOME/watchtower-missions/<name>.md`, exactly one); operator missions are noted as not-captured coverage. The Claude launcher's `args` array currently has no such policy argument, so metadata records Claude as `unverified-no-consumed-policy-args-array`. Launcher paths and hashes make that scope reviewable without copying stale policy prose.

A run contains:

```text
watchtower-policy.md  # byte-for-byte core policy snapshot
missions/<name>.md    # byte-for-byte shipped mission snapshots
metadata.json         # schema, UTC time, hashes, Git provenance, privacy boundary
```

Example metadata shape:

```json
{
  "schema": "rozoro.watchtower-policy-snapshot/v9",
  "artifact_type": "watchtower-policy-snapshot",
  "created_at": "2026-08-24T03:25:36.123456Z",
  "run_id": "20260824T032536.123456Z-a1b2c3d4",
  "source": {
    "repository_relative_path": "templates/watchtower.md",
    "role": "explicit Watchtower core policy source (composed with one mission at launch)",
    "applies_to_harnesses": ["pi"],
    "sha256": "…",
    "bytes": 1234,
    "git_commit": "…",
    "git_blob_at_commit": "…",
    "git_blob_current": "…",
    "matches_git_commit": true
  },
  "missions": {
    "templates/missions/delivery.md": {
      "mission": "delivery",
      "sha256": "…",
      "bytes": 2345,
      "composed_policy_sha256": "…",
      "git_blob_at_commit": "…",
      "git_blob_current": "…",
      "matches_git_commit": true
    }
  },
  "default_mission": "delivery",
  "git_provenance": {
    "status": "verified",
    "method": "held-directory-identity-verified-before-and-after-each-git-read",
    "repository_identity": "fs-0123456789abcdefabcd",
    "reason": null
  },
  "harness_coverage": {
    "validation": "exact-shipped-pi-launcher-sha256-plus-grammar-v2",
    "expected_pi_launcher_sha256": "4f63ae862ed3332d21e244562316b9a36dbe7fdece82c977d2912c5de6386763",
    "option": "--append-system-prompt",
    "value": "$ROOT/templates/watchtower.md",
    "mission_value": "$MISSION_FILE",
    "mission_sources": {"shipped": "templates/missions", "operator": "$ROZORO_HOME/watchtower-missions", "operator_status": "not-captured"},
    "pi": {"status": "captured", "launcher": "bin/rzr-pi-watchtower.sh", "launcher_sha256": "…"},
    "claude": {"status": "unverified-no-consumed-policy-args-array", "launcher": "bin/rzr-claude-watchtower.sh", "launcher_sha256": "…"}
  },
  "files": {
    "watchtower-policy.md": {"sha256": "…", "bytes": 1234},
    "missions/delivery.md": {"sha256": "…", "bytes": 2345}
  },
  "retention": "preserve-until-explicit-operator-deletion"
}
```

`matches_git_commit: false` is valid only with `git_provenance.status: verified`: it means the captured working-tree policy bytes differ from `HEAD`. The validated repository directory remains open while Git reads run, and its lexical pathname is reopened without following links and matched by device/inode before and after every read. A mismatch, command failure, empty output, or output other than a 40- or 64-hex Git object ID sets provenance to `indeterminate`, records an explicit `git-read-failed` reason where applicable, and sets all Git-derived source fields to `null`. No absolute checkout path is stored.

## Progress report schema

A progress-report run contains:

```text
report.md      # operator-readable categories and evidence caveats
evidence.json  # machine-readable task classifications and per-handoff digests
metadata.json  # schema, UTC time, file hashes, privacy/retention boundary
```

`evidence.json` and `metadata.json` declare schema `rozoro.watchtower-progress-report/v2`; `report.md` is their human-readable companion. The source object records `default-rozoro-home` versus `explicit-override`, a non-path display token, and a stable hash of the opened filesystem identity:

```json
{
  "source": {
    "selection": "explicit-override",
    "display": "<explicit-tasks-root>",
    "root_id": "fs-0123456789abcdefabcd"
  }
}
```

`evidence.json` records, per safe task directory:

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
| `reported-done-unverified` | Latest unacknowledged canonical report says `done`; correctness and acceptance are not established. |
| `acknowledged-report-no-current-outcome` | The latest canonical report is acknowledged, so it is not promoted as a current outcome; acknowledgement is not acceptance. |
| `unknown-or-malformed` | Evidence is absent, unsafe, unreadable, malformed, or noncanonical. |

One task can have multiple classifications (for example, a newer report plus an older unacknowledged blocker). Outcome classifications are emitted only when handoff protocol is canonical, the relevant evidence is unacknowledged, identity/session JSON is present and valid, and acknowledgement-file evidence is neither malformed nor unsafe. A task with malformed/unsafe auxiliary evidence or handoff protocol is not simultaneously promoted to an outcome category.

The report has explicit sections for verified durable facts, reported active work, blockers/failures, human decisions, reported done, and unknown/malformed state. “Verified” applies only to file/parser facts. Task-folder evidence has no acceptance marker, so `done`, terminal idleness, or age never becomes accepted work.

## Evidence and privacy boundary

Task roots are required: a missing, unreadable, unowned, or symlink-traversed root fails before creating an artifact instead of becoming a clean empty report. An existing empty root remains a valid empty source. Explicit `--tasks-root` use is recorded as `explicit-override`; its absolute path is excluded, while the root identifier ties metadata and evidence to the directory actually opened.

The scan opens task directories and files relative to validated directory descriptors and parses the exact captured handoff/cursor bytes represented by the recorded digests. Its canonical parser source is itself captured with no-follow descriptor-relative reads from the checkout that owns the skill. `--repo-root` is compatibility-only and must resolve to that same directory device/inode, so another checkout cannot inject parser code. Pathname replacement cannot redirect an in-progress scan. The default artifact excludes:

- brief and free-form handoff prose;
- cwd values and repository contents;
- session identifiers or transcript/session contents;
- environment variables and credentials;
- daemon databases and live Herdr/harness state.

The task key and structural task status are intentionally included because the report must remain actionable and discoverable. Symlinks are never followed; dangling symlinks are recorded as `unsafe`, not `missing`. If an operator needs the exact question behind a `human-decision-needed` entry, inspect that task's durable `handoff.md` in its owner-private source location rather than broadening every report's data surface.

## Direct invocation

The skills normally invoke their bundled scripts. They can also be run directly from the checkout:

```bash
python3 .agents/skills/watchtower-policy-snapshot/scripts/snapshot.py
python3 .agents/skills/watchtower-progress-report/scripts/report.py
```

Each command prints only its newly created run directory. Both are safe to run in either order and do not depend on a target repository.
