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
`templates/watchtower-crew-dispatch-guidelines.md`. This skill does not redefine
standard role models or no-mistakes fallback policy.

## Eligibility

Use Quick Crew only when all relevant conditions hold:

- the work is small and bounded;
- the expected behavior is mechanical rather than design-heavy;
- risk is low;
- latency matters enough to justify the fast path;
- the task is not expected to need long/background work; and
- a single quick attempt is likely to be enough.

Use `gpt-5.3-codex-spark` at low effort for the Quick Crew roles below.

### Quick Scout

Use for narrow, read-only repository fact gathering.

Allowed examples include locating a symbol, confirming a file/flag/reference,
checking a small dependency relationship, or gathering exact evidence needed for
a routing decision.

Do not use Quick Scout for broad analysis, architecture or product decisions,
indefinite exploration, or authoritative conclusions under meaningful
uncertainty.

When selected, read `.agents/skills/quick-scout/SKILL.md` and render the
applicable instructions into the Quick Scout crew brief.

### Quick Coder

Use only for localized mechanical implementation with explicit scope and
acceptance criteria and no meaningful design ambiguity.

Do not use Quick Coder for API/subsystem redesign, cross-cutting changes, scope
expansion, consequential behavior interpretation, or repeated repair attempts.

When selected, read `.agents/skills/quick-coder/SKILL.md` and render the
applicable instructions into the Quick Coder crew brief.

Consequential Quick Coder output still goes through the standard independent
review and testing required by repository policy. A quick completion is not a
validation shortcut.

## Immediate escalation

Do not retry Quick Crew when the quick path stops being quick. Escalate to the
appropriate standard role as soon as scope broadens, confidence drops, a retry is
needed, broader context becomes necessary, or meaningful judgment appears.

A Quick Crew report that needs escalation must use exactly:

```text
NEEDS_STANDARD_CREW
Reason:
Findings:
Suggested next step:
```

Watchtower consumes that report and dispatches the appropriate standard crew. Do
not silently turn the same Quick Crew session into a standard role.

## Precedence

- Standard crew is the default.
- Current standard model selection in the canonical dispatch guidelines wins.
- Current no-mistakes target/fallback policy wins.
- Do not import machine-specific harness rules into Quick Crew routing.
