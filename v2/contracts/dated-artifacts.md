---
name: v2_contract_dated_artifacts
description: "Immutable dated operator artifacts: path shape, privacy discipline, the policy-snapshot and progress-report schemas, and conservative classification."
type: contract
tags: [architecture, contracts, artifacts]
status: v2-draft
generated: "Claude Fable 5, 2026-08-28"
created_at: 2026-08-28T00:00:00+08:00
---

> **v2 working copy** — forked from [`docs/architecture/contracts/dated-artifacts.md`](../../docs/architecture/contracts/dated-artifacts.md) at `b044dbe`. Iterate here; the v2 effort never edits the live architecture docs.

# Dated operator artifacts

Part of the [contracts index](./README.md). Two skills persist immutable, dated evidence artifacts for the operator: policy snapshots and fleet progress reports. Both share one artifact discipline.

## Shared shape

```text
$ROZORO_HOME/artifacts/<category>/YYYY-MM-DD/YYYYMMDDTHHMMSS.ffffffZ-<8-hex-nonce>/
```

- Directories 0700, files 0600, written via `write_exclusive` (`O_CREAT|O_EXCL|O_NOFOLLOW`, fsync file **and** parent) through descriptor-relative no-follow I/O (`lib/rozoro_artifacts/safe_fs.py`).
- **No mutable `latest` alias, no pruning**: `retention: preserve-until-explicit-operator-deletion`. Immutability is the feature — artifacts are evidence, not caches.
- Fail closed on unsafe inputs: a missing/unowned/symlinked source tree aborts rather than producing a clean-looking empty artifact.

## Policy snapshots — `rozoro.watchtower-policy-snapshot/v9`

`watchtower-policy-snapshots/…/` → `watchtower-policy.md` (byte-for-byte core), `missions/<name>.md` (every shipped mission), `metadata.json`.

- Per-mission metadata records `sha256`, `bytes`, and **`composed_policy_sha256` = sha256(core ‖ mission)** — exactly the value a Pi registration records as `policy_sha256`, making snapshots and registrations cross-checkable.
- Coverage is verified aggressively: the Pi launcher's SHA-256 is pinned in the skill and its `exec` line is re-tokenized to prove exactly `[core, mission]` are appended; any launcher edit must bump the constant and schema version — **the staleness is the feature**.
- Git provenance (blob ids) is recorded only when the repo identity is stable across every read; otherwise `status: indeterminate` with null git fields.
- Claude coverage is recorded honestly as `unverified-no-consumed-policy-args-array` (Claude watchtowers consume no policy files).

## Progress reports — `rozoro.watchtower-progress-report/v2`

`watchtower-progress-reports/…/` → `report.md`, `evidence.json`, `metadata.json`.

Per task, from durable folders only (no live runtime claims): identity/session shape, ack cursor files, handoff `{file_state, sha256, parse_state, blocks, acked_through, acked_source, unresolved, protocol_error_count, open_items, latest{…}}`, and conservative classifications:

```text
reported-active-runtime-unverified | blocker-or-failure | human-decision-needed |
reported-done-unverified | acknowledged-report-no-current-outcome | unknown-or-malformed
```

`evidence_problem` gates every outcome category — a task with unsafe or malformed evidence can never be classified as anything stronger than its evidence supports. The handoff parser is loaded from the **validated checkout only** (`--repo-root` must resolve to the same dev/ino as the script's own repo): another checkout cannot supply executable parser code.

## Division of labor

- Conversational status ("get me up to speed") is a separate skill and is **forbidden from persisting files**; progress reports are the persisted counterpart, generated only on explicit operator request.
- Privacy: artifact content excludes prompts/transcripts per the documented exclusion list; reports derive from durable task folders, not live sessions.
