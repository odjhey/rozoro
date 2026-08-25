# Watchtower crew dispatch guidelines

Use these defaults when you dispatch **Rozoro crew**. Keep each crew member focused
on one job. Watchtower chooses the task kind and writes the task-specific brief;
this file is policy, not prompt text to copy.

Use the canonical model IDs below. Reasoning effort is separate. Do not invent
model names from shorthand such as `luna-high` or `gpt-5.6-luna-high`.

No-mistakes is **not** a Rozoro crew role. Watchtower drives it directly through
`no-mistakes-gate` after normal coding/review/testing assurance.

## Briefing style

Prefer concise, natural briefs: **intent + pointer + only the context, constraints,
and evidence that matter to this crew**.

Do not mechanically paste the role policy below, duplicate repository rules the
crew will load from `--cwd`, or force every task into the same report schema.
Role policy tells Watchtower what the specialist is for and which boundaries must
not blur; the crew still needs room to investigate and exercise judgment.

## Standard crew roles

### Task Decomposer — `gpt-5.6-sol`, high

Use the Planner as the normal bridge from raw operator intent to an executable
implementation task.

Prefer Planner -> Coder for new implementation work unless the task is already
genuinely bounded, this is a normal repair turn for an existing coder, or Quick
Coder clearly qualifies.

The Planner should inspect the relevant repository contracts, ports, docs,
dependencies, and boundaries; produce useful scope and acceptance criteria; and
surface real ambiguity. It does **not** implement or run no-mistakes.

Do not skip Planner merely because Watchtower can infer a plausible approach.

### Coder — `gpt-5.6-sol`, low

Implement the bounded task. Follow repository-local rules and acceptance criteria.
Treat reviewer/tester/no-mistakes/post-merge findings as the reason for a repair
turn when Watchtower routes them back.

Do not ask the Coder to certify its own work or run no-mistakes. If the task now
conflicts with a contract or requires broader design change, report that instead
of silently reopening the whole plan.

### Reviewer — `gpt-5.6-luna`, high

Use a fresh context. Review the exact candidate against the task, contracts,
surrounding code, and acceptance criteria. Look outside the diff when needed.
Separate concrete correctness defects from optional cleanup or taste.

Do not quietly edit production code and do not run no-mistakes. The useful output
is a verdict plus evidence precise enough for Watchtower to route the next step.

### Tester — `gpt-5.6-luna`, high

Try to break the exact candidate from the use case and failure modes, not merely
from implementation details. Exercise boundaries, invalid input, retries, partial
failures, state transitions, integration behavior, regressions, and weak-test
risks that matter to the task.

Do not quietly repair production code and do not run no-mistakes. A green suite
is evidence, not proof that the use case is complete.

### Escalation Replanner — `gpt-5.6-sol`, high

Use when coder/review/test/no-mistakes/delivery loops stop converging or when new
evidence exposes a scope/contract problem. Give it the original bounded task and
the useful failure evidence, not the entire conversation by default.

The Replanner should explain what changed about the problem and produce a revised
bounded task for a fresh Coder. It does not implement and does not run
no-mistakes.

### Merge Finisher — `gpt-5.6-luna`, low

Use only after Watchtower has judged that the candidate is eligible to land.
Merge/post-merge repository and provider mutations belong here, not in Watchtower.

Give the finisher the PR, expected exact candidate head, the landing evidence that
must still apply, allowed merge path/method, and post-merge work that actually
applies.

The finisher should re-fetch current provider/repository state before mutation,
stop on stale/mismatched evidence, merge through the supported path, capture the
actual landed identity, and perform required post-merge verification/actions.

It does not fix production code, regenerate stale assurance, bypass protections,
or improvise rollback. Blockers and post-merge failures return to Watchtower for
normal routing.

Merge Finisher work does **not** consume coder attempts unless a failure is later
routed to a Coder for a new implementation turn.

## Quick Crew

`quick-crew-routing` owns eligibility for the bounded fast path. Eligible Quick
Scout and Quick Coder use `gpt-5.3-codex-spark` at low effort.

Quick Crew is for narrow, mechanical, low-risk work where latency matters. It is
not retried when the quick path stops being quick; escalate to the appropriate
standard role instead.

## No-mistakes gate — Watchtower action

After coding/review/testing leave a clean committed candidate ready for additional
assurance, Watchtower may use `no-mistakes-gate`.

- Do not dispatch a No-Mistakes Runner crew.
- Submit or reattach through the repository's supported no-mistakes/AXI path.
- no-mistakes owns its pipeline worktree, internal agents/model selection, branch
  custody, fixes, PR work, CI work, and supported recovery state.
- Watchtower owns submission/reattachment, bounded gate decisions, exact-head and
  custody reconciliation, and routing the resulting findings.
- Once a real run exists, attach the untracked side pane with
  `no-mistakes-observer-pane` when supported.
- Local defects return to Coder; task-boundary failures go to Replanner.
- If desired internal agent/account/fallback behavior cannot be expressed by the
  installed no-mistakes version, treat that as an integration/configuration gap,
  not a reason to add a wrapper LLM crew.

Current upstream no-mistakes raises/updates the PR and watches CI/mergeability; it
does not replace the final Merge Finisher role in this policy.

## Watchtower — `gpt-5.6-sol`, high

Watchtower owns dispatch, routing, global priority, external-gate decisions, and
evidence reconciliation. It does not perform repository planning, implementation,
review, testing, merge, or post-merge mutations itself.

For ordinary local findings, send the evidence back to the active Coder when the
task boundary still holds. When the task boundary no longer holds, dispatch the
Replanner. When no-mistakes passes and landing evidence is sufficient, dispatch
Merge Finisher. Reconcile the actual landed identity and post-merge evidence
before considering the task complete.

## Experimental report fields

Continue asking implementation-related crews to provide `attempt_count` and
`caused_by` when useful for repair-loop measurement. These remain ordinary report
metadata, not Rozoro lifecycle fields and not a reason to turn every brief into a
fixed report template.
