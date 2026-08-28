---
name: v2_contract_handoff
description: "The handoff report grammar: turn blocks, fields, verdicts, the waiting triad, open items, ack cursors, and protocol errors."
type: contract
tags: [architecture, contracts, handoff]
status: v2-draft
generated: "Claude Fable 5, 2026-08-28"
created_at: 2026-08-28T00:00:00+08:00
---

> **v2 working copy** — forked from [`docs/architecture/contracts/handoff.md`](../../docs/architecture/contracts/handoff.md) at `b044dbe`. Iterate here; the v2 effort never edits the live architecture docs.

# Handoff protocol

Part of the [contracts index](./README.md). The handoff is the crew's only structured outbound channel: an append-only Markdown log at `tasks/<key>/handoff.md`, parsed by the **single canonical parser** (`lib/rozoro_monitor/handoff.py`) that every consumer shares (status, daemon report projection, lineage, progress reports).

## Block grammar

```markdown
## turn <n> — <heading>
verdict: done | waiting | needs-action | failed | blocked
reason: <required unless verdict is done>
did: <what happened>
pending: <what remains>
inputs-needed: <what is required from outside, or none>
artifacts: <paths/PRs/links, or none>
```

- Heading regex: `^## turn ([1-9][0-9]*)(?:\s+—.*)?$`. Any other `## ` heading is a **noncanonical H2** protocol error (content H2s are reported, not silently ignored).
- Turn numbers must be monotone; a gap is a deterministic protocol error (`turn sequence expected 2, got 3`).
- Duplicate fields within a block are errors. All fields except `reason` are required.
- "None" spellings: empty, `none`, `n/a`, `na`, `-`.
- Verdict matching is case-insensitive; the raw string is preserved in output.

## Verdict semantics

- **Open verdicts** are `needs-action`, `failed`, `blocked` — they surface until acknowledged.
- **`waiting` requires certification**: `inputs-needed` must be none, and both `pending` and `reason` must be meaningful. A `waiting` that fails the triad is a protocol error; a `waiting` on a runtime that cannot certify background activity is reported as `inconsistent-wait`, never trusted.
- `done` is a crew claim, not acceptance and not verification — downstream classification treats it as `reported-done-unverified` until evidence says otherwise.

## Open items and acknowledgement

- Open items are FIFO: an open `inputs-needed` from turn 1 survives a `done` at turn 2 until explicitly acknowledged (`rozoro ack <id> --through <n>`).
- Two cursors: `.acked-blocks-v2` (canonical, block index) preferred; `.acked-blocks` (legacy H2 index) mapped through each block's `legacy_index` (`acked_source: v2 | legacy-mapped | none`). An out-of-range or invalid cursor is a protocol error and resets `acked_through` to 0.
- **Task ACK ≠ generation ACK**: acknowledging delivery of a notification batch never resolves a task's open items.

## Parse result shape

```json
{
  "blocks": 3, "legacy_headings": 0,
  "acked_through": 1, "acked_source": "v2",
  "latest": { "turn": 3, "verdict": "done", "...": "..." },
  "block_details": [ { "turn": 1, "verdict": "...", "legacy_index": 1, "...": "..." } ],
  "open_items": [ "..." ],
  "unresolved": true,
  "protocol_errors": [ "..." ]
}
```

The parser also exposes `parse_text()` so consumers can parse **captured bytes** (a snapshot taken under safety checks) without re-opening a path.

## Standing rules (prompt-level)

The rendered protocol additionally instructs crews: never delete or rewrite existing blocks; give findings stable ids marked `open`/`resolved(<how>)`; resumed turns still append. It also documents a `heads:` line (`reviewed=<sha> pushed=<sha> ci=<sha> merged=<sha>` or `n/a`) — note this field is **prose-enforced only**: the canonical parser does not recognize it (a known seam; see [rewrite seams](../rewrite-seams.md)).
