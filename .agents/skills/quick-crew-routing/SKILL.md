---
name: quick-crew-routing
description: >-
  Decide whether a bounded task can use Quick Crew instead of the standard crew.
  This is Watchtower-owned routing policy. Standard crew remains the default;
  Quick Crew is only for narrow, mechanical, low-risk work where latency matters.
metadata:
  execution-owner: watchtower
  watchtower-action: invoke-directly
  derived-from: uploaded-watchtower-policy/06-quick-crew-dispatch.md
---

# Quick Crew routing

Use Quick Crew as an optimization, never as a replacement for the standard role
pipeline.

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

When selected, read `.agents/skills/quick-scout/SKILL.md` and incorporate the
applicable role instructions into the crew brief.

### Quick Coder

Use only for localized mechanical implementation with explicit scope and
acceptance criteria and no meaningful design ambiguity.

Do not use Quick Coder for API/subsystem redesign, cross-cutting changes, scope
expansion, consequential behavior interpretation, or repeated repair attempts.

When selected, read `.agents/skills/quick-coder/SKILL.md` and incorporate the
applicable role instructions into the crew brief.

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

The Watchtower consumes that report and dispatches the appropriate standard
crew. Do not silently turn the same Quick Crew session into a standard role.

## Precedence

- Standard crew is the default.
- Current standard model selection in the canonical dispatch guidelines wins.
- Current no-mistakes target/fallback policy wins.
- Do not import machine-specific harness rules into Quick Crew routing.
