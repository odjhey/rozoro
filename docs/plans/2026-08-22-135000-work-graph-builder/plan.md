# Work graph builder plan

Date: 2026-08-22

Repository baseline: `master` at `4bbcf7e`

Scope: planning artifact only. This plan does not add graph execution code or change Rozoro's existing spawn/watch/message/reap contract.

## Recommendation

Build a **work-graph layer above Rozoro**, not inside Rozoro's task/session primitives.

Rozoro should remain the deliberately small session substrate: start a crew, sense it, send DATA, execute CONTROL, resume it, and reap it. The new layer owns workflow topology and durable progression: which node may run, what completion exit was selected, which downstream node becomes runnable, when several nodes must join, and when a bounded loop must return control to the watchtower.

Use **work graph** rather than DAG as the core term. Straight-line and fan-out/fan-in workflows are DAGs, but review/fix/re-review and test/fix/re-test are intentionally cyclic.

The intended layering is:

```text
user
  |
  v
watchtower                    judgment, planning, policy
  |
  v
work-graph runtime            deterministic topology + reconciliation
  |
  v
rozoro                        spawn/watch/message/reap transport
  |
  +--> crew
  +--> crew
  +--> crew
```

The watchtower decides *what graph to run or build*. The graph runtime deterministically decides *what transition is enabled next*. Crew agents do domain work. Rozoro remains unaware of PRs, testing policy, graph edges, joins, or merge authority.

## Why this fits the current architecture

Rozoro already has most of the substrate a higher-level reconciler needs:

- durable unique task identities and task folders;
- append-only `handoff.md` history;
- lifecycle verdicts (`done`, `needs-action`, `failed`, `blocked`);
- explicit DATA vs CONTROL planes;
- exact session resume for supported harnesses;
- watcher status and a durable watchtower wake/reconciliation ledger;
- crash-safe state stored outside the process.

The missing abstraction is not another agent manager. It is a small durable state machine that compiles graph nodes into ordinary Rozoro tasks and reads machine-level node results when those tasks settle.

## Vocabulary

Keep the common language deliberately small:

- **graph** — one workflow definition.
- **run** — one durable execution of a graph.
- **node** — one unit of work.
- **edge** — a transition from one node exit to another node.
- **exit** — the workflow outcome selected by a successfully completed node.
- **output** — structured data exported by a node for downstream nodes.
- **attempt** — one execution/re-entry of a node.
- **join** — a condition waiting for `all`, `any`, or eventually a quorum of upstream exits.
- **subgraph/playbook** — a reusable graph definition.

Avoid introducing separate names for sequence, fan-out, retry, and loop primitives when they can be expressed using nodes, edges, joins, and bounded attempts.

## Separate task lifecycle from workflow outcome

Do not overload Rozoro's handoff `verdict` with graph semantics.

`verdict` answers:

> Did this crew successfully finish this turn/task, or does it need attention?

A graph **exit** answers:

> Which workflow path should run next?

For example, both reviewer outcomes below are successful task completions:

```text
verdict: done
exit: approved
```

```text
verdict: done
exit: changes
```

`changes` is not a failed agent execution. It is a valid reviewer result that routes back to the implementer.

## Node result contract

Preserve `handoff.md` as the human-readable append-only conversation record. Add an optional graph-owned sibling result for machine routing:

```text
tasks/<task-key>/
  brief.md
  handoff.md
  session.json
  graph-result.json
```

Example:

```json
{
  "schema": 1,
  "node": "review",
  "attempt": 2,
  "exit": "changes",
  "outputs": {
    "findings": "/tmp/review-findings.md",
    "pr": 412,
    "head_sha": "abc123"
  }
}
```

The graph layer appends a small completion contract to the node task: choose exactly one declared exit and emit the declared outputs. Rozoro still receives and delivers a normal task body verbatim; it does not parse or validate graph exits.

The graph runtime must validate `graph-result.json` against the node declaration before enabling an edge. Missing files, undeclared exits, malformed JSON, or missing required outputs become a graph-level exception requiring watchtower attention; they must never silently choose a transition.

## Minimal authoring model

YAML is a convenient authoring form, not the runtime truth. Compile it to a small canonical JSON IR so future watchtower generation, a TUI/GUI, or other builders do not couple the runtime to YAML syntax.

Illustrative authoring form:

```yaml
version: 1
name: reviewed-change

nodes:
  implement:
    crew: builder
    cwd: /repo
    task: implement the requested change
    exits: [ready]
    outputs: [branch, pr, head_sha]

  review:
    crew: reviewer
    task: review {{ implement.outputs.pr }}
    exits: [approved, changes]
    outputs: [findings]

  test:
    crew: tester
    task: test {{ implement.outputs.pr }}
    exits: [passed, failed]
    outputs: [findings]

edges:
  - from: implement.ready
    to: [review, test]

  - from: review.changes
    to: implement
    mode: resume
    max: 3

  - from: test.failed
    to: implement
    mode: resume
    max: 3

joins:
  accepted:
    all: [review.approved, test.passed]
    to: finished
```

The first implementation should support only:

1. nodes;
2. edges;
3. joins (`all` and `any` initially);
4. `fresh` vs `resume` transition mode;
5. bounded re-entry with `max` attempts;
6. typed/declared outputs by name;
7. a terminal success/failure/watchtower-attention state.

Do not add arbitrary expressions, embedded scripts, dynamic graph mutation, token budgets, cron scheduling, or a general plugin system in V1.

## Fresh vs resume is first-class

Agent context is part of orchestration semantics.

A review finding normally routes back to the **same implementer**, preserving its context:

```yaml
- from: review.changes
  to: implement
  mode: resume
```

A re-review may deliberately use either:

- `resume` — retain reviewer history and verify the fixes in context; or
- `fresh` — use a new independent reviewer to reduce anchoring.

Therefore keep these identities separate in persisted state:

- graph node identity;
- node attempt identity;
- Rozoro task key;
- harness/session identity.

A node may have several attempts and, depending on edge mode, one or several Rozoro tasks/sessions.

## Stacked PRs

A stacked PR sequence is a normal dependency chain whose outputs become downstream inputs:

```text
foundation -> api -> ui -> cleanup
```

Each node exports at least the branch/PR/head commit required by the next node. A downstream node can be instructed to base itself on the previous node's branch.

Once subgraphs exist, the preferred abstraction becomes:

```text
stacked-prs
  slice-1 -> reviewed-pr
  slice-2 -> reviewed-pr
  slice-3 -> reviewed-pr
```

where `reviewed-pr` itself contains implement/review/test/fix-loop behavior.

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
{"seq":2,"event":"node.ready","node":"implement","attempt":1}
{"seq":3,"event":"node.started","node":"implement","attempt":1,"task":"impl--01..."}
{"seq":4,"event":"node.completed","node":"implement","attempt":1,"exit":"ready"}
{"seq":5,"event":"node.ready","node":"review","attempt":1}
{"seq":6,"event":"node.ready","node":"test","attempt":1}
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
start/send/resume Rozoro tasks
```

The graph runner itself does not need an LLM.

## Watchtower attention nodes

Some transitions need judgment rather than deterministic routing. Represent that explicitly instead of hiding LLM decisions inside edge evaluation.

Example:

```yaml
decide:
  type: watchtower
  needs: [scout-a, scout-b, scout-c]
  exits: [approach-a, approach-b, abandon]
```

A watchtower node does not spawn another crew. It marks the run as requiring the resident watchtower to inspect the accumulated outputs and select one of the declared exits.

Wake the watchtower for:

- `needs-action` / `blocked` / unrecoverable task failure;
- invalid or missing graph result;
- loop-attempt exhaustion;
- explicit `type: watchtower` nodes;
- graph completion;
- other policy decisions intentionally not encoded in the graph.

Do **not** wake the watchtower merely to interpret deterministic edges such as `review.approved -> test`.

## Bounded loops

Every cyclic edge must have a finite attempt policy in V1.

Example:

```yaml
- from: review.changes
  to: implement
  mode: resume
  max: 3
  exhausted: watchtower
```

This prevents an autonomous review/fix loop from becoming an unbounded compute/cost loop. V1 only needs attempt count. Wall-time/token/cost budgets can be evaluated later.

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

A graph creates downstream tasks after the run has already started. Today's `rzr-watch --once <ids>` watches a static set, so a fully autonomous graph would otherwise need the watchtower itself to repeatedly re-arm watchers with newly created ids.

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

## Groundwork G5 — reviewer/tester ping-pong skill (#27) as behavioral prototype, not runtime dependency

PR **#27** captures the current human/watchtower policy for one implementer plus one independent reviewer/tester with repeated fix/re-review rounds.

Treat it as executable prior art and an acceptance scenario for the future graph runtime, not as a prerequisite. The graph should eventually be able to encode the same policy deterministically while preserving stable implementer/reviewer contexts.

Do not couple the graph IR to that skill's wording or PR-specific policy.

## Groundwork queue summary

| Work | Why | Blocks V1? | Can queue independently? |
|---|---|---:|---:|
| G1 caller-idempotent `start` | prevent duplicate node crews after crash/reconcile retry | **yes** | **yes** |
| G2 dynamic long-lived monitor (#25) | discover/sense nodes created later in a run | **yes for hands-off execution** | **yes** |
| G3 JSON lifecycle outputs | stable automation contract, less prose parsing | no | **yes** |
| G4 Pi durable-ledger integration (#26) | uniform Pi wake semantics | no for first harness; yes for parity | **yes** |
| G5 ping-pong skill (#27) | behavioral prototype / acceptance fixture | no | already in PR |

If this plan is approved, G1 and G2 should be the first queueable implementation items. G3 and G4 can proceed in parallel when capacity permits.

# Graph implementation sequence after groundwork

## Phase 1 — graph IR, validator, and offline reconciler

Implement canonical graph schema and validation with no real agent spawning first.

Cover:

- node/edge/join validation;
- detection of undeclared exits and missing nodes;
- cycle validation requiring bounded re-entry;
- fresh/resume mode validation;
- output declarations and template reference validation;
- deterministic computation of runnable nodes from synthetic event/state fixtures.

Exit gate: given a fixture stream, repeated reconciliation always derives the same enabled nodes and never performs duplicate logical transitions.

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
- parallel fan-out;
- `all`/`any` join;
- output substitution into downstream tasks;
- terminal success/failure/watchtower-attention state.

Acceptance scenario:

```text
implement -> [review, test] -> all green -> finished
```

## Phase 4 — bounded resume loops

Add cyclic transitions with `fresh|resume` and attempt limits.

Acceptance scenario should reproduce #27's essential behavior:

```text
implement -> reviewer
review changes -> same implementer
implement fixed -> same reviewer
repeat until clean or max attempts -> watchtower
```

Also test review and test in parallel where either can return the implementer to work and completion requires both green for the **same current artifact/head commit**. Stale approvals/results must be invalidated when the implementation output changes.

## Phase 5 — stacked PR playbook

Use ordinary node outputs to build a static stacked chain:

```text
slice-1 -> slice-2 -> slice-3
```

Each slice may itself use the reviewed-PR subgraph once reusable subgraphs are available.

Require explicit artifact identity (branch/PR/head SHA) so downstream slices and reviewer/tester approvals cannot accidentally target an older revision.

## Phase 6 — reusable subgraphs/playbooks

Once at least two real workflows demonstrate repeated topology, add reusable graph composition.

Candidate built-ins/examples:

- `reviewed-pr`;
- `review-fix-loop`;
- `fanout-review-test`;
- `stacked-prs`.

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

No Rozoro spawn/status/send/resume primitive should import graph concepts.

`graph show` can render a text view first. Mermaid/visual UI should be projections of canonical run state, not the source of truth.

Example:

```text
reviewed-change    RUNNING

✓ implement     attempt 1   ready
✓ review        attempt 1   approved
● test          attempt 1   working
○ finished
```

# Correctness invariants

V1 should not be considered ready until these hold:

1. **At most one crew per logical node attempt.** Reconciliation retries cannot duplicate starts.
2. **Persist before side effect.** A crash after a decision cannot lose the fact that the decision was made.
3. **No implicit edge choice.** Only declared, validated exits activate transitions.
4. **No stale acceptance.** If an implementation artifact/head changes, review/test approvals tied to an older artifact cannot satisfy the final join.
5. **Loops are bounded.** Every cycle has an explicit finite attempt limit in V1.
6. **Resume is explicit.** The scheduler never guesses whether context should be retained.
7. **Watchtower judgment is explicit.** Unexpected/ambiguous states stop for attention instead of being interpreted by hidden heuristics.
8. **Graph state is recoverable from disk.** Killing the watchtower or graph process does not lose in-flight work.
9. **Rozoro remains usable independently.** Existing manual `start/status/send/resume/teardown` workflows are unchanged.
10. **Repo policy stays with the crew.** Graph nodes specify work and topology; target-repository `AGENTS.md`/skills still govern domain execution.

# Testing strategy

Use the existing fake Herdr/test isolation for deterministic graph tests. Add fault injection rather than relying only on happy-path E2E tests.

Minimum cases:

- duplicate reconciler invocation before/after each dispatch persistence boundary;
- concurrent reconciliation attempts for one run;
- process kill after task spawn but before scheduler state write;
- malformed/missing/undeclared graph result;
- review/test fan-out finishing in either order;
- one branch requests fixes while another is still running;
- implementation update invalidates stale review/test success;
- bounded loop reaches success and separately exhausts to watchtower;
- resume target is live vs reaped;
- monitor disconnect/restart while nodes finish;
- stacked nodes preserve intended base/head relationships;
- graph process restart reconstructs the same runnable set.

After fake coverage, live smoke-test one full reviewed-change loop against a real Herdr + harness combination before adding cross-harness matrix coverage.

# Non-goals for the first version

- replacing Rozoro with a general workflow engine;
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

Each groundwork item should remain generic and independently useful. The graph layer consumes those contracts; it should not force graph-specific concepts downward into Rozoro core.
