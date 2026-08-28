# Coordinate rozoro's architecture-boundary work

Status: historical — shipped and regression-tested (see docs/current-vs-target.md)

Created: 2026-08-22 00:03:56 Asia/Manila

Scope: issues #8, #9, #10, and #11

Delivery shape: four implementation plans delivered through five small PRs

## Purpose

This document coordinates four independently implementable plans. It owns only
the shared architecture, dependency order, merge strategy, and program-level
acceptance criteria. Each linked plan contains the evidence, file-level changes,
tests, compatibility details, risks, and exit gate needed for an agent to
implement that issue without reconstructing the full program.

## Implementation plans

1. [Build the Bats regression harness](../2026-08-22-000356-test-foundation/plan.md)
   for issue #11. Land the foundation first and close the issue only after the
   final coverage audit.
2. [Remove Git policy from teardown](../2026-08-22-000356-teardown-boundary/plan.md)
   for issue #8.
3. [Make status pure and turn-aware](../2026-08-22-000356-status-state-model/plan.md)
   for issue #9.
4. [Make conversation linking capability-aware](../2026-08-22-000356-session-linking/plan.md)
   for issue #10.

## Issue references

Restore the spawner boundary: remove Git/upstream policy from teardown

https://github.com/odjhey/rozoro/issues/8

Make handoff status pure, turn-aware, and explicit about runtime vs task state

https://github.com/odjhey/rozoro/issues/9

Make conversation linking capability-aware and prefer Herdr-reported session
identity

https://github.com/odjhey/rozoro/issues/10

Add a lightweight automated regression suite for protocol parsing and lifecycle
glue

https://github.com/odjhey/rozoro/issues/11

## Shared target architecture

```text
driver policy: acceptance, delivery, Git and PR judgment
                         |
rozoro: task identity, brief/handoff, runtime projection, resume capability
                         |
Herdr: pane, tab, agent process, runtime events, reported session identity
                         |
harness: Claude, Codex, Copilot, Pi, ...
```

All four plans preserve these shared invariants:

1. Herdr owns terminal, pane, tab, process, and runtime-event infrastructure.
2. Rozoro owns the durable task envelope and only the minimum projections needed
   to coordinate it.
3. Acceptance, Git delivery, PR state, testing adequacy, and merge authority are
   driver/crew/repository policy—not lifecycle state inferred by rozoro.
4. `brief.md` and append-only `handoff.md` remain the portable harness-neutral
   interface.
5. Runtime identity, task identity, and harness conversation identity remain
   separate namespaces.
6. Ordinary inspection commands do not mutate the facts they report.
7. Compatibility data is read defensively and removed only through a separately
   announced migration window.
8. Tests never touch a contributor's real Herdr server, harness data, home
   directory, or checkout.

This program does not add durable acceptance, workflow scheduling, retries,
DAGs, a database, task-owned worktrees, Git attribution, or generalized harness
management.

## Dependency and merge order

```text
#11 Bats foundation
    |
    +--> #8 teardown boundary ---------+
    |                                  |
    +--> #9 status/watch architecture -+--> #11 coverage closeout
    |                                  |
    +--> #10 session capabilities -----+
```

Recommended PR sequence:

1. `test: add isolated Bats protocol harness` references #11 without closing it.
2. `fix: remove Git policy from teardown` closes #8 after its tests pass.
3. `fix: separate runtime, task, and turn status` closes #9 after its tests pass.
4. `feat: make session linking capability-aware` closes #10 after its tests pass.
5. `test: complete lifecycle regression coverage` closes #11 after the audit.

The first PR is the only hard prerequisite. After it lands, #8 and #10 can be
implemented in parallel. #9 and #10 both touch `bin/rzr-lib.sh`, documentation,
the rozoro skill, and shared fixtures; give them separate branches, serialize
their merges, rebase the second, and run the full test matrix again.

## Shared rollout and verification

Every implementation PR must:

1. Run `./tests/run.sh`, which invokes a supported Bats installation, without a
   live Herdr or harness dependency.
2. Run shell and Python syntax checks through that same entry point.
3. Run `git diff --check` and compare help, README, templates, and skill text
   against actual CLI behavior.
4. Pass Linux and macOS CI with Bats-core v1.14.0, preserving the Bash 3.2
   compatibility promise.
5. Exercise JSON shapes and null handling with fixtures rather than matching
   only human-readable strings.

After the four behavior areas land, the #11 owner performs the final coverage
audit described in the test plan. A disposable manual Herdr 0.8.2 smoke pass is
useful for integration-shape confirmation, but it never replaces fixtures or
becomes a contributor requirement.

## Program-level acceptance criteria

The program is complete when:

- Teardown acts only on exact rozoro/Herdr lifecycle state and never invokes Git
  or claims to establish landed, merged, accepted, or discarded state.
- Repeated status reads are filesystem-pure, runtime and task state are named
  separately, and missing handoffs are derived only from observed turn edges.
- Earlier open items survive later done reports until explicit acknowledgement.
- Herdr-reported session identity is preferred, Claude's fallback is bounded,
  non-Claude starts never scan Claude data, and unsupported resume is explicit.
- Existing durable task folders, acknowledgement cursors, runtime status tokens,
  and Claude session descriptors follow their documented compatibility paths.
- `./tests/run.sh` passes on Linux and macOS without contacting real user state,
  and CI runs the same command with the pinned Bats version.
- README, watchtower template, and `.agents/skills/rozoro/SKILL.md` agree with the
  shipped boundaries and state semantics.

Each issue closes only when its own plan's acceptance criteria pass. The
coordination plan is complete when all four issue plans have landed and the
final #11 audit is green.
