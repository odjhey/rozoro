# Work graph builder plan

Date: 2026-08-22

Repository baseline: `master` at `4bbcf7e`

Scope: planning artifact only. This plan does not add graph execution code or change Rozoro's existing spawn/watch/message/reap contract.

## Recommendation

Build a **work-graph layer above Rozoro**, not inside Rozoro's task/session primitives.

Rozoro should remain the deliberately small session substrate: start a crew, sense it, send DATA, execute CONTROL, resume it, and reap it. The new layer owns durable topology between **crew-sized responsibilities**: which crew may run, which durable result enables another crew, when independent crews must join, and when a bounded cross-crew loop or policy decision must return control to the watchtower.

Use **work graph** rather than DAG as the core term. Straight-line and fan-out/fan-in workflows are DAGs, while intentionally independent cross-crew review/fix/re-review or other feedback relationships may be cyclic.

The intended layering is:

```text
user
  |
  v
watchtower                    judgment, planning, policy
  |
  v
work-graph runtime            deterministic crew topology + reconciliation
  |
  v
rozoro                        spawn/watch/message/reap transport
  |
  +--> crew A --------------------> harness-native subagents
  +--> crew B --------------------> harness-native subagents
  +--> crew C --------------------> harness-native subagents
```

The watchtower decides *what crew-sized responsibilities should exist and how they relate*. The graph runtime deterministically decides *which declared transition is enabled next*. Crew agents do domain work and remain free to use their harness-native subagents. Rozoro remains unaware of PRs, testing policy, graph edges, joins, merge authority, and subagent topology.

## The boundary: graphs coordinate crews, not subagents

This is the central design constraint.

Rozoro already distinguishes:

- **crew** — a Rozoro-spawned durable harness session, visible to the watchtower;
- **subagent** — a harness-native helper spawned inside a crew session and invisible to Rozoro.

The work graph must preserve that distinction rather than flattening both into generic workers.

A normal graph node represents **one independently orchestrated crew responsibility**, not an arbitrary agent invocation and not every internal step the crew might take.

A crew may use zero, one, or many native subagents for:

- code exploration;
- review of its own work;
- test execution or failure diagnosis;
- research or alternative approaches;
- bounded specialist analysis;
- any other task-local delegation supported by its harness.

The graph neither prescribes nor observes that internal topology.

Before creating another graph node, ask:

> Why can this responsibility not remain inside the existing crew?

Good reasons for a separate graph node include:

- it owns a separate branch, worktree, PR, or repository;
- it must remain independently recoverable/resumable;
- it is intentionally isolated from another crew's context;
- it must use a different harness/model/posture by policy;
- it can make durable progress independently and later join another crew's result;
- another durable deliverable must exist before it can start;
- it represents an explicit watchtower/human decision boundary.

**Parallelism alone is not sufficient.** Harness-native subagents already provide task-local parallelism.

This gives the ownership model:

```text
watchtower
  owns: what responsibilities exist, policy, acceptance judgment

work graph
  owns: durable dependencies and progression between crew responsibilities

crew
  owns: how to accomplish its responsibility, including internal subagent use

subagent
  owns: the bounded work delegated by its parent crew
```

## Why a graph layer still fits the current architecture

Rozoro already has most of the substrate a higher-level reconciler needs:

- durable unique task identities and task folders;
- append-only `handoff.md` history;
- lifecycle verdicts (`done`, `needs-action`, `failed`, `blocked`);
- explicit DATA vs CONTROL planes;
- exact session resume for supported harnesses;
- watcher status and a durable watchtower wake/reconciliation ledger;
- crash-safe state stored outside the process.

The missing abstraction is not another agent manager and not a replacement for harness-native subagents. It is a small durable state machine that compiles **crew nodes** into ordinary Rozoro tasks and advances dependencies between those tasks.

The graph is most valuable for horizontal coordination such as:

```text
schema PR -> backend PR -> frontend PR
```

or:

```text
backend crew ----\
                  -> integration crew
frontend crew ---/
```

or an intentionally isolated feedback loop:

```text
implementation crew -> independent review crew
        ^                       |
        |------ changes --------|
```

## Vocabulary

Keep the common language deliberately small:

- **graph** — one workflow definition coordinating crew-sized responsibilities.
- **run** — one durable execution of a graph.
- **node** — one independently orchestrated crew responsibility, except explicit watchtower/gate nodes.
- **edge** — a declared transition from one node exit to another node.
- **exit** — the workflow outcome selected by a successfully completed node.
- **output** — structured data exported by a node for downstream nodes.
- **attempt** — one execution/re-entry of a node.
- **join** — a condition waiting for `all` or `any` upstream exits in V1.
- **subgraph/playbook** — a reusable graph definition once repeated crew topology proves the need.

Avoid introducing separate names for sequence, fan-out, retry, and loop primitives when they can be expressed using nodes, edges, joins, and bounded attempts.

Do not introduce a graph concept for harness-native subagents. They remain an implementation detail of their parent crew.

## Separate task lifecycle from workflow outcome

Do not overload Rozoro's handoff `verdict` with graph semantics.

`verdict` answers:

> Did this crew successfully finish this turn/task, or does it need attention?

A graph **exit** answers:

> Which declared workflow path should run next?

For example, an independently isolated review crew can successfully complete with either result:

```text
verdict: done
exit: approved
```

```text
verdict: done
exit: changes
```

`changes` is not a failed agent execution. It is a valid crew result that can route back to the implementation crew.

This is a cross-crew example, not a requirement that ordinary code review be modeled as another graph node. A normal implementation crew may instead use native review/test subagents internally and expose only a final `ready` result to the graph.

## Node result contract

Preserve `handoff.md` as the human-readable append-only conversation record. Add an optional graph-owned sibling result for machine routing:

```text
tasks/<task-key>/
  brief.md
  handoff.md
  session.json
  graph-result.json
```

Example for a backend PR crew:

```json
{
  "schema": 1,
  "node": "backend",
  "attempt": 1,
  "exit": "ready",
  "outputs": {
    "branch": "stack/backend",
    "pr": 412,
    "head_sha": "abc123"
  }
}
```

The graph layer appends a small completion contract to the node task: choose exactly one declared exit and emit the declared outputs. Rozoro still receives and delivers a normal task body verbatim; it does not parse or validate graph exits.

The graph runtime must validate `graph-result.json` against the node declaration before enabling an edge. Missing files, undeclared exits, malformed JSON, or missing required outputs become a graph-level exception requiring watchtower attention; they must never silently choose a transition.

## Minimal authoring model

YAML is a convenient authoring form, not the runtime truth. Compile it to a small canonical JSON IR so future watchtower generation, a TUI/GUI, or other builders do not couple the runtime to YAML syntax.

The introductory example should demonstrate a responsibility boundary that harness subagents do not replace:

```yaml
version: 1
name: parallel-app-change

nodes:
  backend:
    cwd: /repo/backend-worktree
    task: deliver the backend portion as a review-ready PR
    exits: [ready]
    outputs: [branch, pr, head_sha]

  frontend:
    cwd: /repo/frontend-worktree
    task: deliver the frontend portion as a review-ready PR
    exits: [ready]
    outputs: [branch, pr, head_sha]

  integrate:
    cwd: /repo/integration-worktree
    task: |
      integrate the completed backend and frontend deliverables
      backend: {{ backend.outputs.pr }}
      frontend: {{ frontend.outputs.pr }}
    exits: [ready]
    outputs: [branch, pr, head_sha]

edges:
  - from: backend.ready
    to: integrate

  - from: frontend.ready
    to: integrate

joins:
  integration-inputs:
    all: [backend.ready, frontend.ready]
    to: integrate
```

Each crew is still free to spawn reviewer/tester/scout subagents internally before declaring its PR `ready`.

The first implementation should support only:

1. crew nodes;
2. edges;
3. joins (`all` and `any` initially);
4. `fresh` vs `resume` transition mode;
5. bounded re-entry with `max` attempts;
6. declared outputs by name;
7. terminal success/failure/watchtower-attention state;
8. explicit watchtower/gate nodes if needed for judgment.

Do not add arbitrary expressions, embedded scripts, dynamic graph mutation, token budgets, cron scheduling, a subagent abstraction, or a general plugin system in V1.

## Fresh vs resume is first-class

Agent context is part of orchestration semantics, but only at the crew/session boundary visible to Rozoro.

A legitimate cyclic example is an intentionally independent review crew:

```yaml
- from: independent-review.changes
  to: implement
  mode: resume
  max: 3
```

The implementation crew resumes with its existing context. Re-review may deliberately choose either:

- `resume` — retain the independent review crew's history and verify the fixes in context; or
- `fresh` — start a new isolated review crew to reduce anchoring.

Do not create this topology merely to get ordinary review parallelism. If review is part of one crew's normal delivery responsibility, let that crew use harness-native subagents instead.

Keep these identities separate in persisted state:

- graph node identity;
- node attempt identity;
- Rozoro task key;
- harness/session identity.

A node may have several attempts and, depending on edge mode, one or several Rozoro tasks/sessions.

## Stacked PRs

A stacked PR sequence is a natural graph-level dependency because each slice owns a durable branch/PR and provides the base for the next slice:

```text
foundation -> api -> ui -> cleanup
```

Each node normally represents **one crew responsible for delivering its slice in a review-ready state**. That crew may internally use its harness's review/test/scout subagents; those do not become graph nodes.

Each slice exports at least the branch/PR/head commit required by the next node. A downstream node can be instructed to base itself on the previous node's branch.

Illustratively:

```yaml
nodes:
  foundation:
    task: deliver the foundation slice as a review-ready PR
    exits: [ready]
    outputs: [branch, pr, head_sha]

  api:
    task: |
      deliver the API slice as a review-ready PR
      base it on {{ foundation.outputs.branch }}
    exits: [ready]
    outputs: [branch, pr, head_sha]

  ui:
    task: |
      deliver the UI slice as a review-ready PR
      base it on {{ api.outputs.branch }}
    exits: [ready]
    outputs: [branch, pr, head_sha]
```

Once repeated real workflows justify reusable subgraphs, `stacked-prs` is a plausible playbook. Do not assume each slice expands into a `reviewed-pr` subgraph; review/test delegation remains local to the slice crew unless independence is explicitly required.

Do not implement dynamic `foreach` graph expansion in V1. The watchtower can construct a static graph containing N slices after it has planned the work. Dynamic fan-out can be added later if real use demonstrates the need.

## Durable execution model

Follow Rozoro's existing crash-safe philosophy: **reconciler, not in-memory orchestrator**.

Persist each run outside the repository, for example:

```text
$ROZORO_HOME/graphs/<run-id>/
  graph.json
  state.json
  events.jsonl
```

`graph.json` is the immutable canonical graph IR for the run.

`events.jsonl` is the append-only execution journal, for example:

```jsonl
{"seq":1,"event":"run.created"}
{"seq":2,"event":"node.ready","node":"backend","attempt":1}
{"seq":3,"event":"node.ready","node":"frontend","attempt":1}
{"seq":4,"event":"node.started","node":"backend","attempt":1,"task":"backend--01..."}
{"seq":5,"event":"node.started","node":"frontend","attempt":1,"task":"frontend--01..."}
{"seq":6,"event":"node.completed","node":"backend","attempt":1,"exit":"ready"}
```

`state.json` is a materialized current view derived from/consistent with the event log. Writes must be atomic. Reconciliation must be safe to run repeatedly after interruption.

The runtime loop is conceptually:

```text
read graph + durable run state
        |
read relevant Rozoro task status/results
        |
validate newly completed node results
        |
compute enabled transitions
        |
persist decisions before side effects
        |
start/send/resume Rozoro crews
```

The graph runner itself does not need an LLM.

## Watchtower attention nodes

Some transitions need judgment rather than deterministic routing. Represent that explicitly instead of hiding LLM decisions inside edge evaluation.

Example:

```yaml
decide:
  type: watchtower
  needs: [option-a, option-b]
  exits: [approach-a, approach-b, abandon]
```

A watchtower node does not spawn another crew. It marks the run as requiring the resident watchtower to inspect accumulated crew outputs and select one of the declared exits.

Wake the watchtower for:

- `needs-action` / `blocked` / unrecoverable crew failure;
- invalid or missing graph result;
- loop-attempt exhaustion;
- explicit `type: watchtower` nodes;
- graph completion;
- other policy decisions intentionally not encoded in the graph.

Do **not** wake the watchtower merely to interpret deterministic edges such as `backend.ready -> integration`.

## Bounded loops

Every cyclic edge must have a finite attempt policy in V1.

Example for intentionally independent review:

```yaml
- from: independent-review.changes
  to: implement
  mode: resume
  max: 3
  exhausted: watchtower
```

This prevents an autonomous cross-crew loop from becoming an unbounded compute/cost loop. V1 only needs attempt count. Wall-time/token/cost budgets can be evaluated later.

Again, a crew's own internal subagent review/test iterations are outside graph semantics and remain the harness/crew's responsibility.

# Groundwork before graph execution

The work below is intentionally separated from the graph runtime so it can be reviewed and queued independently.

## Groundwork G1 — retry-safe/idempotent child start (hard blocker)

**Problem:** current `rzr-start` allocates a fresh random durable task key for every invocation. That is correct for interactive starts, but a durable graph reconciler can crash after the crew was spawned and before the returned task key was persisted in graph state. Re-running reconciliation would start a duplicate crew for the same node attempt.

**Required generic capability:** add a caller-supplied correlation/idempotency key to the blessed start path, without making Rozoro understand graphs.

Possible contract:

```text
rozoro start <display> --request-id <opaque-caller-key> ...
```

Semantics:

- first use atomically binds `<request-id>` to exactly one durable task key and proceeds with normal start;
- repeated identical use returns/reattaches to that same task rather than creating another;
- conflicting reuse (materially different cwd/body/profile) fails closed;
- the mapping is durable under `$ROZORO_HOME` and survives caller/process crashes;
- ordinary starts without `--request-id` retain today's always-new behavior;
- concurrent duplicate requests are race-safe.

The feature should be described generically as **caller idempotency/correlation**, not graph functionality. Other automation callers can benefit from it.

**Exit gate:** a test can kill/retry the caller at each start boundary and prove one request id never creates more than one task/session.

## Groundwork G2 — dynamic long-lived task sensing (hard blocker for hands-off graphs)

Issue **#25** already tracks the necessary capability: a resident monitor with dynamic task membership, periodic reconciliation/fallback scanning, and health/status.

A graph creates downstream crews after the run has already started. Today's `rzr-watch --once <ids>` watches a static set, so a fully autonomous graph would otherwise need the watchtower itself to repeatedly re-arm watchers with newly created ids.

The graph runtime should not own a second Herdr event subscriber if Rozoro's generic monitor can provide this correctly.

Minimum graph dependency from #25:

- dynamically discover newly started tasks;
- surface actionable settled/blocked/gone changes without a static startup list;
- survive/reconcile after monitor restart/disconnect;
- expose machine-readable health so the graph runner can detect degraded sensing.

**Exit gate:** start task A, begin monitoring, create task B later, and observe B settle without restarting/reconfiguring the monitor.

## Groundwork G3 — machine-stable lifecycle result surface (recommended, independently queueable)

`rzr-status --json` already provides a machine-readable handoff view. The graph layer also needs stable machine consumption of start/send/resume operations and task identity.

Prefer adding explicit JSON output modes rather than parsing human log lines, e.g.:

```text
rozoro start ... --json
rozoro resume ... --json
rozoro send ... --json
```

At minimum return stable keys such as task key, cwd, session/link state, and operation outcome.

This is not a conceptual blocker—the graph runner can call lower-level helpers initially—but it materially reduces coupling and should be queued before or alongside the runtime if practical.

## Groundwork G4 — Pi wake path shares the durable ledger (parallel portability work)

Issue **#26** tracks integrating the Pi watchtower extension with the same generation/delivered/ack ledger as the external wake path.

This is **not required to prove the graph runtime** using a watchtower path that already consumes the durable ledger, but it is required before claiming uniform cross-harness graph wake semantics for Pi.

Queue independently from graph implementation.

## Groundwork G5 — reviewer/tester ping-pong skill (#27) as cross-crew prior art

PR **#27** captures a policy using one implementation crew plus an intentionally independent reviewer/tester crew with repeated fix/re-review rounds.

Treat it as useful prior art for **cross-crew isolation, resume semantics, and bounded cyclic feedback**, not as the canonical graph use case and not as evidence that ordinary review/testing should become separate graph nodes.

The default should remain: a crew owns its delivery responsibility and may use harness-native review/test subagents internally.

Use #27 as a stress/acceptance scenario only when the desired property is specifically **independent durable review context**.

Do not couple the graph IR to that skill's wording or PR-specific policy.

## Groundwork queue summary

| Work | Why | Blocks V1? | Can queue independently? |
|---|---|---:|---:|
| G1 caller-idempotent `start` | prevent duplicate node crews after crash/reconcile retry | **yes** | **yes** |
| G2 dynamic long-lived monitor (#25) | discover/sense nodes created later in a run | **yes for hands-off execution** | **yes** |
| G3 JSON lifecycle outputs | stable automation contract, less prose parsing | no | **yes** |
| G4 Pi durable-ledger integration (#26) | uniform Pi wake semantics | no for first harness; yes for parity | **yes** |
| G5 ping-pong skill (#27) | cross-crew isolation/resume stress case | no | already in PR |

If this plan is approved, G1 and G2 should be the first queueable implementation items. G3 and G4 can proceed in parallel when capacity permits.

# Graph implementation sequence after groundwork

## Phase 1 — graph IR, validator, and offline reconciler

Implement canonical graph schema and validation with no real agent spawning first.

Cover:

- crew-node/edge/join validation;
- detection of undeclared exits and missing nodes;
- cycle validation requiring bounded re-entry;
- fresh/resume mode validation;
- output declarations and template reference validation;
- deterministic computation of runnable nodes from synthetic event/state fixtures.

Exit gate: given a fixture stream, repeated reconciliation always derives the same enabled crew nodes and never performs duplicate logical transitions.

## Phase 2 — durable run journal and idempotent Rozoro dispatch

Add `$ROZORO_HOME/graphs/<run-id>/` with immutable graph IR, append-only events, and atomic materialized state.

Integrate G1 so each node attempt derives a stable request id, e.g.:

```text
<run-id>/<node-id>/<attempt>
```

Persist dispatch intent before calling Rozoro, then use caller idempotency so retry after any crash boundary cannot duplicate the crew.

Exit gate: fault-injection tests across persist/start/result/transition boundaries recover to one correct logical run.

## Phase 3 — node result contract + sequences/fan-out/joins

Deliver graph-result validation and the useful acyclic subset:

- sequence;
- parallel crew fan-out;
- `all`/`any` join;
- output substitution into downstream crew tasks;
- terminal success/failure/watchtower-attention state.

Primary acceptance scenario:

```text
backend ----\
             -> integration -> finished
frontend ---/
```

The backend and frontend crews may each use native subagents internally; the graph verifies only their declared durable outputs and the join.

## Phase 4 — bounded cross-crew resume loops

Add cyclic transitions with `fresh|resume` and attempt limits.

Primary acceptance scenario should exercise a deliberately independent context boundary:

```text
implementation crew -> independent review crew
        ^                       |
        |------ changes --------|

review approved -> finished
max attempts -> watchtower
```

This proves resume/re-entry without implying that normal review must be a separate crew.

A secondary stress scenario may reproduce #27 when independent reviewer/tester context is explicitly desired.

Require artifact identity (for example PR/head SHA) on such loops so approval for an older revision cannot satisfy completion after the implementation changes.

## Phase 5 — stacked PR playbook

Use ordinary node outputs to build a static stacked chain:

```text
slice-1 -> slice-2 -> slice-3
```

Each slice is one crew responsibility that delivers its PR review-ready. Internal review/test/scout subagents remain local to that crew.

Require explicit artifact identity (branch/PR/head SHA) so downstream slices cannot accidentally base themselves on an older revision.

## Phase 6 — reusable subgraphs/playbooks

Only after at least two real workflows demonstrate repeated **crew-level topology**, add reusable graph composition.

Plausible candidates/examples:

- `stacked-prs`;
- `parallel-work-then-integrate`;
- `independent-review-gate` only if repeated real use justifies the cross-crew boundary.

Do **not** add `reviewed-pr`, `review-fix-loop`, or `fanout-review-test` merely to model operations a single crew's harness can already perform with native subagents.

Do not add a catalog/framework before real graph definitions stabilize the minimal parameter contract.

# CLI shape

Keep the first user-facing vocabulary similarly small:

```text
rozoro graph run <graph-file>
rozoro graph reconcile <run-id>
rozoro graph status <run-id> [--json]
rozoro graph show <run-id>
```

If preserving Rozoro's strict "not a workflow engine" product boundary is preferred, these commands may live in a sibling `watchtower`/`wt` package instead. The important architectural rule is dependency direction:

```text
graph runtime -> Rozoro CLI/state contract
Rozoro core   -X-> graph runtime
```

No Rozoro spawn/status/send/resume primitive should import graph concepts, and Rozoro must not gain visibility into harness-native subagents.

`graph show` can render a text view first. Mermaid/visual UI should be projections of canonical run state, not the source of truth.

Example:

```text
parallel-app-change    RUNNING

✓ backend       attempt 1   ready
✓ frontend      attempt 1   ready
● integration   attempt 1   working
○ finished
```

# Correctness invariants

V1 should not be considered ready until these hold:

1. **Graph nodes are crew-sized responsibilities.** Harness-native subagents are not promoted into graph nodes or observed by the graph runtime.
2. **At most one crew per logical node attempt.** Reconciliation retries cannot duplicate starts.
3. **Persist before side effect.** A crash after a decision cannot lose the fact that the decision was made.
4. **No implicit edge choice.** Only declared, validated exits activate transitions.
5. **No stale acceptance.** When a cross-crew approval/gate is used, results tied to an older artifact/head cannot satisfy the current run.
6. **Loops are bounded.** Every cycle has an explicit finite attempt limit in V1.
7. **Resume is explicit.** The scheduler never guesses whether crew context should be retained.
8. **Watchtower judgment is explicit.** Unexpected/ambiguous states stop for attention instead of being interpreted by hidden heuristics.
9. **Graph state is recoverable from disk.** Killing the watchtower or graph process does not lose in-flight work.
10. **Rozoro remains usable independently.** Existing manual `start/status/send/resume/teardown` workflows are unchanged.
11. **Repo policy stays with the crew.** Graph nodes specify responsibility and topology; target-repository `AGENTS.md`/skills still govern domain execution and internal delegation.
12. **Parallelism alone does not force another crew.** The graph does not replace harness-native subagent orchestration.

# Testing strategy

Use the existing fake Herdr/test isolation for deterministic graph tests. Add fault injection rather than relying only on happy-path E2E tests.

Minimum cases:

- duplicate reconciler invocation before/after each dispatch persistence boundary;
- concurrent reconciliation attempts for one run;
- process kill after task spawn but before scheduler state write;
- malformed/missing/undeclared graph result;
- two independent crew branches finish in either order and correctly enable an `all` join;
- an `any` join enables exactly once;
- downstream output substitution uses the correct branch/PR/head from each upstream crew;
- bounded independent-review loop reaches success and separately exhausts to watchtower;
- implementation update invalidates stale independent approval;
- resume target is live vs reaped;
- monitor disconnect/restart while nodes finish;
- stacked nodes preserve intended base/head relationships;
- graph process restart reconstructs the same runnable set;
- no test requires or assumes visibility into harness-native subagents.

After fake coverage, live smoke-test one full crew-level fan-out/join against a real Herdr + harness combination. Then smoke-test one intentionally independent cross-crew resume loop before adding cross-harness matrix coverage.

# Non-goals for the first version

- replacing Rozoro with a general workflow engine;
- replacing or standardizing harness-native subagents;
- observing or scheduling a crew's internal subagent topology;
- creating separate crews merely for local review/test/scout parallelism;
- arbitrary user code/expression evaluation inside graph conditions;
- dynamic graph mutation/`foreach` discovered at runtime;
- cron or long-duration business workflow scheduling;
- distributed execution across machines;
- automatic PR merge policy inside Rozoro;
- storing graph state in GitHub issues/PRs;
- an embedded LLM scheduler;
- a visual editor before the canonical runtime semantics stabilize.

# Approval / queue proposal

Approval of this planning PR should authorize **groundwork to be queued separately**, not imply that the entire graph runtime lands as one PR.

Recommended queue after approval:

1. **G1:** generic caller-idempotent/correlated `rozoro start`.
2. **G2 / #25:** long-lived dynamic monitor and machine-readable health.
3. **G3:** structured JSON lifecycle outputs (can run in parallel with #25).
4. Begin graph Phase 1 (IR/validator/offline reconciler) while G1/G2 implementation is finishing, because Phase 1 has no live-spawn dependency.
5. Graph Phase 2+ only after G1 is proven; hands-off E2E only after G2 is proven.
6. **G4 / #26:** Pi ledger parity can proceed independently and becomes a cross-harness parity gate rather than a core runtime gate.
7. Use **G5 / #27** only as an optional cross-crew isolation/resume stress case, not as the canonical graph model.

Each groundwork item should remain generic and independently useful. The graph layer consumes those contracts; it should not force graph-specific concepts downward into Rozoro core or force harness-internal subagent concepts upward into the graph.
