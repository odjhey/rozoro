# Rozoro: runtime, not orchestrator

Status: proposed product boundary
Date: 2026-08-24

## Decision

Rozoro should no longer define itself as an agent orchestrator or as a control tower that owns a fleet workflow.

The target product is a **durable local runtime and message bus for AI harness sessions**. Rozoro starts or attaches to a harness-level conversation, gives it a stable task/session address, observes runtime and lifecycle facts, transports data and control messages, persists events and mailbox state, and can resume the exact native conversation later.

Everything that requires understanding **what work should happen next** lives above Rozoro.

A useful one-line description is:

> Start, address, observe, message, and resume durable AI sessions across harnesses.

The architectural rule is:

> **One Rozoro session corresponds to one harness-level conversation/process. Anything recursively below that conversation belongs to the harness.**

## Why change the boundary

The original Rozoro pitch solved a real usability problem: one driver spawned, watched, messaged, and reaped several independent agent sessions so the operator did not have to babysit terminal tabs.

That boundary is becoming less defensible as harnesses add their own subagent trees, background agents, worktree isolation, routing, fan-out/fan-in, agent-team semantics, and session UIs. Reimplementing those features in Rozoro creates a permanent race with Claude, Pi, Codex, and other harness ecosystems.

Rozoro has a stronger cross-harness boundary that those features do not replace: a durable local address and lifecycle/message/event substrate that is independent of which harness is running the conversation and independent of which process is driving it.

This also makes non-agent producers first-class. A GitHub listener, CI job, cron job, shell script, desktop UI, or another agent can publish an event or message to a durable task address without becoming the workflow manager.

## Target architecture

```text
                         intelligence / workflow policy

       Claude native      Pi native       Codex native      optional clients
       subagents/teams     extensions      capabilities      watchtower, UI,
       workflows/etc.                                      scripts, automation
             |                |                |                  |
             +----------------+----------------+------------------+
                                      |
                               Rozoro protocol
                                      |
                         +------------v------------+
                         |        rozorod          |
                         |                         |
                         | task/session identity   |
                         | lifecycle projections   |
                         | durable event log       |
                         | mailbox / acknowledgement|
                         | DATA message delivery   |
                         | CONTROL actuation       |
                         | native resume linkage   |
                         +------------+------------+
                                      |
                                   Herdr
                                      |
                         terminals / processes / OS
```

Harness adapters translate native lifecycle/session capabilities into the Rozoro runtime model. They must not translate native workflow policy into a Rozoro workflow engine.

## What Rozoro core owns

Rozoro core may own only concepts that remain meaningful without understanding the task domain:

- durable task/session identity and addressing;
- starting, attaching, stopping, restarting, and resuming harness-level sessions;
- native session linkage required to resume the exact conversation;
- harness adapters and capability detection;
- process/liveness and harness-supported foreground/background lifecycle facts;
- durable event storage and projections;
- DATA-plane message delivery to a conversation;
- CONTROL-plane actuation such as interrupt, cancel, key, stop, and restart;
- mailbox/inbox ordering, attribution, delivery, acknowledgement, and supersession primitives;
- launch profiles that describe **how a harness process starts**, not what role it plays in a workflow;
- operator- and program-facing APIs/CLI/socket interfaces for the above.

The DATA/CONTROL distinction remains a core invariant:

```text
send      = tell the conversation something
control   = tell the runtime/process something
```

## What Rozoro core does not own

The following are explicitly outside core:

- task decomposition;
- planner/coder/reviewer/tester workflow graphs;
- deciding which agent should act next;
- fan-out/fan-in orchestration;
- nested agent trees;
- agent-team semantics;
- worktree strategy or branch policy;
- PR review or merge policy;
- test-gate policy;
- business priority;
- deciding whether an implementation is correct;
- deciding whether a task is accepted or complete;
- repository-specific instructions;
- role/persona taxonomies that imply workflow state.

The litmus test is:

> If a feature must understand what the agent is trying to accomplish, it probably lives above Rozoro. If it only needs to know where a session is, whether it is alive, what runtime event occurred, or how something can talk to it, it probably belongs in Rozoro.

## Where the removed features live

Removing orchestration from core does **not** mean deleting useful operating behavior. It relocates that behavior to the layer that can own it without coupling the runtime to one harness or one engineering workflow.

| Former / tempting Rozoro concern | New owner | Notes |
|---|---|---|
| Nested subagents and child-agent trees | **Harness-native orchestration** | Claude subagents/teams/workflows, Pi extensions, or equivalent native mechanisms. Rozoro sees the parent harness-level conversation, not its internal children. |
| Fan-out/fan-in inside one harness conversation | **Harness-native orchestration** | Use the harness capability when available instead of rebuilding a graph engine in Rozoro. |
| Child worktree creation/isolation | **Harness or repo tooling** | Worktrees are implementation/workflow policy, not session-runtime identity. |
| Task decomposition | **Driver/watchtower application or harness-native planner** | A client may decompose work and create multiple independent Rozoro sessions when separate lifecycle/context/accountability is actually useful. |
| Coder -> reviewer -> tester routing | **Optional watchtower application / skill** | Keep the proven operating model as a client of Rozoro, not as Rozoro state-machine semantics. |
| Cross-task prioritization | **Operator + optional watchtower application** | The operator owns business priority; a client can consume mailbox events and propose/execute routing policy. |
| Review/test/merge rules | **Target repository** | `AGENTS.md`, `CLAUDE.md`, skills, scripts, CI, and repository policy remain authoritative. |
| Crew personas/roles | **Prompt/skill or harness configuration** | If needed, they are application-level behavior. A core launch profile only describes process startup. |
| Acceptance / "done" judgment | **Operator or application layer** | Runtime `idle`/`turn-complete`/`stopped` are facts; accepted/correct/ready-to-merge are judgments. |
| GitHub/CI/background-job reactions | **External producer + Rozoro mailbox/message API** | The producer publishes to a durable task address. It does not need to impersonate or spawn a manager agent. |

### The optional watchtower still exists

The watchtower should survive as an **application of Rozoro**, not as the product definition.

It may be implemented as a prompt/skill/client that consumes stable Rozoro primitives and adds policy such as:

- decompose a checked plan into independent work;
- choose when separate sessions are useful;
- assign coder/reviewer/tester roles;
- triage mailbox items across many tasks;
- preserve operator priority;
- route reviewer/test feedback back to the relevant session;
- decide when evidence is sufficient to ask the operator for acceptance.

Conceptually:

```text
+------------------------+
| optional watchtower    |
|------------------------|
| decomposition          |
| priorities             |
| coder/review/test loop |
| completion judgment    |
+-----------+------------+
            |
       Rozoro protocol
            |
+-----------v------------+
| Rozoro core            |
|------------------------|
| sessions               |
| identities             |
| messages               |
| events                 |
| mailbox                |
| lifecycle              |
+------------------------+
```

A Claude driver, Pi driver, purpose-built client, or future desktop application can all implement the watchtower policy against the same core.

### Repository policy remains repository-local

Rules that only make sense for a particular checkout remain in that checkout. Examples include how to create or select worktrees, whether a PR may merge, which tests are required, branch conventions, release gates, and project-specific review standards.

Rozoro launches the conversation in the target `--cwd`; the harness and repository rules determine how the work is performed.

## Tasks become durable addresses/mailboxes

The durable Rozoro abstraction should be the **task/session address**, not a crew role.

For example, the durable address `pr-63` can receive independently produced information:

```text
GitHub review ----+
CI failure -------+----> pr-63 mailbox ----> attached/resumed harness session
human message ----+
another process --+
```

Producers should not need to know the Claude/Pi/Codex/Copilot native session identifier. Rozoro resolves the durable task address to the current native session linkage and preserves the history across stop/resume cycles.

The mailbox owns mechanical properties such as stable identity, ordering, attribution, delivery state, acknowledgement, and supersession. Rozoro must not infer business priority or correctness from those items.

This is the basis for supporting many simultaneous tasks without requiring one resident manager agent to receive every event at the same instant.

## Runtime facts versus application judgments

Core status should prefer mechanical facts:

```text
session:       alive
foreground:    idle
background:    none
input:         available
last_event:    turn.completed
```

Application-level reports may still be transported and persisted, but core should treat their payload as opaque data. For example, a client may publish:

```json
{
  "type": "report",
  "task": "pr-63",
  "payload": {
    "verdict": "needs-action",
    "summary": "reviewer found a blocker"
  }
}
```

Rozoro may store and deliver this report. It should not define `needs-action` as a universal workflow state or decide what should happen next.

## Target product surface

The eventual CLI should converge on boring runtime nouns and verbs:

```text
rozoro start
rozoro attach
rozoro list
rozoro status
rozoro send
rozoro control
rozoro stop
rozoro resume
rozoro events
rozoro inbox
rozoro ack
rozoro profile
rozoro doctor
```

Existing commands do not need to be renamed immediately. This is a product-boundary target, not a demand for a flag-day migration.

`crew` should eventually become `profile` where it means launch configuration. Terms such as `watchtower`, `planner`, `coder`, `reviewer`, and `tester` should not appear in core schemas or runtime state except as opaque user/application labels.

## Migration implications

This decision should drive a deliberate cleanup rather than an immediate destructive rewrite:

1. Preserve shipped runtime/event-bus/session-resume behavior that fits the new boundary.
2. Separate mailbox/event transport semantics from watchtower-specific policy.
3. Move watchtower prompt/directive material into an optional application/skill area.
4. Stop adding workflow semantics to core status, schemas, and CLI.
5. Prefer harness-native subagent/workflow features whenever work stays inside one harness-level conversation.
6. Create independent Rozoro sessions only when independent lifecycle, context, cross-harness execution, durable addressability, or accountability is useful.
7. Rename `crew` concepts opportunistically when they are only launch profiles; maintain compatibility rather than forcing a flag day.
8. Delete or demote core documentation that presents Rozoro itself as the intelligence/manager after equivalent userland guidance exists.

No shipped persistence or session data needs to be discarded merely because the conceptual boundary changes.

## Relationship to the existing watchtower documentation PR

PR #46 correctly separates workflow policy from lower-level lifecycle primitives in its proposed workflow-boundary ADR, but its broader product framing still centers one primary watchtower coordinating a large crew fleet.

This decision goes further: **the watchtower is optional userland policy, not a core Rozoro actor or scaling unit**. The durable event/mailbox/session substrate proposed there remains useful, while watchtower-specific priority, routing, and workflow semantics move above the core.

If PR #46 lands, its watchtower-centric ADRs and language should be reconciled against this decision rather than treated as permanent core architecture.

## Consequences

Benefits:

- Rozoro stops competing with rapidly improving harness-native orchestration.
- Claude, Pi, Codex, and future harnesses can use their strongest native delegation model without Rozoro modelling their internal trees.
- Cross-harness sessions still share one durable identity/event/message surface.
- Background jobs and external automation become first-class producers.
- The existing watchtower workflow remains possible without contaminating the runtime with one workflow design.
- The product becomes easier to test: core correctness is about identity, durability, ordering, delivery, lifecycle, and actuation rather than agent judgment.

Costs:

- Some current terminology and documentation becomes transitional.
- The optional watchtower/client layer needs an explicit home and interface.
- Harness-specific orchestration behavior will differ by harness instead of being normalized by Rozoro.
- Users who want an opinionated end-to-end multi-agent workflow will need a client/skill on top of core.

These costs are intentional. Rozoro should normalize the **runtime boundary**, not the intelligence above it.
