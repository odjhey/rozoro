---
name: no-mistakes-observatory
description: >-
  Maintain the dedicated Herdr visualization surface for active no-mistakes runs.
  Use whenever Watchtower submits or reattaches a no-mistakes gate so each run's
  `no-mistakes attach` graph is visible in a persistent Observatory without
  creating a Rozoro crew or a second control owner.
---

# No-mistakes Observatory

Use this in **Watchtower for every active no-mistakes gate**.

The Observatory exists so the operator can watch no-mistakes pipeline graphs,
compare runs, and learn where review/fix/test/CI time and retries are accumulating.
It is presentation only. Structured no-mistakes/AXI state remains authoritative.

## Layout

Prefer one persistent, untracked Herdr tab for the Watchtower workspace named or
labeled **no-mistakes Observatory**.

Inside that tab:

- create one pane per active no-mistakes run;
- label the pane with enough task/run identity to distinguish concurrent gates;
- use the target repository as that pane's working directory when the installed
  no-mistakes attach flow is repository-scoped; and
- run `no-mistakes attach` using the supported syntax for the installed version.

Do not make the Observatory tab or its panes Rozoro tasks, crews, sessions, or
mailbox owners. Do not count them as agent capacity.

If the installed Herdr version cannot create the preferred multi-pane Observatory,
use the smallest supported untracked observation surface for the run, such as a
separate observer tab. Record the degraded layout rather than inventing terminal
control commands.

## Lifecycle

When the first active no-mistakes run appears, create or reuse the Observatory.
For later concurrent gates, add/reuse a pane for the matching run instead of
splitting the Watchtower pane repeatedly.

Do not steal focus from Watchtower when creating or updating the Observatory.

When a no-mistakes run becomes terminal, keep its graph/scrollback available
through the associated landing/post-merge episode so the operator can inspect the
whole delivery path. It may be closed after the task's final delivery evidence is
captured, when the pane is superseded by a newer run for the same lineage, or on
explicit operator cleanup.

An Observatory pane ending or failing has no task or pipeline lifecycle meaning.
It must not block the real no-mistakes gate.

## Observe, do not control

The Observatory may display stage progress, findings, retries, fixes, gates, and
other graph/TUI information exposed by no-mistakes. It must not:

- edit repository files;
- move refs or branches;
- become an AXI/no-mistakes controller;
- answer gates by itself;
- become a Rozoro crew; or
- be treated as proof that checks passed or custody returned.

Watchtower makes decisions through supported structured no-mistakes/AXI commands.
Treat the Observatory as a human-readable projection for inspection and learning.

## Learning and optimization

Use the live graph to spot hypotheses worth measuring, for example:

- stages that dominate elapsed time;
- repeated review/fix or test/fix loops;
- recurring CI repair classes;
- expensive stages that add little new evidence;
- agent/model choices that appear to cause retries; and
- work that could move earlier into Planner/Coder/Tester before the gate.

Do not turn visual impressions into policy by themselves. For durable optimization,
record the run ID and prefer structured evidence exposed by no-mistakes for stage
timing, retries, fixes, agent/model usage, findings, and outcomes when available.

If useful structured telemetry is missing, treat that as an instrumentation gap to
track separately rather than scraping terminal pixels or treating TUI text as a
stable machine contract.
