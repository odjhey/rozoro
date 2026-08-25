# Role-separated delivery

Use role separation when a change needs independent assurance, parallel work, or
controlled publication.

## Roles

- **Planner / Task Decomposer:** turns raw intent into bounded tasks, dependencies,
  acceptance criteria, and useful stacking/integration information.
- **Coder:** implements one bounded task and reports the exact candidate head.
- **Reviewer:** independently evaluates correctness and scope at an exact head.
- **Tester:** independently exercises behavior and failure modes at an exact head.
- **Replanner:** revises scope/dependencies when evidence shows the current task
  boundary is wrong or repair loops stop converging, while carrying the lineage's
  cumulative attempt/replan counters forward.
- **No-Mistakes Runner:** thin Rozoro crew that submits/reattaches an exact
  candidate to the configured no-mistakes pipeline, listens through its supported
  Git/CLI/AXI surface, and reports structured run evidence.
- **Workset Merger:** reconstructs dependency/stack order for one workset,
  integrates participating branches, reads assurance/no-mistakes results in that
  context, decides what needs repair or re-planning, and performs final
  merge/post-merge work when authorized.
- **Watchtower:** owns cross-project/workset priority, dispatch, routing, attempt/
  replan accounting, and operator interaction.

## Workset flow

1. Identify the intended deliverable/workset.
2. Use Planner when the work needs decomposition, dependency discovery, or a
   stacking plan.
3. Dispatch bounded tasks to Coders, parallelizing independent work.
4. Bind Reviewer/Tester evidence to exact candidate heads as required by policy.
5. Route local findings back to the relevant Coder while the current attempt
   ceiling allows it; use Replanner when the task/dependency boundary changes or
   the implementation loop is not converging.
6. Replanner receives the current plan plus useful failure evidence and the
   cumulative `attempt_count`, `attempt_limit`, and `replan_count`. A materially
   revised plan extends the Coder ceiling by 10, up to a hard limit of 30 total
   Coder attempts. The lineage may use at most 3 Replanner turns; counters never
   reset because a fresh Coder, branch, worktree, or plan is created.
7. When an exact committed candidate needs no-mistakes assurance, dispatch a
   No-Mistakes Runner with the candidate identity and selected machine/global
   no-mistakes profile.
8. Keep each task branch/head and its assurance evidence attached to the workset.
9. Dispatch or reuse a Workset Merger when branches must be integrated, stacked,
   ordered, or landed.
10. The Workset Merger reads the Planner/Decomposer result when available, then
    reconciles it against actual branches/heads and determines the current merge
    order.
11. Integrate in dependency order. Any integration-created head gets the exact-head
    assurance required by repository policy.
12. Give no-mistakes results to the Workset Merger when their interpretation
    depends on the integrated workset. It classifies findings as local repair,
    integration fallout, or a planning/dependency problem and reports the next
    route to Watchtower.
13. When the integrated candidate is ready to land, apply `/afk` policy:
    - ON: the Workset Merger may perform the final supported merge when evidence,
      repository policy, and existing operator authority permit.
    - OFF: the merger stops immediately before the final merge mutation and asks
      the operator to confirm.
14. Record the actual landed identity and required post-merge evidence before the
    workset is complete.

A one-task workset follows the same flow with the integration step collapsed to a
single candidate.

## Attempt and replan budget

Use `attempt-budget` as the routing authority for non-converging implementation
lineages.

The normal progression is:

```text
initial plan:  attempt_limit=10  replan_count=0
replan #1:     attempt_limit=20  replan_count=1
replan #2:     attempt_limit=30  replan_count=2
replan #3:     attempt_limit=30  replan_count=3
```

`attempt_count` is cumulative. Replanning extends the lineage instead of resetting
it. The third Replanner turn is available for final restructuring, splitting, or
deferral decisions but does not authorize Coder attempt 31.

At the current Coder ceiling, let assurance for the exact candidate finish. If
another code repair is required and another budget-extending replan is available,
replan. At the hard 30-attempt ceiling or after 3 Replanner turns, defer/escalate
the lineage rather than creating an unbounded retry loop.

## No-mistakes configuration

Repository `.no-mistakes.yaml` and the selected global no-mistakes profile are the
configuration authorities for the pipeline. Global configuration lives at
`~/.no-mistakes/config.yaml` unless `NM_HOME` selects another profile.

Current no-mistakes supports an `agent` value or ordered fallback list and
`agent_config` entries for per-agent model/effort. The optional Rozoro machine
profile may say which of those profiles/accounts are available locally; the
No-Mistakes Runner verifies the effective selection rather than rewriting config
for each run.

## Briefing

Watchtower writes each brief from the current task/workset state. Prefer
**intent + pointer + only the context, constraints, and evidence this specialist
needs**.

For Replanner, include the current task/plan, useful failed directions and findings,
and the current `attempt_count`, `attempt_limit`, and `replan_count`.

For Workset Merger, include the workset intent, plan/decomposition when available,
participating exact heads, dependency clues, assurance/no-mistakes evidence,
target merge policy, and current `/afk` state.

## Learning

The Watchtower is allowed to begin with incomplete project context. Plans, crew
handoffs, merged results, no-mistakes runs, and operator steering become reusable
durable context for later work in that project.

The optional no-mistakes Observatory is a qualitative learning surface. Keep run
IDs and prefer structured no-mistakes data for durable timing, retries, fixes,
findings, agent/model use, and outcomes.
