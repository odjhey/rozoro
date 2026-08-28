---
name: v2_contract_artifacts_evidence
description: "v2 contract (new): typed artifact references and version-bound evidence records; gate verdicts as records; heads: as sugar over evidence."
type: contract
tags: [contracts, artifacts, evidence, v2]
status: v2-draft
generated: "Claude Fable 5, 2026-08-28"
created_at: 2026-08-28T00:00:00+08:00
---

> **v2 addition** — introduced by [proposal 0001](../proposals/0001-orchestrator-primitives-alignment.md) (P3, charter D7). Formalizes what v1 does in prose: the delivery-evidence skill, changed-head reconciliation, and the handoff `heads:` line.

# Artifacts and evidence

Part of the [contracts index](./README.md). The founding rule, inherited from v1's changed-head discipline and now structural:

> **Evidence must identify exactly which artifact version it validates.** "Tests passed" without a head SHA is not evidence; it is a rumor about code that may already have changed.

## ArtifactRef

```json
{
  "schema": 1,
  "artifact_id": "<ulid>",
  "kind": "code-change | document | report | build | deployment | decision-record | configuration | dataset",
  "location": { "repo": "…", "ref": "…", "path": null, "url": null },
  "version": { "commit": "<sha>", "tree": "<sha>", "content_sha256": null },
  "producer_attempt": "<attempt id>",
  "recorded_at": "<ISO8601Z>"
}
```

- `version` carries whatever exact identity the kind supports; for code changes that is commit **and** tree (rebases change the commit, not the work — v1's changed-head record already distinguishes them).
- Artifacts live in their stores (repo, filesystem, CI); the core records **references**. The control plane never becomes the data plane — v1's rule, unchanged.

## Evidence

```json
{
  "schema": 1,
  "evidence_id": "<ulid>",
  "kind": "test | build | diff-review | static-analysis | benchmark | runtime | contract-check | human-approval",
  "subject": { "artifact_id": "…", "version": { "commit": "<sha>" } },
  "method": "…",
  "result": { "verdict": "pass | fail | mixed", "detail_ref": "…" },
  "producer": { "kind": "gate | crew | operator | tool", "id": "…", "attempt_id": null },
  "recorded_at": "…",
  "stale": false
}
```

- `subject` is mandatory and exact — evidence without a version-bound subject is rejected at the schema, the way contradictory report tuples are rejected in protocol v1.
- **Staleness is derived and monotonic**: an `invalidates` edge firing, or a new accepted artifact version on the same subject, marks dependent evidence `stale`. Stale evidence is never deleted (it remains true *about its version*); it simply no longer supports acceptance at the current head. This is changed-head reconciliation as a mechanism instead of a named-owner prose record.
- Hard/soft separation (research §6) maps to `kind`: correctness kinds gate acceptance; advisory kinds (benchmark, maintainability review) may inform decisions but a gate rule cannot be satisfied by advisory evidence alone.

## Gate verdicts

The gate itself stays **external** (ADR-0008: no-mistakes and repo CI own their mechanics); v2 records its outcomes:

```json
{ "schema": 1, "verdict_id": "<ulid>", "gate": "no-mistakes | ci | review | human",
  "subject": { "artifact_id": "…", "version": { "commit": "<sha>" } },
  "verdict": "accepted | rejected", "evidence_refs": ["…"], "failure_class": null,
  "recorded_at": "…" }
```

A verdict consumes evidence refs, never prose claims; a rejection carries a [failure class](./attempts.md#failure-classes-p4) so routing keys on facts.

## `heads:` becomes sugar (extends charter D3)

The handoff `heads:` line (`reviewed=<sha> pushed=<sha> ci=<sha> merged=<sha>`) is now **parsed as shorthand for evidence records**: each `<stage>=<sha>` pair asserts stage-evidence bound to that exact version, recorded on ingest. The mechanical head-chain equality test of the eager mission (`reviewed == pushed == ci == merged`) becomes a pure query over evidence. The [handoff contract](./handoff.md) is amended accordingly; free-text `artifacts:` remains legal but a crew that records ArtifactRefs gives the graph `invalidates` edges something exact to bite on.

## Invariants

- No acceptance (gate verdict, workset terminal) on stale or version-mismatched evidence — fail closed, name the deficit (the v1 evidence-deficit dispatch, mechanized).
- Evidence and artifacts are append-only; corrections are new records.
- Human approval is an evidence kind like any other — recorded, version-bound, and required where policy says so; absence of objection is not approval (v1 human-gates rule, unchanged).
