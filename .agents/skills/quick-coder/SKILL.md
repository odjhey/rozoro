---
name: quick-coder
description: >-
  Brief a Quick Coder crew for one localized, mechanical, low-risk implementation
  task. Use when Watchtower has selected the Quick Coder task kind and needs to
  put the Spark/low one-attempt contract, scope limits, checks, and escalation
  marker into that crew's brief.
---

# Quick Coder briefing guideline

Use this when **Watchtower is preparing the brief for a Quick Coder crew** after
`quick-crew-routing` has determined that the task qualifies for the fast path.
Include the applicable contract below together with explicit scope, acceptance
criteria, and repository constraints.

Do not implement the repository change in Watchtower merely because this skill is
loaded. Render these instructions into the Quick Coder brief.

Use `gpt-5.3-codex-spark` at low effort for this task kind.

## Eligibility contract to brief

Proceed only while the work remains:

- localized;
- low-risk;
- mechanically understandable;
- free of meaningful design ambiguity; and
- unlikely to require more than one quick implementation attempt.

Do not use this role to redesign APIs/subsystems, reinterpret ambiguous behavior,
make cross-cutting changes, expand scope, or perform repeated repair attempts.

## Work contract to brief

- Implement only the bounded change in the brief.
- Follow repository-local rules and run the deterministic checks appropriate to the changed surface.
- Add or update focused behavioral tests when the change requires them.
- Do not self-certify the result as independently reviewed or tested.
- Do not run no-mistakes.
- Do not broaden the task to make the quick path succeed.

Consequential output still requires the standard independent review and testing
that repository policy calls for.

## Escalation contract to brief

The quick path gets one implementation attempt. If a retry is required, scope
broadens, confidence drops, broader context is needed, or meaningful judgment
appears, stop and require exactly:

```text
NEEDS_STANDARD_CREW
Reason:
Findings:
Suggested next step:
```

Include the branch/head and useful partial evidence under `Findings` when
available. Do not keep repairing with Spark.

## Report shape to brief

When completed, require:

- exact scope implemented;
- files/behavior changed;
- checks and tests run;
- exact branch/head when available;
- remaining uncertainty;
- whether standard review/testing is ready to proceed.
