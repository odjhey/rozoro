# Decisions

This directory contains lightweight architectural decision records for choices that constrain future Rozoro work.

The goal is not ceremony. A decision record exists so a future crew can answer **why this boundary exists, what alternatives were considered, and what would have to change to reverse it** without reconstructing the decision from chat history or old PR discussion.

## ADR-lite format

Use one Markdown file per decision:

```md
# ADR-NNNN: Short decision title

review: pending|approved|rejected
date: YYYY-MM-DD
gate: N        # optional; include only when tied to a numbered gate
supersedes: ... # optional

## Context
What problem or ambiguity forced a decision?

## Options
1. Option A — tradeoff.
2. Option B — tradeoff.

## Choice
What are we choosing and what exact boundary does it establish?

## Consequences
What becomes easier, harder, required, or explicitly out of scope?
```

## Review semantics

- `review: pending` — proposed direction; implementation must not treat it as settled policy.
- `review: approved` — accepted product/architecture constraint.
- `review: rejected` — preserved for history but must not guide new implementation.
- `gate: N` — optional link to a numbered product/release gate when the decision is specifically part of that gate.

If an approved decision changes, prefer a new ADR that `supersedes` the old one rather than rewriting history until the reversal is invisible.

## Current decisions

- [ADR-0001: One primary watchtower; operator owns priority](0001-one-primary-watchtower.md)
- [ADR-0002: Harness-native lifecycle is semantic truth](0002-harness-native-lifecycle.md)
- [ADR-0003: Events, projections, and delivery acknowledgements stay separate](0003-events-projections-delivery.md)
- [ADR-0004: Require first-class watchtower attention identity](0004-watchtower-mailbox.md)
- [ADR-0005: Keep repository workflow policy above Rozoro core](0005-workflow-boundary.md)
- [ADR-0006: Resolve cross-machine Watchtower policy differences](0006-cross-machine-watchtower-policy-resolution.md) — superseded by ADR-0009 and ADR-0012
- [ADR-0007: Select no-mistakes auto model through the invoking harness](0007-no-mistakes-auto-harness-selection.md) — superseded by ADR-0008 and ADR-0009
- [ADR-0008: Treat no-mistakes as an external gate](0008-no-mistakes-external-gate.md) — superseded by ADR-0009
- [ADR-0009: Use workset mergers, runner crews, and machine-local routing profiles](0009-workset-merger-runner-and-machine-profile.md) — fixed delivery-role roster and implementation-only repair-accounting boundary superseded by ADR-0014
- [ADR-0010: CLI reconcile delivers the changed-task delta of a generation window](0010-cli-reconcile-changed-task-delta.md)
- [ADR-0011: Named Watchtowers and versioned presets](0011-named-watchtowers-and-versioned-presets.md) — policy-override boundary superseded by ADR-0013
- [ADR-0012: Role model assignments live in durable operator policy](0012-durable-role-model-policy.md)
- [ADR-0013: Mission-composed watchtower policy](0013-mission-composed-watchtower-policy.md)

- [ADR-0014: Delivery failure routing and ad-hoc specialists](0014-delivery-failure-routing-and-ad-hoc-specialists.md)
