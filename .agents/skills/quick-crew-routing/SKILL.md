---
name: quick-crew-routing
description: >-
  Decide whether Watchtower should dispatch a Quick Scout or Quick Coder for a
  bounded task. Use when the work is narrow, mechanical, low-risk, and
  latency-sensitive enough to benefit from the fast path.
---

# Quick Crew routing

Quick Crew is an optimization for a small bounded task. Use
`crew-model-selection` after deciding that the quick path applies so execution is
resolved against this machine's verified availability.

## Eligibility

Use Quick Crew when all relevant conditions hold:

- the work is small and bounded;
- expected behavior is mechanical rather than design-heavy;
- risk is low;
- latency matters;
- the task is not expected to need long/background work; and
- a single quick attempt is likely to be enough.

The preferred Quick Crew target is `gpt-5.3-codex-spark` at low effort when this
machine can run it. If the fast target is unavailable, route the task to the
appropriate standard role instead of inventing another quick tier.

### Quick Scout

Use for one narrow, read-only repository fact-gathering question: locate a symbol,
confirm a file/flag/reference, check a small dependency relationship, or gather
exact evidence needed for routing.

Broader analysis, architecture/product decisions, or uncertainty that can change
the work belong to the normal Planner/Reviewer/other specialist path.

### Quick Coder

Use for localized mechanical implementation with explicit scope and acceptance
criteria and no meaningful design ambiguity.

Consequential Quick Coder output still receives the independent assurance required
by repository policy and participates in its workset like any other candidate.

## Brief

Write the exact narrow action and pointer plus any constraint the crew cannot
reliably infer from the repository/workset. Keep the quick task small enough that
the stop condition is obvious.

## Escalation

As soon as scope broadens, confidence drops, a retry is needed, broader context
becomes necessary, or meaningful design judgment appears, route the evidence to
the appropriate standard role.

When practical, the Quick Crew handoff can make that transition explicit:

```text
NEEDS_STANDARD_CREW
Reason:
Findings:
Suggested next step:
```

Carry forward useful evidence already gathered so the standard crew can continue
from it.
