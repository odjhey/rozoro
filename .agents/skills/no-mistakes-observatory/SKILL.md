---
name: no-mistakes-observatory
description: >-
  Maintain an optional dedicated Herdr visualization surface for active
  no-mistakes runs. Use when the operator wants live pipeline graphs or when a
  persistent visual learning surface would help compare active runs.
---

# No-mistakes Observatory

The Observatory is a human-readable projection of no-mistakes runs. Structured
no-mistakes/AXI state and the No-Mistakes Runner's handoff are the operational
inputs.

## Layout

Prefer one persistent, untracked Herdr tab for the Watchtower workspace named or
labeled **no-mistakes Observatory**.

Inside that tab:

- create one pane per active no-mistakes run when useful;
- label the pane with enough project/workset/task/run identity to distinguish
  concurrent gates;
- use the target repository as the pane's working directory when attach is
  repository-scoped; and
- run `no-mistakes attach` using the syntax supported by the installed version.

The Observatory panes are display surfaces, not Rozoro tasks or capacity-bearing
crew. The separate No-Mistakes Runner crew owns Rozoro-side execution/listening
for the run.

## Lifecycle

Create or reuse the Observatory when an active run is worth showing. Add panes for
concurrent runs without stealing focus from Watchtower.

After a run becomes terminal, keep its graph/scrollback through the associated
integration/landing episode when practical. Close it after final delivery evidence
is captured, when superseded by a newer run for the same lineage, or on operator
cleanup.

An Observatory pane ending has no task, gate, or custody meaning.

## Learning and optimization

Use the graph to form hypotheses about:

- expensive stages;
- repeated review/fix or test/fix loops;
- recurring CI repair;
- agent/model choices correlated with retries; and
- work that might move earlier into planning, coding, or testing.

Keep run IDs and prefer structured no-mistakes evidence for durable timing,
retries, fixes, findings, model/agent use, and outcomes. Treat missing structured
telemetry as an instrumentation opportunity rather than a reason to make the TUI
a machine contract.
