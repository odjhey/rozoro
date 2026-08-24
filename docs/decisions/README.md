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
