# Skill ownership and routing

Project skills under `.agents/skills/` are **Watchtower tools**. They help the
Watchtower make routing and operator-policy decisions; the Watchtower still writes
the task-specific brief for each crew.

A useful brief is usually **intent + pointer + only the context, constraints, and
evidence this crew needs**. Repository-local rules come from the crew's `--cwd`.

## Watchtower action skills

| Skill | When Watchtower uses it |
| --- | --- |
| `crew-model-selection` | Before a fresh Rozoro crew dispatch: choose task kind and resolve an available harness/model/effort. |
| `quick-crew-routing` | Decide whether a bounded task qualifies for Quick Scout/Quick Coder. |
| `delivery-evidence` | Reconcile exact-head assurance and delivery evidence when deciding what runs next. |
| `attempt-budget` | Track cumulative Coder attempts and Replanner turns, extend bounded lineages through replanning, and defer exhausted work. |
| `afk` | Read or change unattended merge authority. `/afk` is ON by default. |
| `get-me-up-to-speed` | Give a concise evidence-based summary under **Done**, **Current**, and **Next**; also triggered by `gmuts`. |
| `no-mistakes-observatory` | Maintain the optional human visualization surface for active no-mistakes runs. |
| `watchtower-attention-ledger` | Record/supersede attention items during reconcile, note handling decisions as you route, and `prime` a fresh/resumed session from disk. |
| `watchtower-policy-status` | Explain applicable Watchtower rules with activation-verified source scope. |

Skills are orchestration guidance, not prompt blocks to paste into crew sessions.

## Context grows from work

A Watchtower is expected to start with incomplete project context. It learns the
working shape of a project from operator instructions, repository-local docs, task
plans, crew handoffs, gate results, and delivery outcomes.

Reuse relevant durable task results when they answer a question or constrain a new
turn. Load deeper repository context when a task requires it. The Watchtower does
not need a reconstructed history of superseded conventions before it can work.

## One Watchtower may cover multiple projects

Every fresh crew has an explicit `--cwd`. A single Watchtower may therefore route
work across unrelated repositories at the same time.

Keep project facts scoped to the repository/workset they came from. Cross-project
priority belongs to the Watchtower/operator; repository implementation and policy
belong to the target project and its crew.

## Optional machine profile

A Watchtower may read `$ROZORO_HOME/config/machine.md` (default
`~/.rozoro/config/machine.md`) for machine-local facts such as:

- installed/usable harnesses;
- available model families or preferred defaults;
- named harness/account profiles and required environment;
- no-mistakes profiles (`NM_HOME`, agent preference, or launcher notes); and
- local capacity/cost preferences useful for routing.

The file is deliberately text-based policy for now, not a versioned machine
protocol. Treat it as an availability/preference hint and verify the selected
harness/profile when dispatching. Explicit operator instructions and
repository-local requirements still win.

## Crew roles

The canonical role contracts and dispatch semantics live in
`templates/watchtower-crew-dispatch-guidelines.md`. Concrete per-role
model/effort assignments and global denials are durable operator policy under
`$ROZORO_HOME/watchtower-policies/` (ADR-0012). Machine profiles filter authorized
targets by fresh availability; presets only realize authorized selections.
Missing or ambiguous assignments fail closed.

The important ownership boundaries are:

- **Planner/Task Decomposer** bounds the work and owns its execution strategy:
  dependencies, parallel groups, stacks/sequences, fan-out/fan-in, and intended
  integration order.
- **Coder** implements a bounded task.
- **Reviewer** and **Tester** provide independent assurance.
- **Replanner** changes a non-converging task/dependency/execution strategy while
  preserving cumulative lineage counters; use `attempt-budget` to decide whether
  another Coder/Replanner turn is available.
- **No-Mistakes Runner** is a thin crew that submits/attaches to the configured
  no-mistakes pipeline, keeps the run alive/listened to, and returns structured
  run evidence. It does not replace no-mistakes' own pipeline agents.
- **Workset Merger** executes and reconciles the Planner/Replanner strategy against
  actual branches, reads no-mistakes results in workset context, routes evidence
  that requires repair/replanning, and performs final merge/post-merge work when
  current authority permits.
- **Watchtower** owns cross-workset priority, dispatch, routing, and operator
  interaction.

## Worksets and merging

When several tasks contribute to one deliverable, preserve their relationship as a
workset. The Planner/Replanner plan should identify which tasks may run in parallel,
which are stacked or sequential, and how they are expected to fan in and integrate.
Watchtower dispatches according to that plan.

Give the Workset Merger the current execution strategy plus task branches/heads and
assurance results. The merger validates and realizes the planned dependency/stack
order against actual results instead of treating completed crew as an unordered bag
or silently replacing the plan. If repository evidence invalidates the strategy,
route that evidence to Replanner.

No-mistakes findings are most useful when read by the same merger that understands
the integrated workset shape.

## No-mistakes

No-mistakes remains authoritative for its own disposable worktree, internal
pipeline agents, fixes, PR/CI work, and structured AXI state. The No-Mistakes
Runner is the Rozoro-side operator for that external pipeline: it chooses the
configured machine/repository profile, starts or reattaches the run through the
supported Git/CLI/AXI path, listens, and reports evidence back.

Configuration comes from the repository's trusted `.no-mistakes.yaml` plus the
selected no-mistakes global profile (`~/.no-mistakes/config.yaml` or another
`NM_HOME`). Prefer no-mistakes' native `agent`/fallback and `agent_config`
mechanisms over per-run config mutation.

## Merge authority

`/afk` controls whether an otherwise-ready Workset Merger may perform the final
merge without a fresh operator confirmation:

- **ON (default):** the merger may land when repository policy, exact-head
  evidence, and existing operator authority all permit it.
- **OFF:** the merger may prepare and validate the landing, but waits for operator
  confirmation before the final merge mutation.

The toggle changes merge authority only. It never authorizes branch-protection
bypass, destructive recovery, scope expansion, or decisions the operator has not
delegated.
