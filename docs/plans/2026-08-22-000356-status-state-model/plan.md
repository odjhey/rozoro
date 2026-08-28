# Make handoff status pure and turn-aware

Status: historical — shipped and regression-tested (see docs/current-vs-target.md)

Created: 2026-08-22 00:03:56 Asia/Manila

Scope: issue #9

Program coordination: [architecture findings](../2026-08-22-000356-architecture-findings/plan.md)

Test prerequisite: [Bats regression harness](../2026-08-22-000356-test-foundation/plan.md)

## Issue reference

Make handoff status pure, turn-aware, and explicit about runtime vs task state

https://github.com/odjhey/rozoro/issues/9

## Outcome

Rozoro reports three facts without conflating them:

- Herdr runtime state, observed by the watcher;
- durable task/handoff state, projected by a shared parser;
- whether the latest observed working turn appended a valid handoff block.

Ordinary status reads are filesystem-pure. Only an observed
`working -> idle|done|blocked` edge can produce a missing-handoff observation.
Acceptance remains driver/user judgment and is absent from the projection.

## Current-state evidence

- `bin/rzr-status.sh` advances `.seen-blocks` on every non-`--peek` read.
- A second read can print a missing-handoff warning without a new turn.
- Independent readers suppress one another through the shared cursor.
- `bin/rzr-watch.sh` writes a plain Herdr token to `state/<id>.status` but stores
  no turn boundary or handoff baseline.
- `bin/rzr-list.sh` labels live Herdr state as `STATE`, while status JSON exposes
  handoff fields without an explicit runtime/task split.
- Status and ack separately count every `## ` heading, so Markdown content can
  become a false turn and their counts can drift.

The explicit `.acked-blocks` cursor is not the defect. Preserve its FIFO meaning
until selective out-of-order acknowledgement is demonstrated.

## State contracts

### Runtime observation

`rzr-watch.sh` atomically writes `state/<id>.runtime.json` on initial
reconciliation and every real edge:

```json
{
  "schema_version": 1,
  "runtime_status": "idle",
  "observed_at": "2026-08-21T16:10:00Z",
  "source": "herdr-watch"
}
```

Allowed values are `idle`, `working`, `done`, `blocked`, `unknown`,
`shell`, and `gone`. Status reads this mirror rather than calling Herdr. If no
mirror or compatibility token exists, return `runtime_status: null` and an
explicit `unobserved` source.

For one compatibility window the watcher also writes `state/<id>.status`.
`rzr_status_get` reads structured data first and falls back to the token.

### Turn observation

Each watcher keeps its own previous runtime state and canonical handoff-block
baseline. On `working`, capture the count. When that observed turn settles,
atomically write `state/<id>.turn.json`:

```json
{
  "schema_version": 1,
  "transition": "working->done",
  "report_status": "missing",
  "blocks_before": 3,
  "blocks_after": 3,
  "observed_at": "2026-08-21T16:11:00Z"
}
```

`reported` means the count increased; equal means `missing`; decreasing means
`protocol-error`. Initial settled reconciliation writes no turn result. A
watcher starting while working captures the current baseline.

Overlapping watchers may write the same deterministic result via
process-unique temporary files and atomic rename. There is no shared increment
cursor that lets one watcher or reader suppress another.

### Canonical handoff projection

Add `bin/rzr-handoff.py` as the single standard-library parser used by status,
ack, and watcher counts.

A protocol block begins only at `^## turn [1-9][0-9]*\b`. Other headings are
content. Duplicate/decreasing numbers, missing or unknown verdicts, and unsafe
cursors surface protocol errors.

Task status precedence:

1. `protocol-error`
2. `no-handoff`
3. `open-items`
4. `reported-done`
5. `reported-failed`
6. `reported-incomplete`

An unacknowledged `needs-action|blocked|failed` verdict or non-empty
`inputs-needed` produces `open-items`, even after a later done block. Only ack
advances `.acked-blocks`.

### Status JSON v2

```json
{
  "schema_version": 2,
  "id": "task-1",
  "runtime_status": "idle",
  "runtime_source": "watcher-mirror",
  "runtime_observed_at": "2026-08-21T16:10:00Z",
  "task_status": "open-items",
  "handoff_verdict": "done",
  "blocks": 2,
  "acked_through": 0,
  "unresolved": 1,
  "open_items": [],
  "turn_report_status": "reported",
  "turn_observed_at": "2026-08-21T16:10:00Z",
  "protocol_errors": []
}
```

Retain descriptive fields and temporarily keep `verdict` as an alias. Remove
`new_block` and `--peek`; their reader-relative meaning is the bug. Human
output labels axes explicitly and warns only when the turn observation is
`missing`.

## File-level implementation

- `bin/rzr-handoff.py`: canonical parse, normalized fields, count, projection,
  open items, and deterministic errors.
- `bin/rzr-status.sh`: pure composition of handoff, runtime, turn, and ack data.
- `bin/rzr-ack.sh`: canonical count from the parser and atomic cursor writes.
- `bin/rzr-watch.sh`: per-process working baseline and atomic runtime/turn
  projections while preserving edge deduplication.
- `bin/rzr-lib.sh`: structured-state helpers and legacy-token fallback.
- `bin/rzr-list.sh`: explicit `RUNTIME` and `TASK` columns.
- `bin/rzr-teardown.sh`: remove runtime/turn files when reaping.
- `README.md`, `templates/watchtower.md`, and
  `.agents/skills/rozoro/SKILL.md`: replace NEW/same guidance and separate
  runtime done, reported done, open work, and acceptance.

## Bats coverage

Extend `tests/handoff.bats`, `tests/watch.bats`, and lifecycle cases with:

- zero blocks, one done block, buried open item, FIFO ack, malformed fields,
  invalid verdict, non-turn H2 headings, duplicate/decreasing numbers, and cursor
  edge cases;
- byte-for-byte snapshots around repeated human and JSON reads;
- two independent readers returning equivalent facts;
- working-to-settled with and without a new canonical block;
- no missing report on initial settled reconciliation or settled-to-settled;
- watcher startup while working and eventual classification;
- overlapping watchers producing valid non-torn turn JSON;
- runtime mirror absent, legacy-only, and structured-current cases;
- JSON version/enums/null assertions and human warning behavior.

## Compatibility and migration

- Existing `.acked-blocks` retains FIFO semantics and gains atomic writes.
- Existing `.seen-blocks` is ignored in place.
- `state/<id>.status` remains a compatibility mirror for one window.
- JSON moves to schema v2. `verdict` remains temporarily; consumers migrate from
  removed `new_block` to the explicit runtime/task/turn fields.
- Historical non-canonical handoffs surface a protocol error with remediation;
  do not silently discard or reinterpret them.
- Acceptance is not added as state.

## Risks and mitigations

| Risk | Mitigation |
| --- | --- |
| Agent settles before a handoff write is visible | Enforce append-before-end; add one bounded reconciliation delay only if real evidence requires it, never reader polling |
| Overlapping watchers race | Write complete deterministic JSON atomically and avoid increment cursors |
| Canonical headings reject old prose | Surface errors with remediation and preserve original files |
| JSON v2 breaks consumers | Version output, retain `verdict` temporarily, and fixture replacements |
| Parser and ack drift | Make both use the same implementation |

## Acceptance criteria

- Repeated human and JSON status reads write no files and return stable facts.
- Missing handoff exists only for an observed working-to-settled turn without a
  new canonical block.
- Initial reconciliation and repeated reads cannot manufacture missing reports.
- Independent readers and overlapping watchers do not suppress or corrupt state.
- Earlier open items remain until explicit ack.
- Status and list name runtime and task state separately; acceptance is absent.
- One parser defines block recognition, counts, fields, open items, and errors.
- Compatibility tokens, cursors, aliases, and schema migration are Bats-covered.
- `.seen-blocks` is no longer read or written.
