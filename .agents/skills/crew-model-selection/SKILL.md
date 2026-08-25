---
name: crew-model-selection
description: >-
  Choose the task kind, model, reasoning effort, and dispatch path for a fresh
  Rozoro crew. Use immediately before Watchtower spawns a planning, coding,
  review, testing, merge/post-merge, or Quick Crew session. This skill selects
  the crew; it does not generate that crew's prompt.
---

# Crew model selection

Use this in **Watchtower immediately before every fresh Rozoro crew dispatch**.
Read current policy instead of answering from remembered defaults.

No-mistakes validation is **not** a crew dispatch. Use `no-mistakes-gate` for that
pipeline instead of this skill.

## Choose the task kind first

Read `templates/watchtower-crew-dispatch-guidelines.md` as the source of truth for
standard roles, canonical model IDs, reasoning effort, and role boundaries.

For new implementation work, treat the Task Decomposer as the normal bridge from
raw operator intent to a bounded coder task. Prefer Planner -> Coder unless one of
these is already true:

- the work qualifies for Quick Coder;
- the operator or an earlier Planner/Replanner already supplied a genuinely
  bounded implementation task with usable scope, constraints, and acceptance
  criteria;
- this is an ordinary repair turn being sent back to the existing coder; or
- the requested change is already narrow, mechanical, and sufficiently specified
  that another planning turn would add no useful information.

Do not skip planning merely because Watchtower can personally infer a plausible
implementation. Repository investigation and decomposition belong to the Planner,
not Watchtower.

Read `quick-crew-routing` when the work might qualify for the bounded Quick Crew
fast path. Quick Crew does not replace the standard role pipeline.

Then choose the role, model, and reasoning effort. Keep harness/profile identity
separate from model ID and reasoning effort.

## Compose the brief; do not template it

Watchtower writes the crew brief itself.

Return to the older concise style: **intent + pointer + only the context,
constraints, and evidence this crew needs for this task**. The canonical role
policy should influence Watchtower's judgment, but it is not a block of text to
copy into the prompt and not a required report schema.

A useful brief may be only a few lines. Examples of task-specific additions that
matter:

- Planner: source issue/request and any operator constraints or exclusions.
- Reviewer/Tester: exact candidate head, task/acceptance pointer, and relevant
  prior finding when one caused the dispatch.
- Merge Finisher: PR, expected head, applicable landing evidence, merge policy,
  and required post-merge work.
- Quick Scout/Coder: exact narrow question or mechanical change plus the quick
  path's stop/escalation condition.

Do not paste the whole role policy, repeat repository rules the crew will load
from its `--cwd`, or turn every brief into a checklist. Preserve enough context
for the crew to exercise judgment.

## Rules

- Current standard role/model/effort selection wins over older snapshots or
  machine-local policy copies.
- Use canonical model IDs exactly as written. Do not invent shorthand model
  names.
- Standard crew is the default. Quick Crew is an explicit bounded fast path only.
- The uploaded cross-machine blanket Pi-harness rule was discarded and must not
  be inferred as a global default.
- Do **not** create a No-Mistakes Runner role. A clean committed candidate is
  submitted and driven through the Watchtower-owned `no-mistakes-gate`; the
  no-mistakes pipeline owns its internal agents and model selection.
- Merge and post-merge repository/provider mutations are a **Merge Finisher crew**
  task. Watchtower decides that landing may proceed; the finisher performs the
  mutation and returns exact landed evidence.
- If a canonical source is missing, ambiguous, or internally inconsistent, report
  that condition instead of guessing.

Follow-up on an existing live task normally uses the same crew/context via
`./bin/rozoro send`; do not re-run fresh-crew selection merely because another
turn is needed. Re-run selection when Watchtower intentionally dispatches a new
task-kind crew such as reviewer, tester, replanner, merge finisher, or replacement
coder.
