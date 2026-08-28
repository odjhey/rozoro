---
name: v2_contract_attention_ledger
description: "The watchtower attention ledger: durable per-(task, reason) attention items with stable identity, supersession, and handling logs — the interim Watchtower Mailbox."
type: contract
tags: [architecture, contracts, watchtower, attention]
status: v2-draft
generated: "Claude Fable 5, 2026-08-28"
created_at: 2026-08-28T00:00:00+08:00
---

> **v2 working copy** — forked from [`docs/architecture/contracts/attention-ledger.md`](../../docs/architecture/contracts/attention-ledger.md) at `b044dbe`. Iterate here; the v2 effort never edits the live architecture docs.

# Attention ledger

Part of the [contracts index](./README.md). The attention ledger is the watchtower's durable decision notebook — the interim implementation of the **Watchtower Mailbox** capability required by ADR-0004 (stable task-scoped attention identity with independent handling). It is deliberately a shared sibling of the per-incarnation driver directories so it **survives driver cycling**.

Schema id: `rozoro.watchtower-attention-ledger/v1`. Location: `$ROZORO_HOME/watchtowers/attention/` — `attention.lock` plus `items/<YYYYMMDDTHHMMSS>-<task>-<nonce>.md`.

## Item format (strict, both directions)

Frontmatter with an **exact, ordered** key set — missing or extra keys make the item `Malformed`:

```markdown
---
schema: rozoro.watchtower-attention-ledger/v1
id: <item id>
task: <task key>
reason: needs-action | failed | blocked | quiescent | missing-report | malformed-report |
        gone | waiting-background | no-mistakes | operator | other
priority: urgent | normal
status: open | handled | deferred | superseded
created_utc: 2026-08-28T10:00:00Z          # strict format
updated_utc: 2026-08-28T10:05:00Z
generation: none | <digits ≤18>
source: reconcile | status | operator | manual
superseded_by: none | <item id>
resume_when: <condition, when deferred>
tags: [a, b]
---
# <summary>

## Snapshot
…
## Handling log
- 2026-08-28T10:05:00Z open->handled: <note>
## Context
…
```

Body sections are exactly `## Snapshot`, `## Handling log`, `## Context` — any other `##` is malformed. Log lines: `- <ts> <old>-><new>: <note>`.

## Operations

| Op | Contract |
|---|---|
| `add` | Creates an item; by default **supersedes** any open/deferred item with the same `(task, reason)` (sets `superseded_by` + log line); `--no-supersede` opts out. |
| `update <id> --note …` | Note required. `--status deferred` requires `--resume-when`. Refuses to touch superseded or malformed items. |
| `list` | Frontmatter + title only (progressive disclosure); cursor pagination; AND-across/OR-within filters; `md|json|tsv`. |
| `show` / `prime` | `prime` re-primes a fresh/compacted session: urgent-open, normal-open, deferred with resume conditions, last-5-handled, counts, malformed — always prefixed by a provenance disclaimer. |
| `doctor` | Exit 1 if any item is malformed. |
| `export` | `artifact_type: watchtower-attention-ledger-export` — the declared ADR-0004 migration path off this interim format. |

- Every mutation takes an exclusive flock on `attention.lock`; reads take none.
- Items are append-only in spirit: state transitions append log lines; nothing is rewritten or deleted.
- Malformed files are **surfaced by name, never silently repaired or counted**.

## Semantics boundary

`handled` here means the watchtower dealt with its own attention — it is **not** task open-item resolution, not generation ACK, not a handoff verdict, and not operator acceptance. The ledger records routing decisions; the durable task record and delivery cursors keep their own truth.

## Known seam

The lineage view reads items with its own loose regexes rather than the canonical parser — a duplicated reader likely to diverge (see [rewrite seams](../rewrite-seams.md)).
