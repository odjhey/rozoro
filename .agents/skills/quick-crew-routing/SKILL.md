---
name: quick-crew-routing
description: >-
  Decide whether Watchtower should dispatch a Quick Scout or Quick Coder instead
  of the standard crew for a bounded task. Use during Watchtower routing when the
  work may be narrow, mechanical, low-risk, and latency-sensitive. Standard crew
  remains the default.
---

# Quick Crew routing

Use this in **Watchtower while choosing the task kind and dispatch path**. Quick
Crew is an optimization, never a replacement for the standard role pipeline.

Current standard model selection remains authoritative in
`templates/watchtower-crew-dispatch-guidelines.md`.

## Eligibility

Use Quick Crew only when all relevant conditions hold:

- the work is small and bounded;
- the expected behavior is mechanical rather than design-heavy;
- risk is low;
- latency matters enough to justify the fast path;
- the task is not expected to need long/background work; and
- a single quick attempt is likely to be enough.

Use `gpt-5.3-codex-spark` at low effort for both Quick Crew task kinds.

### Quick Scout

Use for one narrow, read-only repository fact-gathering question: locate a symbol,
confirm a file/flag/reference, check a small dependency relationship, or gather
exact evidence needed for routing.

Do not use Quick Scout for broad analysis, architecture/product decisions,
indefinite exploration, or authoritative conclusions under meaningful
uncertainty.

Watchtower should write a small natural brief containing the exact question and
pointer. Do not turn the Quick Scout prompt into a copied role contract.

### Quick Coder

Use only for localized mechanical implementation with explicit scope and
acceptance criteria and no meaningful design ambiguity.

Do not use Quick Coder for API/subsystem redesign, cross-cutting changes, scope
expansion, consequential behavior interpretation, or repeated repair attempts.

Watchtower should write a small natural brief containing the exact change,
acceptance criteria, and any task-specific repository constraint that matters.

Consequential Quick Coder output still goes through the standard independent
review and testing required by repository policy. A quick completion is not a
validation shortcut.

## Immediate escalation

Do not retry Quick Crew when the quick path stops being quick. Escalate to the
appropriate standard role as soon as scope broadens, confidence drops, a retry is
needed, broader context becomes necessary, or meaningful judgment appears.

A Quick Crew report that needs escalation should make the condition unmistakable,
using this marker when practical:

```text
NEEDS_STANDARD_CREW
Reason:
Findings:
Suggested next step:
```

Useful evidence already gathered should travel with the escalation so the
standard crew does not repeat cheap discovery. Do not silently turn the same
Quick Crew session into a standard role.

## Precedence

- Standard crew is the default.
- Current standard model selection in the canonical dispatch guidelines wins.
- No-mistakes is a separate Watchtower-managed external gate.
- Do not import machine-specific harness rules into Quick Crew routing.
