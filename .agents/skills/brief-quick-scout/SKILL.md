---
name: brief-quick-scout
description: >-
  Brief a Quick Scout crew for one narrow, read-only fact-gathering task. Use when
  Watchtower has selected the Quick Scout task kind and needs to put the bounded
  Spark/low work contract and escalation marker into that crew's brief. Watchtower
  routes the task; the dispatched Quick Scout gathers the facts.
---

# Quick Scout briefing guideline

Use this when **Watchtower is preparing the brief for a Quick Scout crew** after
`quick-crew-routing` has determined that the task qualifies for the fast path.
Include the applicable contract below together with the exact question and source
pointer the scout should inspect.

Do not perform the repository fact gathering in Watchtower merely because this
skill is loaded. Render these instructions into the Quick Scout brief.

Use `gpt-5.3-codex-spark` at low effort for this task kind.

## Work contract to brief

The Quick Scout performs one narrow, read-only fact-gathering job and reports
exact evidence. This role is for speed, not judgment.

- Stay within the explicit question in the brief.
- Prefer direct repository evidence: exact files, symbols, commands, commit/PR identity, or other concrete facts.
- Keep exploration bounded. Do not start indefinite background work.
- Separate observed facts from inference.
- If the answer requires architecture/product judgment, broad context, or consequential uncertainty, stop and escalate instead of guessing.
- Do not edit files.
- Do not design solutions.
- Do not run no-mistakes.

## Escalation contract to brief

Do not retry the quick path. If the task is no longer narrow, read-only,
mechanical, and low-risk, require exactly:

```text
NEEDS_STANDARD_CREW
Reason:
Findings:
Suggested next step:
```

Useful evidence already gathered belongs under `Findings` so the standard crew
does not repeat cheap discovery.

## Report shape to brief

When the Quick Scout can answer safely, require:

- the exact question answered;
- concrete findings;
- source paths/commands/identities supporting them;
- remaining uncertainty, if any;
- recommended routing consequence, if Watchtower needs one.
