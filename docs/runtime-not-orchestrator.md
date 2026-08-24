# Rozoro: preserve the workflow, test the substrate

Status: proposed product direction / implementation pause
Date: 2026-08-24

## Decision

Do **not** begin a `rozoro-core` extraction yet.

Preserve the current Rozoro experience that is already useful in day-to-day work, while treating the proposed lower-level runtime/message-bus boundary as a hypothesis to test rather than a new subsystem to build immediately.

Before extracting harness/session infrastructure from the current implementation, run a focused spike against:

- [Agent Client Protocol (ACP)](https://github.com/agentclientprotocol/agent-client-protocol), which already standardizes a substantial part of coding-agent session communication; and
- [acpx](https://github.com/openclaw/acpx), a headless client for stateful ACP sessions that already covers persistent session operation across coding agents.

The question is no longer "how should we build `rozoro-core`?". The question is:

> **What capability remains uniquely worth owning in Rozoro after ACP/acpx and harness-native orchestration are used as far as they can go?**

Until that question is answered with working evidence, current Rozoro remains the operational product.

## Preserve current Rozoro

This direction is deliberately compatibility-first. The existing workflow should continue to work while the alternative substrate is evaluated.

In particular, preserve:

- the current `./bin/rozoro` commands and operator workflow;
- Herdr-backed spawning and inspectable tabs/panes;
- task folders and durable task identity;
- exact native-session linkage and resume behavior;
- `rozorod`, its event store, projections, wake generations, and reconciliation path;
- DATA versus CONTROL separation;
- current handoff/report semantics used by the watchtower;
- the current watchtower workflow and its coder/reviewer/tester routing conventions;
- compatibility with existing `$ROZORO_HOME` state.

No migration should make the working setup less useful merely to achieve a cleaner architecture.

A useful rule for every exploratory or migration change is:

> **Can today's Rozoro workflow still run after this change?**

Until a deliberate breaking migration is approved, the answer must remain yes.

## Why the earlier `rozoro-core` proposal is paused

The previous version of this decision proposed extracting a harness-neutral local runtime that would own session identity, lifecycle, messaging, control, resume, and harness adapters.

That is directionally attractive, but the ecosystem now covers much of that surface already.

ACP provides a standard protocol boundary for coding-agent clients and agents. acpx provides a practical stateful/headless client around ACP sessions. Rebuilding our own Claude/Codex/Pi session protocol and adapter layer before proving gaps in those projects would create unnecessary ownership and maintenance cost.

Therefore:

- do **not** create a new harness abstraction simply because current Rozoro is coupled to Herdr;
- do **not** extract `ClaudeAdapter`, `CodexAdapter`, `PiAdapter`, etc. until the ACP path has been tested;
- do **not** introduce `HerdrHost` / `TmuxHost` as a new abstraction solely for architectural neatness;
- do **not** delete current Herdr integration while it remains the proven operational path.

The target architecture remains intentionally unresolved until the spike produces evidence.

## What still appears valuable

The product-boundary insight from the earlier proposal still stands: Rozoro should be suspicious of features that duplicate harness-native agent orchestration.

Harnesses increasingly own:

- nested subagents;
- agent teams/trees;
- fan-out/fan-in inside a harness conversation;
- worktree-aware child-agent execution;
- native session UIs and background agents;
- planning/delegation mechanics that are specific to that harness.

Rozoro should not race those ecosystems merely to offer another multi-agent framework.

What may remain valuable is a thinner layer above ACP/acpx that is specific to our operating problem:

- durable **task addresses** that are meaningful outside the native agent session;
- a mailbox/inbox for independently produced events and messages;
- attribution, ordering, acknowledgement, and supersession of those items;
- mapping a stable task address to whichever coding-agent session currently owns it;
- external producers such as GitHub, CI, cron/background jobs, scripts, or future UIs;
- compatibility with the existing watchtower experience while orchestration policy remains outside the substrate.

This is a hypothesis, not yet a commitment to build a new core.

## The likely boundary, if the spike validates it

The current working hypothesis is:

```text
                    workflow / judgment

       harness-native agents     optional watchtower
       teams / trees / planning  routing / prioritization
                  |                       |
                  +-----------+-----------+
                              |
                  stable task/mailbox layer
                       (possible Rozoro)
                              |
                         ACP / acpx
                              |
                   coding harness sessions
```

In this model ACP/acpx owns as much of the coding-session protocol and persistence problem as possible.

Rozoro would only own the application-level indirection that ACP sessions do not necessarily provide:

```text
GitHub review ----+
CI failure -------+----> task: pr-63 ----> current ACP session
human message ----+
background job ---+
```

External producers address `pr-63`; they do not need to know whether the current owner is Claude, Codex, Pi, or which native session identifier is active.

If ACP/acpx already provides this adequately, even this layer should be reduced further or contributed upstream rather than rebuilt locally.

## What does not belong in a future substrate

Whether the eventual substrate is ACP/acpx directly or a thin Rozoro layer around it, it should not own:

- task decomposition;
- planner/coder/reviewer/tester workflow graphs;
- deciding which agent should act next;
- nested agent trees;
- agent-team semantics;
- worktree strategy or branch policy;
- PR review or merge policy;
- test-gate policy;
- business priority;
- correctness judgment;
- acceptance judgment;
- repository-specific instructions.

Those belong to one of three higher layers:

1. **Harness-native orchestration** for child agents, trees, teams, and within-session delegation.
2. **Repository-local policy** for worktrees, branch/PR/test/merge rules, CI, and project instructions.
3. **Optional watchtower/client policy** for cross-session decomposition, routing, triage, and prioritization when that operating model is useful.

The current watchtower therefore remains useful. The architectural correction is only that it should eventually be a client of stable session/task primitives rather than defining universal runtime semantics.

## Relationship to no-mistakes

This direction also keeps a clean boundary with [no-mistakes](https://github.com/kunchenguid/no-mistakes).

- no-mistakes owns validation and delivery of a **code change**: review, test, docs, lint, fixes/escalation, push, PR, and CI gates.
- the possible Rozoro task/mailbox layer owns continuity and communication around a **live task/session**.
- ACP/acpx owns as much as practical of the coding-agent session protocol and persistence underneath.

A possible composition is:

```text
optional orchestration / watchtower
              |
     Rozoro task/mailbox ?
              |
          ACP / acpx
              |
      coding harness session
              |
         no-mistakes
     when a change is ready
```

The layers are not required to be strictly nested at runtime; the diagram expresses responsibility.

## ACP/acpx spike

The next architectural work should be a small, disposable spike rather than a refactor of current Rozoro.

### Goal

Determine what ACP/acpx already replaces and identify only the missing capabilities that matter to the current Rozoro experience.

### Minimum experiment

Run equivalent operations against Claude, Codex, and Pi where practical:

1. create three independently addressable sessions;
2. send initial work to each;
3. observe structured session/turn state without scraping terminal output;
4. send a follow-up to an existing session;
5. terminate the launching shell/helper where supported;
6. reconnect and continue the same native conversation;
7. cancel/interrupt a running turn where supported;
8. consume machine-readable lifecycle/session events;
9. determine what state survives process restart;
10. determine whether named application tasks can be cleanly mapped to ACP/acpx sessions.

### Task/mailbox proof

Then test the part that may remain uniquely useful:

```text
external producer
      |
      v
 durable task address: pr-63
      |
      v
 whichever ACP session owns pr-63
```

At minimum prove:

- a stable task ID independent of the ACP/native session ID;
- durable delivery of an externally generated message/event;
- exact attribution to the intended task when many tasks are active;
- reconnect/resume without external producers changing their address;
- acknowledgement that is independent of session transport acknowledgement.

### Decision output

The spike should end with a capability matrix:

| Capability | Current Rozoro | ACP | acpx | Thin Rozoro layer needed? |
|---|---:|---:|---:|---:|
| create session | | | | |
| named/persistent session | | | | |
| prompt/follow-up | | | | |
| structured lifecycle | | | | |
| cancel/control | | | | |
| exact resume | | | | |
| multi-harness support | | | | |
| stable application task address | | | | |
| external producer mailbox | | | | |
| attribution/ordering/ack | | | | |
| current watchtower compatibility | | | | |

Only capabilities in the final column should become candidates for new Rozoro substrate work.

## Herdr and tmux are also deferred

The previous discussion suggested separating hosting from harness semantics with Herdr/tmux/local host adapters.

That remains plausible, but it is **not yet justified**.

If ACP/acpx can operate sessions headlessly and provide the structured lifecycle/control path we need, Herdr or tmux may be primarily an inspectability/terminal UX choice rather than part of runtime correctness.

Therefore:

- Herdr remains the current default and supported operational path;
- no Herdr removal is proposed;
- no tmux adapter should be built until the ACP/acpx spike identifies a concrete hosting gap;
- if a host abstraction is later needed, extract it from proven requirements rather than inventing it in advance.

## Current product versus exploration

### Current product

Current Rozoro remains a **highly opinionated way to deliver tasks to multiple coding harness sessions** through Herdr, with durable local state and a watchtower-oriented operating model.

That is the thing we can use today.

### Exploration

The project is evaluating whether its longer-term durable substrate should become much thinner by delegating session protocol/persistence to ACP/acpx and retaining only task/mailbox behavior that is demonstrably missing.

The exploration must not be presented as shipped architecture.

## Relationship to PR #46

PR #46 documents the richer watchtower/mailbox product model and correctly separates repository workflow policy from lower-level lifecycle primitives.

This decision does not require throwing that operational model away. Instead:

- preserve the watchtower workflow as the current opinionated product experience;
- preserve the durable event/mailbox lessons from #46;
- avoid hardening watchtower-specific semantics into a newly extracted core before ACP/acpx is evaluated;
- reconcile #46 later against whatever the spike proves.

## Consequences

### Benefits

- Current Rozoro remains usable at work while architecture is explored.
- We avoid duplicating ACP/acpx without evidence that duplication is necessary.
- We avoid premature Herdr/tmux/harness adapter abstractions.
- Harness-native orchestration can improve independently of Rozoro.
- The likely unique value—stable task addressing, external event delivery, mailbox semantics, and cross-session continuity—can be tested directly.
- A failed hypothesis is cheap: if ACP/acpx solves almost everything, Rozoro can shrink rather than defend unnecessary infrastructure.

### Costs

- The internal architecture remains transitional for longer.
- Current Herdr coupling remains in place during the spike.
- Some recent architectural ideas are deliberately left unresolved.
- We need experimental evidence before committing to a cleaner decomposition.

These costs are preferable to extracting and maintaining a new `rozoro-core` that existing ecosystem components may already provide.

## Decision rule

Do not build substrate because it feels architecturally clean.

First prove that current Rozoro needs a capability that ACP, acpx, harness-native orchestration, repository-local tooling, and no-mistakes do not already provide well enough.

Then build only that gap.