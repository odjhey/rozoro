# Rozoro control-plane contracts

This document captures the target product shape for Rozoro after separating the smart Watchtower role from the control plane, durable execution state, work topology, runtime hosting, and operator frontends.

It is an alignment document, not a claim that every interface below is implemented today. Status is marked as **exists**, **partial**, **missing**, or **move** where ownership is expected to migrate to zxro or Beads.

## Product identity

A **Watchtower** is any sufficiently capable smart agent entrusted with fleet-level orchestration judgment. It is not a specific model, harness, daemon, terminal, pane, or UI.

**Rozoro** is the local-first active control plane that lets such an agent operate a fleet of independent agent sessions. Rozoro provides actuation, runtime integration, event/wake delivery, adapter composition, and operator-facing control surfaces. The Watchtower provides the intelligence.

Target stack:

```text
                         Operator
                            |
                      any frontend
                            |
                 Rozoro Control Protocol
                            |
                         rozorod
                  active control plane
                            |
        +-------------------+-------------------+
        |                   |                   |
        v                   v                   v
      Beads                zxro            Runtime adapters
 work/dependency       execution/attention    ACP/acpx/native
      graph              durable ledger            |
                                                     v
                                                  Host port
                                             Herdr/tmux/process/SSH
                            |
                            v
                        Watchtower
                 smart protocol client
```

The repository's own DDD docs, contracts, ports, ADRs, and rules remain the semantic source the Task Decomposer, Replanner, and specialist crews interpret. Beads and zxro materialize accepted structure and execution facts; they do not replace that domain model.

## Core ownership rule

Use this split when deciding where future behavior belongs:

```text
Beads      remembers the accepted work graph.
zxro       remembers what executions happened and what attention remains.
Rozoro     makes agent/runtime operations happen and wakes the Watchtower.
Watchtower decides what should happen next.
```

Repository/provider systems remain authoritative for their own domains. For example, GitHub owns PR/CI state and no-mistakes/AXI owns pipeline state.

## Protocol overview

The target Rozoro product surface consists of three correctness-critical semantic ports plus two looser adapter surfaces:

```text
                         WATCHTOWER
                            |
        +-------------------+-------------------+
        |                   |                   |
        v                   v                   v
   Work/State Port     Agent Runtime Port    Attention Port
        |                   |                   |
  Beads + zxro          ACP/acpx/native      zxro + rozorod

                         optional adapters
                      +----------+----------+
                      |                     |
                      v                     v
                   Host Port           Frontend/View
                Herdr/tmux/etc.       browser/TUI/etc.
```

The stable product model must not mention Herdr tabs, tmux panes, terminal idle, Claude-specific session plumbing, or ACP transport details unless describing an adapter.

---

# 1. Watchtower contract

## Purpose

Define the role any smart agent must satisfy to act as the primary cognitive coordinator for one orchestration domain.

## Required capabilities

A Watchtower must be able to:

- inspect current work and structural readiness;
- inspect durable execution/turn evidence progressively;
- inspect pending attention without reading every historical artifact;
- start, steer, control, resume, and stop crew runtimes through the runtime port;
- reconcile authoritative external/runtime state after a wake;
- decompose, route, replan, prioritize, and judge within operator/repository policy;
- preserve one primary cognitive coordination authority for its fleet.

It must not infer:

- host idle = semantic completion;
- runtime availability = task verdict;
- turn completion = logical work acceptance;
- notification delivered = attention handled;
- technical severity = operator/business priority;
- graph completion = operator acceptance.

## Current status

**Partial, conceptually strong.**

The role already exists in `templates/watchtower.md`, `templates/watchtower-crew-dispatch-guidelines.md`, the ubiquitous language, and the one-primary-Watchtower ADR. Current launch/integration paths are still Pi/Claude-specific in places.

## Target rework

- Define Watchtower as a harness-neutral capability role.
- Treat Pi, Claude, Codex, or a future service as Watchtower hosts, not different Watchtower product types.
- Make the Watchtower a privileged client of the same Rozoro machine protocol used by CLI/frontends rather than giving it a separate internal API.

---

# 2. Agent Runtime Port

## Purpose

Provide one semantic interface for controlling an external agent conversation independent of whether the implementation is ACP/acpx, Pi, Claude, Codex, another CLI harness, or a future service.

The zxro `agent-runtime-port.md` draft already captures most of the desired semantics and should be treated as the strongest existing source for this contract.

## Target operations

```text
runtime.start(turn, initial_input?) -> RuntimeBinding
runtime.describe(binding)           -> RuntimeDescription
runtime.send(binding, text)         -> DeliveryResult
runtime.control(binding, action)    -> ControlResult
runtime.resume(binding, followup?)  -> RuntimeBinding
runtime.stop(binding)               -> StopResult
```

`RuntimeDescription` should expose conservative runtime state and capabilities, for example:

```json
{
  "binding": "rt-123",
  "native_session_id": "abc",
  "state": "working",
  "capabilities": {
    "send": true,
    "interrupt": true,
    "cancel": false,
    "exact_resume": true,
    "structured_lifecycle": true,
    "background_activity": true
  }
}
```

## Invariants

### DATA and CONTROL are separate

Free-form model-visible input:

```text
runtime.send(binding, text)
```

must never substitute for a control action such as:

```text
runtime.control(binding, interrupt)
runtime.control(binding, cancel)
runtime.stop(binding)
```

Unsupported CONTROL fails explicitly; it must not be translated into chat text.

### Start, resume, and replacement are different

```text
start new     = new conversation for a new delegated turn
resume exact  = the same recorded native conversation
replace       = create a new turn and new conversation deliberately
```

If exact resume cannot be proven, fail rather than silently cold-start.

### Capabilities are explicit

Adapters must describe unsupported operations rather than pretending every harness has the same semantics.

## Current status

**Partial; conceptually exists.**

Current Rozoro commands approximate the port:

```text
start / spawn
send
control
resume
teardown
status
```

The DATA/CONTROL split and exact-resume intent already exist. Current problems are coupling and command composition:

- `start` mixes durable reservation, brief rendering, host creation, runtime start, and session linking;
- `control key` is host-specific rather than portable runtime semantics;
- `control restart` conflates exact resume, replacement, and host restart/rebind;
- harness-specific shell/scripts act as implicit adapters instead of conforming to one formal port.

## Target rework

Keep high-level `rozoro start` as convenient UX, but implement it by composing lower-level semantic operations:

```text
ensure logical work/turn
        -> runtime.start
        -> persist session binding
        -> optionally create/present host view
```

Demote arbitrary key presses and raw terminal input to host-specific escape hatches.

---

# 3. Runtime lifecycle source contract

## Purpose

Separate **controlling** a runtime from **observing lifecycle facts** emitted by that runtime.

The Runtime Port answers "what can I ask this runtime to do?". A Lifecycle Source answers "what trustworthy lifecycle facts has this runtime produced?"

## Target shape

A lifecycle adapter registers a runtime binding and emits normalized facts such as:

```text
session_started
foreground_started
foreground_settled
background_started
background_settled
input_required
runtime_error
session_gone
```

Example envelope:

```json
{
  "schema_version": 1,
  "source": "acp",
  "runtime_binding": "rt-123",
  "native_session_id": "abc",
  "kind": "foreground_settled",
  "sequence": 43,
  "observed_at": "...",
  "evidence": {
    "background_active": false
  }
}
```

Structured harness evidence is semantic authority where it can certify the fact. Host/process liveness remains supporting evidence. Unknown is preferable to guessing from terminal idle.

## Current status

**Partial, substantial.**

Pi, Claude, Codex, and Herdr-related event paths already exist, but the product surface exposes implementation-specific adapters rather than one formal lifecycle-source contract.

## Target rework

Normalize ACP, Pi-native, Claude-native, Codex-native, and host-liveness fallback through one source-adapter interface and conformance suite.

---

# 4. Host Port

## Purpose

Represent where a live runtime is hosted without confusing that location with the task, turn, native session, or runtime conversation.

A host binding is a replaceable current attachment.

## Target object

```text
HostBinding {
  id
  provider
  native_host_id
  runtime_binding
  capabilities
}
```

## Target operations

```text
host.create(...)      -> HostBinding
host.describe(binding)-> HostState
host.list()           -> [HostBinding]
host.attach(binding)
host.detach(binding)
host.close(binding)
```

Example host capabilities:

```json
{
  "interactive": true,
  "focusable": true,
  "detachable": true,
  "raw_terminal": true,
  "remote": false
}
```

Possible adapters:

```text
HerdrHost
TmuxHost
SubprocessHost
SSHHost
ContainerHost
```

## Current status

**Missing as a generic contract; Herdr implementation exists.**

Herdr currently owns tabs/panes/process hosting, host-level liveness, addressing, and supported actuation. Older Rozoro material still leaks "one task -> one tab -> one pane -> one agent" assumptions even though the product docs already state that task identity is not a pane.

## Target rework

Treat Herdr as the first Host Port adapter. Remove tab/pane/keypress semantics from the portable core vocabulary.

---

# 5. Frontend/View Port

## Purpose

Let humans inspect and interact with fleet resources without making the UI authoritative or requiring the frontend to host the runtime.

A browser may display a session hosted by tmux or a plain process. A headless Watchtower may have no frontend at all.

## Target resources

Frontends should consume stable resources rather than pixel/layout contracts:

```text
fleet
work
turn/execution
runtime
attention
artifact
external-run
```

Optional presentation actions may include:

```text
view.focus(runtime_binding)
view.open_artifact(ref)
view.open_external_run(ref)
```

Potential implementations:

```text
HerdrFrontend
TmuxFrontend
BrowserFrontend
DesktopFrontend
TUIFrontend
HeadlessFrontend
```

## Current status

**Mostly missing as a contract.**

Herdr currently doubles as host and frontend. The no-mistakes Observatory establishes the useful precedent that a view is presentation-only and must not become semantic authority, branch custody, task ownership, or a wake mechanism.

## Target rework

Do not build a "browser Herdr replacement". Build a browser client of the same Rozoro machine protocol used by the CLI and Watchtower.

---

# 6. Work / planning port

## Purpose

Represent accepted logical work structure and cheap dependency/readiness queries without asking the Watchtower to repeatedly reconstruct structural bookkeeping.

## Target operations

```text
work.create
work.get
work.list
work.update
work.close
work.ready
work.dependencies
work.dependents
work.children
work.parents
work.link
```

## Intended ownership

Beads is the intended stronger planning/dependency graph. zxro may retain a stable Work identity for execution correlation. Link them by stable external references/metadata rather than mirroring whole records bidirectionally.

Task Decomposer/Replanner remain semantic compilers. They inspect repository contracts and produce/revise bounded work. The accepted structural result may then be materialized into Beads for deterministic ready/blocked/dependency queries.

Crews may recommend graph changes, but Watchtower should normally be the cognitive authority that accepts and writes planning-graph mutations.

## Current status

**Partial / transitional / move.**

Rozoro has durable task identities. zxro has Work. Dependency topology is not first-class in Rozoro and Beads adoption is planned.

## Target rework

Avoid creating a third competing Rozoro work graph. Compose Beads planning topology with zxro execution identity behind the Rozoro control plane.

---

# 7. Durable execution port

## Purpose

Persist one logical execution ledger independent from live runtime/host state.

## Target operations

```text
turn.create
turn.get
turn.list
turn.bind
turn.settle

artifact.put
artifact.stat
artifact.resolve
```

Future optional metadata may include attempt lineage, cost, token use, and duration without changing core lifecycle meaning.

## Intended ownership

zxro should become authoritative for durable execution semantics: work/turn identity, native-session binding, settlement/verdict, artifacts, and associated execution attention.

## Current status

**Partial / move.**

Rozoro already has task folders, append-only handoffs, session links, event log, and projections. zxro now has a more provider-neutral Work/Turn/Artifact contract designed specifically for this extraction.

## Target rework

Preserve `rozoro start/status/resume` as useful facade commands where appropriate, but move durable execution truth toward zxro rather than maintaining parallel Rozoro task/turn stores indefinitely.

---

# 8. Attention Port

## Purpose

Persist cognitive work separately from wake delivery.

## Target operations

```text
attention.unread
attention.pending
attention.ack
attention.handle
attention.history?   # optional diagnostics
```

Required distinctions:

```text
read != handled
handled != work closed
wake delivered != read
turn settled != attention handled
```

## Intended ownership

zxro should own durable event identity, read cursor, and per-item handled state. `rozorod` should own resident wake/coalescing/activation mechanics.

## Current status

**Exists conceptually and substantially, but split.**

Rozoro already has durable events, actionable generations, delivery offers, reconcile/ACK, generation membership, and task open-item ACK. The current generation-centric substrate is sophisticated but conflates delivery batching with some of the product's desired attention semantics. zxro's mailbox model makes read and handled state explicit.

## Target rework

Consolidate durable attention into one owner instead of keeping both a zxro mailbox and an independent long-term Rozoro mailbox model.

---

# 9. Wake / activation port

## Purpose

Activate a dormant Watchtower when durable attention may require judgment.

Wake is intentionally content-light and disposable. Authoritative state remains in zxro/Beads/runtime/external systems.

## Target operations

```text
wake.register(watchtower, endpoint/capabilities)
wake.unregister(...)
wake.offer(watchtower, token, affected_refs[])
wake.confirm(...)
```

Example wake envelope:

```json
{
  "schema_version": 1,
  "type": "attention_available",
  "watchtower_id": "main",
  "token": "wake-123",
  "affected": [
    "zxro:work:auth-fix",
    "external:no-mistakes:run-42"
  ]
}
```

After wake, the Watchtower reconciles authoritative state. A wake payload must not become semantic truth.

## Current status

**Exists, but coupled to durable generation machinery.**

`rozorod` already handles Watchtower registration, epochs, coalescing, delivery offers, confirmation, reconcile, and ACK.

## Target rework

Retain resident registration/coalescing/activation in Rozoro while moving durable attention identity/read/handled semantics toward zxro.

---

# 10. External event-source adapter contract

## Purpose

Normalize asynchronous facts from no-mistakes, GitHub/CI, runtime providers, timers, or other systems into durable attention plus optional Watchtower activation.

## Target shape

```text
source.register(resource_ref)
source.unregister(resource_ref)
source.describe(resource_ref)
```

A source emits idempotent normalized events containing stable source-resource identity and the originating logical work reference.

Example:

```json
{
  "schema_version": 1,
  "source": "no-mistakes",
  "resource": "run:abc",
  "work_ref": "zxro:auth-fix",
  "kind": "input_required",
  "idempotency_key": "...",
  "observed_at": "..."
}
```

Persist source facts before attempting a wake. Progress may be durable without waking; actionable/terminal edges may request activation.

## Current status

**Partial.**

Pi/Claude/Codex lifecycle paths and the no-mistakes event-adapter design already exhibit this pattern, but there is no single external-source contract.

---

# 11. Rozoro Control Protocol

## Purpose

Expose one versioned machine interface from the active composition layer so CLI, browser, desktop, tmux helpers, and Watchtower can be clients of the same semantics.

`rozorod` is the natural resident server because Rozoro, not zxro, owns active orchestration integration and Watchtower activation.

## Target namespaces

```text
system.*
work.*
turn.*
runtime.*
attention.*
host.*
```

Frontend-specific presentation APIs should remain light and optional.

Example request/response shape only:

```json
{
  "schema_version": 1,
  "request_id": "req-42",
  "op": "runtime.send",
  "params": {
    "binding": "rt-abc",
    "text": "Address the reviewer findings."
  }
}
```

```json
{
  "schema_version": 1,
  "request_id": "req-42",
  "ok": true,
  "data": {
    "delivery": "accepted"
  }
}
```

The exact transport is an implementation decision. A local Unix socket is plausible because `rozorod` is already resident, but transport must not define semantics.

## Current status

**Missing as a general public composition API.**

The CLI is effectively today's API, and `monitor.sock` is a specialized event-bus interface rather than a general control protocol.

## Target rework

Make:

```text
rozoro CLI
browser
future desktop/TUI
a Watchtower host
```

clients of one control-plane protocol.

`rozorod` should act as facade/supervisor over zxro, Beads, runtime adapters, and host adapters, not duplicate their durable domains into another giant database.

---

# 12. Adapter capability contract

## Purpose

Allow heterogeneous runtime/host adapters without pretending all implementations support the same semantics.

Example runtime adapter description:

```json
{
  "adapter": "acpx",
  "kind": "runtime",
  "protocol_version": 1,
  "capabilities": {
    "start": true,
    "send": true,
    "exact_resume": true,
    "interrupt": true,
    "structured_lifecycle": true
  }
}
```

Example host adapter:

```json
{
  "adapter": "tmux",
  "kind": "host",
  "protocol_version": 1,
  "capabilities": {
    "interactive": true,
    "focus": true,
    "detach": true,
    "raw_terminal": true
  }
}
```

Unsupported capabilities fail explicitly. A weaker behavior must not silently emulate a stronger semantic contract.

## Current status

**Missing as a first-class contract.**

Capability support currently appears through harness-specific conditionals, scripts, and fail-closed paths.

---

# 13. System / health API

## Target operations

```text
system.describe
system.health
system.adapters
system.capabilities
system.version
```

This should expose machine-readable daemon health and adapter availability without requiring frontend-specific knowledge.

## Current status

**Partial.**

`rozoro doctor`, `rozoro monitor status --json`, crew/preset inspection, and adapter-specific diagnostics already cover pieces of this.

---

# Current command mapping

The following current commands are useful UX even if their underlying implementation changes.

| Current command | Target interpretation | Disposition |
|---|---|---|
| `rozoro start` | High-level composition of work/turn creation, runtime start, session binding, optional host/view | Keep as facade |
| `rozoro send` | Resolve current runtime binding then `runtime.send` | Keep |
| `rozoro resume` | Exact native conversation resume only | Keep, tighten invariant |
| `rozoro status` | Composed projection of work + execution + runtime + attention | Keep as view/facade |
| `rozoro doctor` | System/adapter capability health | Keep/evolve |
| `rozoro spawn` | Raw runtime start bypassing durable task semantics | Demote to debug/runtime-level or redefine |
| `rozoro control key` | Raw host input | Demote to host-specific escape hatch |
| `rozoro control restart` | Ambiguous mix of host/runtime/logical replacement | Replace with explicit resume/replace/rebind operations |
| `rozoro link` | Durable native session binding | Migrate toward zxro `turn.bind` semantics |
| generic `ack` | Currently overloaded across delivery/task concepts | Replace in machine protocol with precise read/handle/close operations |

The public machine API should be more precise than compatibility CLI aliases.

---

# Current-vs-target matrix

| Component / contract | Status | Target owner/direction |
|---|---|---|
| Watchtower role | **Exists** | Formal harness-neutral capability contract |
| Watchtower prompt/policy | **Exists** | Keep above core |
| Task Decomposer/Replanner policy | **Exists** | Keep semantic decomposition agentic |
| Runtime DATA/CONTROL split | **Exists** | Promote into formal Runtime Port |
| Exact resume semantics | **Exists conceptually** | Formal runtime invariant |
| Runtime adapter abstraction | **Partial** | ACP/native conformance adapters |
| Structured lifecycle adapters | **Partial** | Formal Lifecycle Source contract |
| Herdr hosting | **Exists** | First Host Port adapter |
| Generic Host Port | **Missing** | Add |
| Generic Frontend/View contract | **Missing** | Add lightly |
| Browser control API | **Missing** | Client of Control Protocol |
| tmux support | **Missing adapter** | Host/frontend adapter |
| ACP/acpx support | **Partial/planned** | Reference Runtime Port adapter |
| Runtime capability negotiation | **Missing** | Add |
| Durable logical work | **Exists in overlapping forms** | Beads planning graph + zxro execution reference |
| Dependency/ready graph | **Missing in Rozoro** | Beads |
| Durable turns | **Exists messily / zxro stronger** | zxro |
| Session binding | **Exists / zxro stronger** | zxro |
| Artifacts | **Exists / zxro stronger** | zxro |
| Durable attention | **Exists but generation-centric** | consolidate toward zxro |
| Read vs handled distinction | **Partial Rozoro / explicit zxro** | zxro |
| Wake coalescing | **Exists** | keep in `rozorod` |
| Watchtower registration/activation | **Exists** | keep in `rozorod` |
| External event adapters | **Partial** | generic source adapter |
| no-mistakes event adapter | **Specified, not yet generic** | external source adapter |
| General Rozoro machine API | **Missing** | `rozorod` Control Protocol |
| CLI | **Exists** | facade/client over stable protocol |
| System health/capabilities | **Partial** | unified machine API |
| Adapter conformance suites | **Missing** | add |
| UI is non-authoritative | **Exists as principle** | generalize |
| One resident control service | **Exists: `rozorod`** | keep |
| zxro daemon | **Not required** | remain invocation-scoped unless a concrete future requirement changes this |

---

# `rozorod` target shape

## Current shape

Today `rozorod` owns or participates in:

```text
event ingestion
append-only event log
task/session projections
actionable generations
generation snapshots/membership
delivery ledger
Watchtower registration/epochs
reconcile/ACK
wake delivery
```

Much of this exists because Rozoro had to establish durable semantics before zxro was extracted.

## Target shape

As zxro and Beads take more durable ownership, `rozorod` should trend toward:

```text
rozorod
├── Rozoro Control Protocol server
├── adapter supervisor
│   ├── runtime adapters
│   ├── lifecycle source adapters
│   ├── external source adapters
│   └── host adapters
├── inherently-live runtime projections
├── wake coordinator
│   ├── Watchtower registration
│   ├── coalescing
│   ├── delivery/activation
│   └── activation health
└── facade over
    ├── zxro
    ├── Beads
    └── runtime/host providers
```

For every current `rozorod` table or state machine, ask:

> Is this durable execution/attention truth, or inherently resident runtime/control-plane state?

Durable execution/attention truth is a candidate to move to zxro. Work topology is a candidate to move to Beads. Live adapter supervision, wake coalescing, activation, and machine-protocol serving remain Rozoro responsibilities.

`rozorod` should not become another copied source of truth over zxro, Beads, runtime state, GitHub, or no-mistakes.

---

# zxro daemon decision

The target architecture does **not** require a resident zxro daemon.

zxro is passive durable infrastructure: each command/provider operation may read, validate, atomically mutate, durably commit, and exit. `rozorod` is the resident active orchestration authority because it must observe asynchronous systems, supervise adapters, coalesce wakeups, expose the active control-plane protocol, and activate dormant Watchtowers.

A future optional zxro service may implement the same public durable contracts if a demonstrated requirement appears, such as remote shared access or first-class standalone subscriptions. Daemon presence must not become part of zxro semantics merely because Rozoro has a daemon.

A useful distinction is:

```text
zxro      durable, invocation-scoped, transactional
rozorod   resident, reactive, adapter-supervising, activating
```

The zxro mailbox records that attention exists. `rozorod` says "look now". Losing a wake must not lose the durable attention.

---

# Recommended contract-writing order

Do not standardize every proposed surface at once. The highest-leverage next documents are:

1. **Watchtower contract** — role, authority, required capabilities, forbidden inferences.
2. **Agent Runtime Port** — promote the existing zxro semantic runtime port and define adapter capability negotiation.
3. **Host Port** — extract hosting from Herdr-specific tab/pane semantics.
4. **Rozoro Control Protocol** — versioned machine API served by `rozorod`, with CLI/Watchtower/browser as clients.

Lifecycle-source and external-event adapters can then conform to one normalized ingress model. Frontend/View contracts should remain deliberately light until a second frontend proves which abstractions are actually portable.

---

# Architectural principles to preserve

- **Watchtower decides; Rozoro actuates.**
- **Semantics stay agentic; bookkeeping moves downward into deterministic systems.**
- **The repo/domain model informs decomposition; a stored graph is a materialized plan, not the source of meaning.**
- **Runtime, host, task/work, turn, session, PR, and UI identities remain distinct.**
- **Structured lifecycle evidence outranks terminal idle.**
- **DATA and CONTROL never collapse into one channel.**
- **Exact resume never silently becomes a cold start.**
- **Persist durable facts before notifying.**
- **Wake delivery is disposable; durable attention is not.**
- **UI/Observatory state is presentation only.**
- **Unsupported adapter capabilities fail explicitly.**
- **Prefer one resident active control plane (`rozorod`) over daemonizing every durable subsystem.**
- **Prefer adoption through stable ports over reimplementing provider domains inside Rozoro.**
