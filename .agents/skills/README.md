# Skill ownership and routing

These skills are loaded in the **Watchtower context**. Rozoro does not currently
pass skill objects or skill references into crew sessions.

There are two semantic categories. The distinction is documented here and in each
skill's `description` and body; do not rely on custom frontmatter metadata for
routing because the supported harnesses do not provide a portable contract for
our own ownership keys.

## Watchtower action skills

Watchtower uses these directly while orchestrating, reconciling evidence, routing,
or observing work.

| Skill or prompt | When Watchtower uses it |
| --- | --- |
| `delivery-evidence` | Reconcile exact-head evidence, decide what runs next, and record bounded unattended decisions. |
| `attempt-budget` | Decide whether another coder attempt is allowed and when exhausted work should be deferred/revisited. |
| `quick-crew-routing` | Decide whether a task qualifies for Quick Scout/Quick Coder; standard crew remains the default. |
| `no-mistakes-observer-pane` | Open/close an untracked observer pane around an active no-mistakes run. |
| `prompts/watchtower-model-selection.md` | Retrieve current standard role/model/effort and no-mistakes fallback policy before dispatch. |

These are Watchtower actions. They are not instructions to paste wholesale into a
crew brief.

## `brief-*` crew-briefing guidelines

Every skill whose name starts with `brief-` tells Watchtower **what to put in the
brief when spawning a specific task-kind crew**. Loading one does not mean
Watchtower should perform that crew's repository work.

| Briefing guideline | Task-kind crew | Watchtower action |
| --- | --- | --- |
| `brief-task-planner` | Task Decomposer / Escalation Replanner | Render the applicable decomposition/replanning contract and report shape into the planning crew brief, then dispatch. |
| `brief-reviewer` | Reviewer | Render the review contract, exact-head inputs, and report shape into a fresh reviewer brief, then dispatch. |
| `brief-tester` | Tester | Render the behavioral/failure-mode test contract and report shape into the tester brief, then dispatch. |
| `brief-no-mistakes-recovery` | No-Mistakes Runner | Render the supported recovery/custody contract and exact branch/run evidence into the runner brief, then dispatch/resume. |
| `brief-rozoro-coder` | Coder working on Rozoro | Render the applicable Rozoro-specific authoring/validation rules into the coder brief, then dispatch. |
| `brief-quick-scout` | Quick Scout | Render the narrow read-only Spark/low contract and escalation marker into the scout brief, then dispatch. |
| `brief-quick-coder` | Quick Coder | Render the one-attempt mechanical Spark/low contract and escalation marker into the coder brief, then dispatch. |

### Briefing rule

A `brief-*` guideline is applied only when its relevant instructions are included
in the task brief that the crew actually receives.

Keep the brief focused. Include:

- the task-kind/role contract;
- constraints that matter to this task;
- task-specific source pointers and evidence;
- acceptance criteria or exact-head identity when relevant; and
- the required report/escalation shape.

Do not paste unrelated policy or the entire skill library. Do not assume a skill
name, repo-local skill discovery, preset, system rule, or custom frontmatter field
is transmitted to a crew by Rozoro today.

## Model routing

Current standard model selection remains authoritative in
`templates/watchtower-crew-dispatch-guidelines.md`. Current no-mistakes target
fallback also remains authoritative there/current no-mistakes policy.

`quick-crew-routing` is a bounded fast-path exception: eligible Quick Scout and
Quick Coder tasks use `gpt-5.3-codex-spark` at low effort. It does not redefine
any standard role assignment and must not be retried when the quick path fails.

Do not import machine-specific harness defaults into global role policy.

## Attempt budget

Implementation lineages have ten coder attempts derived from durable coder turns.
Attempt 10 may complete normal review/test/gate assurance. If that evidence asks
for another coder repair, do not start attempt 11.

An exhausted lineage is deferred while other runnable work exists. Reconsider
deferred work when the runnable queue is empty, or earlier only when materially
new evidence/tooling changes the premise or the operator explicitly reprioritizes
it.

## Boundary rule

**Watchtower chooses the task kind, prepares the brief, dispatches, reconciles
reports, and decides what runs next. Crew performs repository planning,
implementation, review, testing, and pipeline/recovery work described by its
brief.**

When a crew report exposes a new routing decision, Watchtower consumes the report,
records the decision, and dispatches the next task-kind crew. Do not silently
change the current crew's role just to avoid another dispatch.
