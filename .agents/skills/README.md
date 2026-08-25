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

| Skill | When Watchtower uses it |
| --- | --- |
| `crew-model-selection` | Immediately before every fresh Rozoro crew dispatch: choose task kind, current canonical model/effort, Quick Crew eligibility, and applicable `brief-*` guideline. |
| `no-mistakes-gate` | When a clean committed candidate is ready for no-mistakes assurance: submit or reattach the external run, drive AXI gates, reconcile exact-head/custody evidence, and route findings. |
| `delivery-evidence` | Reconcile exact-head evidence, decide what runs next, and record bounded unattended decisions. |
| `attempt-budget` | Decide whether another coder attempt is allowed and when exhausted work should be deferred/revisited. |
| `quick-crew-routing` | Decide whether a task qualifies for Quick Scout/Quick Coder; standard crew remains the default. |
| `no-mistakes-observer-pane` | For every active no-mistakes gate, open/close the untracked side pane beside Watchtower when the local Herdr pane operation is supported. |

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
| `brief-rozoro-coder` | Coder working on Rozoro | Render the applicable Rozoro-specific authoring/validation rules into the coder brief, then dispatch. |
| `brief-quick-scout` | Quick Scout | Render the narrow read-only Spark/low contract and escalation marker into the scout brief, then dispatch. |
| `brief-quick-coder` | Quick Coder | Render the one-attempt mechanical Spark/low contract and escalation marker into the coder brief, then dispatch. |

There is intentionally **no `brief-no-mistakes-*` crew role**. No-mistakes is a
Watchtower-managed external gate, not a spawned Rozoro crew.

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

## Fresh-dispatch bootstrap

`templates/watchtower.md` requires `crew-model-selection` before every fresh
**Rozoro crew** start. That skill reads the canonical standard dispatch policy and,
when relevant, Quick Crew routing, then names the applicable `brief-*` guideline
to render into the task body.

No-mistakes assurance is outside that fresh-crew path. When a committed candidate
is ready, Watchtower invokes `no-mistakes-gate` directly. Once an active run
exists, Watchtower invokes `no-mistakes-observer-pane` by default and attaches an
untracked side pane beside the Watchtower pane.

A follow-up turn on the same live crew task is different: use `./bin/rozoro send`
and preserve the existing crew context unless Watchtower is intentionally
dispatching a new task-kind crew.

## Model routing

Current standard Rozoro crew model selection remains authoritative in
`templates/watchtower-crew-dispatch-guidelines.md`.

`quick-crew-routing` is a bounded fast-path exception: eligible Quick Scout and
Quick Coder tasks use `gpt-5.3-codex-spark` at low effort. It does not redefine
any standard role assignment and must not be retried when the quick path fails.

No-mistakes owns its own internal pipeline-agent/model/fallback configuration.
Rozoro does not select those internal models by wrapping the pipeline in a crew.
If the desired no-mistakes agent/account/fallback policy cannot be expressed by
the installed no-mistakes version, treat that as an integration/configuration gap
in no-mistakes rather than adding a wrapper crew.

Do not import machine-specific harness defaults into global Rozoro role policy.

## Attempt budget

Implementation lineages have ten coder attempts derived from durable coder turns.
Attempt 10 may complete normal review/test/gate assurance. If that evidence asks
for another coder repair, do not start attempt 11.

An exhausted lineage is deferred while other runnable work exists. Reconsider
deferred work when the runnable queue is empty, or earlier only when materially
new evidence/tooling changes the premise or the operator explicitly reprioritizes
it.

## Boundary rule

**Watchtower chooses task kinds, prepares crew briefs, dispatches crews, drives
external gates, reconciles reports/evidence, and decides what runs next. Crew
performs repository planning, implementation, review, and testing described by its
brief. No-mistakes performs its own pipeline work under its own custody.**

When a crew report or no-mistakes run exposes a new routing decision, Watchtower
records the decision and sends work to the appropriate existing or fresh crew. Do
not create an extra crew merely to proxy a tool that already owns its pipeline.