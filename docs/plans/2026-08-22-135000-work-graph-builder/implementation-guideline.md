# Work Graph Implementation Guideline

This is a practical implementation roadmap for the work-graph layer proposed in PR #32. It is intentionally not a detailed technical specification. The goal is to give implementors a clear sequence, ownership boundary, and set of invariants so the work does not drift into either a general workflow engine or a replacement for harness-native subagents.

## 1. Start with the boundary

Before implementing anything, keep this model fixed:

```text
watchtower
    |
    v
work graph
    |
    v
rozoro crews
    |
    v
harness-native subagents
```

The responsibilities are:

- **Watchtower** decides what durable responsibilities should exist and applies judgment where deterministic routing is insufficient.
- **Work graph** coordinates dependencies and progression between crew-sized responsibilities.
- **Rozoro** starts, senses, messages, resumes, and reaps durable crew sessions.
- **Crew** owns how its task is solved.
- **Subagents** are internal tools of a crew and remain invisible to Rozoro and the graph.

A graph node should normally correspond to a responsibility worth tracking independently.

Examples:

- one stacked PR slice;
- one separate worktree;
- one backend or frontend implementation stream;
- one cross-repository change;
- an intentionally independent review crew;
- an integration step dependent on several completed crews.

Do not create graph nodes merely for local code review, testing, exploration, or parallel research when a crew can use its own subagents for those tasks.

## 2. Target user experience

The graph runtime should mostly disappear behind the watchtower.

A user should be able to describe the durable work shape in ordinary terms:

```text
"Implement #424 as three stacked PRs. Backend and frontend can run in parallel,
then have an integration slice depend on both."
```

The watchtower should translate that into a crew-level graph:

```text
backend ─────┐
             ├── integration ── cleanup
frontend ────┘
```

The user should not need to specify reviewer/tester/scout agents. Those remain internal decisions of each crew and its harness.

The watchtower can acknowledge the run with a compact view:

```text
run: issue-424
4 crew responsibilities

● backend
● frontend
○ integration   waiting on backend + frontend
○ cleanup       waiting on integration
```

The normal interactive surface should then be simple status/show commands or equivalent watchtower requests:

```text
show graph
status issue-424
```

Example status:

```text
issue-424    RUNNING

✓ backend       PR #431   ready
● frontend      working
○ integration   waiting: frontend
○ cleanup       waiting: integration
```

Deterministic graph progression should happen without waking the watchtower. When `frontend` finishes, `integration` should become runnable automatically.

A crew's internal subagents must not appear as graph nodes:

```text
frontend crew
  ├─ scout subagent
  ├─ reviewer subagent
  └─ test subagent
```

The graph still reports only:

```text
● frontend
```

For stacked PRs, outputs such as branch, PR number, and head SHA should flow automatically into downstream crew tasks. Users should not manually shuttle those values between crews.

Intentional cross-crew feedback is different. If the watchtower explicitly creates an independent review boundary:

```text
implement ──> independent review
    ^               |
    |---- changes --|
```

then the graph may automatically resume the same implementation crew with the review findings. If the loop hits its configured limit, the watchtower should be brought back in with a concise explanation and current artifact identity.

The primary UX principle is:

> The user speaks in outcomes and durable work boundaries. The watchtower turns that into a graph of crews. The graph advances deterministic dependencies automatically. Each crew remains autonomous internally. The watchtower/user is interrupted only when judgment is actually required.

A low-level CLI should still exist for inspectability, debugging, recovery, and automation:

```text
rozoro graph run <graph>
rozoro graph status <run>
rozoro graph show <run>
rozoro graph reconcile <run>
```

But this should not be the primary interaction model for normal watchtower use.

## 3. Implementation order

Implement the system in layers. Each layer should remain usable and testable before moving to the next.

```text
Groundwork
    ↓
Graph IR
    ↓
Offline reconciler
    ↓
Durable run state
    ↓
Rozoro dispatch
    ↓
Sequence / fan-out / joins
    ↓
Resume / bounded cycles
    ↓
Stacked PR workflows
    ↓
Reusable playbooks
```

Avoid implementing the full graph runtime in one large PR.

## 4. Groundwork: stabilize Rozoro automation contracts

These should preferably land independently of the graph runtime.

### 4.1 Idempotent crew start

The graph reconciler must be safe to retry after crashes.

Add a generic caller-supplied request/correlation identifier to `rozoro start`.

Conceptually:

```text
rozoro start ... --request-id <opaque-id>
```

The important behavior is:

```text
same request-id
        |
        +--> always resolves to the same logical Rozoro task
```

A crash between:

```text
graph decides to start crew
        ↓
Rozoro starts crew
        ↓
graph persists returned task id
```

must not cause a second crew to be created when reconciliation runs again.

Exit criteria:

- repeated calls with the same request id do not create duplicates;
- concurrent identical calls are safe;
- conflicting reuse fails rather than silently reusing the task;
- normal interactive starts without a request id remain unchanged.

### 4.2 Dynamic task sensing

The graph will create crews after the run has already started.

The monitoring layer therefore needs to notice newly created tasks without requiring the watchtower to repeatedly rebuild a static watch list.

The graph runtime should consume the generic Rozoro monitor rather than creating another Herdr subscriber.

Exit criteria:

```text
start watching
    ↓
crew A appears
    ↓
crew A completes
    ↓
crew B is created later
    ↓
crew B completes
```

without restarting or manually reconfiguring the monitor.

### 4.3 Stable machine-readable CLI results

Automation should not parse human-oriented terminal messages.

Prefer stable JSON output for operations such as:

```text
rozoro start
rozoro send
rozoro resume
rozoro status
```

The exact schema can evolve initially, but it should expose at least:

- task key;
- operation result;
- session/link state where relevant;
- cwd;
- meaningful failure information.

Do not make this graph-specific.

## 5. Build the graph model before connecting agents

The first graph implementation should work completely offline.

Use fixtures and synthetic events rather than real crews.

### 5.1 Define a small canonical IR

YAML can be the authoring format, but the runtime should consume a canonical representation.

Start with only:

```text
graph
run
node
edge
exit
output
attempt
join
watchtower gate
```

A normal node means:

> start or resume one Rozoro crew responsibility.

Do not add a `subagent` node type.

Do not add arbitrary scripting or expression evaluation.

### 5.2 Keep the initial schema boring

A rough authoring form is enough:

```yaml
nodes:
  backend:
    task: deliver backend change
    exits: [ready]
    outputs: [branch, pr, head_sha]

  frontend:
    task: deliver frontend change
    exits: [ready]
    outputs: [branch, pr, head_sha]

  integration:
    task: integrate backend and frontend
    exits: [ready]

joins:
  inputs-ready:
    all:
      - backend.ready
      - frontend.ready
    to: integration
```

The canonical runtime representation can be JSON or equivalent.

The important part is deterministic semantics, not authoring syntax.

### 5.3 Validate aggressively

Reject invalid graphs before execution.

Validate:

- duplicate node ids;
- missing referenced nodes;
- undeclared exits;
- invalid joins;
- cycles without bounded attempts;
- impossible output references;
- invalid `fresh` / `resume` transitions;
- unreachable terminal states where practical.

Prefer failing early over trying to interpret ambiguous graphs at runtime.

## 6. Build a pure reconciler

Before spawning real crews, implement the central function conceptually as:

```text
reconcile(graph, state, observed_results)
        ↓
deterministic decisions
```

Given the same inputs, it must produce the same result.

For example:

```text
backend = ready
frontend = working
integration = pending
```

should deterministically produce:

```text
nothing new is runnable
```

Later:

```text
backend = ready
frontend = ready
```

produces:

```text
integration becomes runnable
```

There should be no LLM inside this layer.

## 7. Persist execution as an event journal

Once the state machine works offline, add durable runs.

Suggested shape:

```text
$ROZORO_HOME/graphs/<run-id>/
    graph.json
    events.jsonl
    state.json
```

Where:

- `graph.json` is immutable for that run;
- `events.jsonl` is append-only execution history;
- `state.json` is the current materialized view.

Typical events:

```text
run.created
node.ready
node.dispatch-intended
node.started
node.completed
node.reentered
node.blocked
run.needs-attention
run.completed
```

Persist decisions before performing external side effects whenever possible.

The runtime should be restartable simply by reading disk and reconciling again.

## 8. Connect the reconciler to Rozoro

Only after the graph semantics and durable state are proven should the implementation start real crews.

Each node attempt should derive a stable dispatch identifier, for example:

```text
<run-id>/<node-id>/<attempt>
```

Then the flow becomes:

```text
node becomes runnable
        ↓
persist dispatch intent
        ↓
rozoro start --request-id ...
        ↓
persist resulting task key
        ↓
observe crew
```

If the process dies anywhere in that sequence, rerunning reconciliation must not duplicate the logical crew.

This is one of the most important correctness requirements in the whole project.

## 9. Define the graph result contract

The graph needs machine-readable outcomes beyond the human `handoff.md`.

Keep these concepts separate:

```text
handoff verdict
    =
what happened to the crew/task?

graph exit
    =
which edge should become eligible?
```

A graph-managed task may emit something like:

```json
{
  "schema": 1,
  "node": "backend",
  "attempt": 1,
  "exit": "ready",
  "outputs": {
    "branch": "feature/backend",
    "pr": 123,
    "head_sha": "abc123"
  }
}
```

The graph runtime validates this before using it.

Invalid results should stop for watchtower attention rather than guessing.

## 10. Implement the acyclic useful subset first

The first live graph version should support the workflows that clearly justify cross-crew orchestration.

### 10.1 Sequence

```text
schema
  ↓
backend
  ↓
frontend
```

Useful for stacked work or ordered repository changes.

### 10.2 Parallel fan-out

```text
        ┌─ backend
start ──┤
        └─ frontend
```

Both crews can progress independently.

### 10.3 Join

```text
backend ──┐
          ├── integration
frontend ─┘
```

Support `all` first.

`any` can also be included if it stays simple.

Avoid quorum and richer boolean expressions until a real workflow requires them.

Phase exit criteria:

- either parallel branch can finish first;
- graph process restart is safe;
- monitor restart is safe;
- repeated reconciliation is safe;
- malformed node results fail closed;
- downstream task dispatch retries do not duplicate work.

## 11. Add `resume` only after basic graphs are stable

Once sequence/fan-out/join work reliably, add context-preserving transitions.

Example:

```text
implementation crew
        ↓
independent reviewer
        ↓ changes
implementation crew resumed
```

The scheduler must never infer whether a new session or old context is appropriate.

The graph definition should say:

```text
fresh
```

or:

```text
resume
```

explicitly.

For a live crew, this may map to `send`.

For a reaped crew, it may map to `resume`.

That implementation detail belongs in the graph-to-Rozoro adapter.

## 12. Add cycles conservatively

Cycles are useful, but they are where accidental autonomous loops appear.

Require every cycle to have a finite bound.

For example:

```text
implementation
      ↓
independent review
      ↓ changes
implementation
```

with:

```text
max attempts: 3
```

After the limit:

```text
watchtower attention
```

Do not make ordinary crew-internal review/test iterations into graph cycles.

Those remain inside the crew.

## 13. Make artifact identity explicit

Any cross-crew validation or stacked dependency should identify the artifact it evaluated.

For PR-oriented work, record values such as:

```text
branch
PR
head SHA
```

This prevents:

```text
review approves commit A
implementation changes to commit B
graph still considers old approval valid
```

If an upstream artifact changes, dependent approvals/results tied to the old artifact must be invalidated.

## 14. Implement stacked PRs as the first higher-level workflow

Stacked PRs are a strong graph use case because each slice has durable identity and dependency.

Example:

```text
foundation
    ↓
backend
    ↓
frontend
    ↓
cleanup
```

Each node should normally mean:

> one crew owns and delivers this PR slice in review-ready state.

Inside that crew:

```text
scout subagent
review subagent
test subagent
```

may or may not exist. The graph does not care.

The graph only needs outputs such as:

```text
branch
PR
head SHA
```

so the next slice can build on the right base.

## 15. Delay reusable playbooks

Do not design a playbook framework before at least two or three real graph definitions repeat the same topology.

Good eventual candidates might be:

```text
stacked-prs
parallel-work-then-integrate
independent-review-gate
```

Avoid creating playbooks such as:

```text
reviewed-pr
review-fix-loop
fanout-review-test
```

unless there is a genuine cross-crew reason for those boundaries.

Ordinary review/test delegation belongs to the harness.

## 16. Watchtower integration

The watchtower should not be involved in deterministic transitions.

For example:

```text
backend.ready + frontend.ready
        ↓
integration
```

should happen without asking the watchtower.

Wake or pause for the watchtower when:

- a crew reports `needs-action`;
- a crew is blocked;
- an unexpected/invalid graph result appears;
- a bounded loop is exhausted;
- an explicit judgment gate is reached;
- the graph completes;
- policy requires a human/LLM decision.

The watchtower remains the judgment layer, not the scheduler loop.

## 17. Suggested PR breakdown

Implementation should preferably land as a sequence of independently understandable changes.

A reasonable breakdown is:

```text
PR A
caller-idempotent Rozoro start

PR B
dynamic monitor / task discovery

PR C
stable JSON lifecycle outputs

PR D
graph schema + validator

PR E
offline deterministic reconciler

PR F
durable run journal + materialized state

PR G
Rozoro dispatch integration

PR H
graph-result contract + sequence/fan-out/join

PR I
fresh/resume + bounded cycles

PR J
stacked PR workflow

PR K
playbooks, only if real usage justifies them
```

Some groundwork PRs can run in parallel.

Avoid combining the runtime, monitoring changes, graph model, UI, and stacked workflows into one implementation branch.

## 18. Testing priorities

Favor failure-mode tests over only happy-path examples.

At minimum cover:

- same node reconciled repeatedly;
- same dispatch attempted concurrently;
- crash before Rozoro start;
- crash after Rozoro start but before graph state update;
- crash after result observation but before transition persistence;
- malformed `graph-result.json`;
- undeclared exit;
- missing output;
- parallel branches finishing in different orders;
- monitor disconnect/restart;
- graph runner restart;
- live crew resume;
- reaped crew resume;
- loop success;
- loop exhaustion;
- stale artifact approval;
- stacked PR base/head propagation.

For every important crash boundary, ask:

> If the process dies here and reconciliation runs again, what happens?

The expected answer should usually be:

> The same logical state is recovered and no duplicate durable work is created.

## 19. Things implementors should actively avoid

Do not let the implementation drift toward:

- a replacement for Claude/Codex/Pi subagents;
- graph nodes for every reviewer, tester, or scout;
- an embedded LLM scheduler;
- arbitrary executable graph conditions;
- a generic Airflow/Temporal clone;
- dynamic graph mutation before static workflows are proven;
- rich UI before runtime semantics stabilize;
- graph concepts leaking into Rozoro's core task/session primitives;
- repo-specific PR/testing policy inside Rozoro itself.

A useful smell test is:

> Could this logic stay entirely above Rozoro without changing `start/status/send/resume` semantics?

If yes, keep it above Rozoro.

## 20. V1 definition of done

V1 does not need to solve every orchestration problem.

It is sufficient if the system can reliably do something like:

```text
backend crew ----\
                  -> integration crew -> finished
frontend crew ---/
```

and:

```text
PR1 crew
   ↓
PR2 crew
   ↓
PR3 crew
```

while guaranteeing:

- durable crash recovery;
- no duplicate crews from reconciler retries;
- explicit dependencies;
- stable outputs;
- optional explicit resume;
- bounded cross-crew feedback loops;
- clear watchtower escalation;
- no awareness of crew-internal subagents.

If those properties hold, the architecture is strong enough to grow from real usage rather than speculation.
