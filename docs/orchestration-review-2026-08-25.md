# Orchestration review — 2026-08-25

A point-in-time critique of Rozoro's orchestration layer (Watchtower + wake delivery + policy surface), with comparisons against Gas Town / Gas City and other fleet-of-coding-agents tools, and a prioritized list of options. This document records analysis and proposals; nothing here is a committed decision. Where a proposal would constrain future work, it should graduate to an ADR in `docs/decisions/`.

Scope: orchestration only. Session spawning, protocol internals, and harness adapters are covered only where they shape orchestration behavior.

## Summary

The machinery **below** the Watchtower — durable task identity, the event bus, coalesced generations, ack/reconcile, conservative availability semantics — is unusual in the field and holds up well against every surveyed peer. The weak half is **above** the daemon: the Watchtower is a single, unwatched, effectively un-resumable LLM session whose working state lives in conversational memory, steered by roughly 1.3k lines of prose policy that no code enforces. The highest-leverage next step is the capability already described in [ADR-0004](decisions/0004-watchtower-mailbox.md): task-scoped attention items, plus a "prime" story that makes the Watchtower session as disposable as a crew session.

## Strengths (keep these)

1. **Durable task identity decoupled from session identity.** Across the survey, only vibe-kanban (tasks vs. task attempts), Google A2A (durable task objects), and Yegge's Beads make the same separation. Most tools equate task with session or branch and degrade when the session dies. This matches Yegge's own stated #1 transferable lesson from Gas Town: durable externalized work state is the part worth keeping; the orchestrator on top is swappable.
2. **The delivery reliability layer is best-in-class for its niche.** Durable-before-ack ingestion, spool replay with dedup, epoch-fenced registration, coalescing with urgent bypass, immutable generation snapshots, and ack-only-the-snapshotted-generation reconciliation. No surveyed peer has an equivalent; the closest analogs are A2A's webhook-then-refetch pattern and Claude Code Agent Teams' "idle notification carries no payload; reconcile from the task list" convention — both of which independently converged on the same wake-vs-payload separation Rozoro uses.
3. **Waking the LLM only on certified quiescent edges.** Gas Town's "propulsion principle" (prompt agents to self-propel) is its documented core failure mode; field reviews describe idle agents needing manual tmux nudges. A daemon that certifies quiescence and injects exactly one wake prompt is strictly more reliable and cheaper than always-on swarm chatter.
4. **Invariant discipline.** `done` is not acceptance; Herdr idle is not `quiescent`; prefer `unknown` to inference. Gas City's redesign (dropping the fixed role zoo, keeping primitives, delegating runtimes to providers) independently arrived at the position Rozoro's README already holds. Gas City even lists Herdr as a runtime provider.

## Weaknesses

### 1. The Watchtower's real state store is its context window

The reliability engineering stops at the generation boundary. Below it, everything is durable. Above it, partial handling of attention items, in-flight routing decisions, and "I already saw this needs-action" live only in the Watchtower's conversational memory. [ADR-0001](decisions/0001-one-primary-watchtower.md) itself warns against relying on conversational memory; the designed fix (attention items with independent handled/superseded state, ADR-0004) is unbuilt. Consequences:

- Watchtower context grows for the fleet's lifetime; no summarization, cycling, or handoff story exists for the driver itself.
- Duplicate-wake dedup is pushed onto the model (`templates/watchtower.md` declares duplicate notifications acceptable).
- A lost or wedged Watchtower session cannot be reconstructed: durable task folders and the progress-report skill rebuild *task* state, but not *what the driver had partially handled*.

Crew sessions already have the desired property (exact resume from `session.json` + append-only `handoff.md`). The Watchtower does not. Gas Town treats session cycling as normal operation because `gt prime` + hooks + beads rebuild working state from durable ground; Rozoro has no equivalent for the driver.

### 2. Policy is ~1.3k lines of prose that nothing enforces

The attempt budget, planner-before-coder default, model routing table, quick-crew eligibility, delivery-evidence head checks, and the multi-step no-mistakes procedures are all natural-language skills interpreted per-turn. Violations are silent. Two concrete facts sharpen this:

- The Pi launcher injects policy at launch (`bin/rzr-pi-watchtower.sh` passes `--append-system-prompt templates/watchtower.md`); the Claude launcher does not (`bin/rzr-claude-watchtower.sh` passes only `--settings` and session flags). Policy delivery to a Claude driver is not launch-guaranteed. `docs/dated-watchtower-artifacts.md` records Claude as `unverified-no-consumed-policy-args-array`. (Tracked as a standalone issue.)
- The deterministic-supervisor camp (vibe-kanban, Sculptor, Conductor) buys auditability with rigidity; Gas City's middle path is a code reconcile-loop supervisor plus declarative config, with LLM judgment only where judgment is needed.

### 3. "Push-based" is aspirational; the transport is a local poller

The daemon never initiates delivery. `bin/rzr-claude-watchtower-poll.py` loops every 100 ms sending `watchtower.availability`, and only on `quiescent` sends `notification.pending`; the Pi TS client polls every 500 ms. The server only ever returns a `notification` frame as the correlated response to a `notification.pending` request; its coalescer actuator is a deferred no-op, and the Pi client's unsolicited-notification branch is dead code against the current server. Push is real at the LLM level (the model idles until one injected prompt) but the transport is poll. Costs: continuous RPC load per driver, dead code, and a name that obscures the design.

### 4. Nobody watches the watchmen

Gas Town's watchdog chain (daemon → Boot → Deacon → Witness) exists because supervisors die too. Rozoro today:

- One `rozorod` per home. Down means the fleet sleeps: events spool durably, but no wakes fire until restart.
- Delivery confirmation binds to `herdr agent prompt` success, not to the LLM actually processing the wake. A wedged Watchtower leaves a delivered-but-unacked generation stalled until the next quiescent edge or a fresh registration epoch.
- No stall detection for crews: availability distinguishes `busy` from `gone`, but a crew that has been `busy` for 90 minutes going in circles is invisible until a handoff surfaces it. Gas Town's stalled/zombie taxonomy plus heartbeat-vs-tmux cross-validation is richer here.

### 5. Single-watchtower is hard-coded in disguise

`bump_actionable` advances every registered driver's `latest_generation` with no per-driver scoping (`lib/rozoro_monitor/store.py`), so the store's multi-driver rows are a fiction: two drivers would each be woken by every task's edges. Fine as a decision (ADR-0001), but then the multi-driver machinery is dead weight, and future partitioning (per-repo watchtowers) is a schema change rather than a config change.

### 6. Merge/delivery is the thinnest part of the pipeline

The surveyed field has converged on isolation-per-task plus an explicit merge gate (vibe-kanban rebase/PR flow; Gas Town's Refinery with Bors-style bisection over batched merge queues). Rozoro deliberately delegates this to the target repo, no-mistakes, and a Merge Finisher crew — a defensible boundary — but as parallel crews per repo grow, merge contention becomes the bottleneck, and today the entire flow is prose held in the driver's head. Gas City demoted merge queues from platform feature to pack/formula logic, which supports keeping this at policy level — but their version is a durable, checkpointed formula, not an unpersisted procedure.

## Options, in priority order

1. **Build the ADR-0004 mailbox and make the Watchtower resumable.** Task-scoped attention items with independent handled/superseded state, plus a `rozoro prime`-style command that renders fleet + attention state for a fresh driver session. This one capability fixes weakness 1, enables deliberate Watchtower cycling (the driver analog of `gt handoff`), caps context cost, and turns a wedged Watchtower into a respawn instead of archaeology. Per ADR-0004's own guidance, evaluate ACP/acpx and off-the-shelf local-first stores against the contract before building.
2. **Extract the enforceable subset of policy into code the Watchtower calls.** Not a policy engine — a few deterministic verbs: a `route` command that answers the crew/model/effort table, attempt-budget counting computed from durable turn history, delivery-evidence exact-head comparison. Skills shrink to judgment and procedure; violations become impossible rather than improbable. Also close the Claude launcher policy-injection gap (separate issue).
3. **Add a small deterministic patrol to `rozorod`.** Flag crews `busy` beyond a threshold with no events; re-offer delivered-but-unacked generations after a timeout without requiring a fresh epoch; surface both as ordinary actionable edges so the existing wake path carries them. This closes the stalled blind spot without importing Gas Town's role hierarchy.
4. **Continue the ACP/acpx bet; clean up the transport either way.** ACP `session/update` notifications provide typed push instead of pane prompt injection; acpx covers persistence and queueing; Gas City's provider list (tmux, subprocess, ACP, Kubernetes, Herdr) confirms the runtime layer is becoming pluggable. Independently: either implement genuine server-initiated frames over the already-persistent socket, or delete the dead unsolicited-notification branch and document the poll honestly.
5. **Decide multi-watchtower honestly.** Either scope generations per driver (enabling later partitioning) or remove the multi-driver machinery and record single-watchtower as an invariant. The halfway state is complexity with no capability.

## What not to copy from Gas Town

The fixed role hierarchy (Gas City itself abandoned it), propulsion-by-prompt (certified-edge wake is better), the cost profile (multiple $200/month accounts; field reviews report orphaned processes and supervisors that were not actually running), and the codebase sprawl. Rozoro's conservatism — `unknown` over inference, shrink over extract — is the trait most surveyed projects lack. The pure fleet-manager graveyard (Terragon, Bloop/vibe-kanban-the-company, Crystal) suggests survivors are local, protocol-adjacent, small-surface tools.

## Survey notes (condensed)

- **Gas Town / Gas City (Steve Yegge).** Gas Town: fixed roles (Mayor dispatch, Witness per-rig lifecycle patrol, Deacon cross-rig supervisor, Refinery merge queue with Bors-style bisection), Beads for durable work items, identity/sandbox/session three-layer split, session cycling as normal operation. Gas City: leaner SDK successor — six primitives (Agent, Bead, Formula, Rig, Pack, Event), roles become declarative `city.toml` config, a code reconcile-loop supervisor, pluggable runtime providers (tmux, subprocess, ACP, Kubernetes, Herdr), merge queues demoted to pack/formula logic.
- **Agent Teams (Claude Code, experimental).** The only other credible LLM-as-orchestrator: lead session coordinates via mailbox inbox files, idle notifications that carry no output, deterministic hook gates, and a shared durable task list. Documented gap: resume does not restore in-process teammates — the place where Rozoro's external-session model is stronger.
- **Deterministic-supervisor camp.** vibe-kanban (SQLite tasks/attempts, worktree per attempt, human kanban), Conductor (workspace per task, Mac app), Sculptor (container per agent, session fully persisted), container-use (container + git branch per environment, human polls), cmux (pane-native notifications via OSC escapes; UI only). Common shape: human orchestrator, deterministic code supervisor, LLM confined inside tasks, worktree-or-container isolation as table stakes.
- **Protocols.** ACP (JSON-RPC sessions with streamed `session/update`), acpx (headless persistent ACP client), A2A (durable task objects; sync, SSE, and webhook push delivery modes — the closest standardized analog to Rozoro's wake-then-reconcile pattern).

## References

- Gas Town: <https://github.com/steveyegge/gastown> (docs: propulsion-principle, heartbeats, polecat-lifecycle, molecules); Gas City: <https://github.com/gastownhall/gascity> (docs: gastown-command-map, config, system-packs); essays: <https://yegge.ai/gastown>, <https://yegge.ai/essays/welcome-to-gas-city/>; field review: <https://tenzinwangdhen.com/posts/gastown-good-bad-ugly/>; discussion: <https://news.ycombinator.com/item?id=46734302>
- Beads: <https://github.com/steveyegge/beads>
- Agent Teams: <https://code.claude.com/docs/en/agent-teams>; subagents: <https://code.claude.com/docs/en/sub-agents>
- vibe-kanban: <https://github.com/BloopAI/vibe-kanban>; Conductor: <https://conductor.build/>; container-use: <https://github.com/dagger/container-use>; cmux: <https://cmux.com/>; Sculptor: <https://imbue.com/blog/sculptor-announce>; claude-squad: <https://github.com/smtg-ai/claude-squad>; terragon-oss: <https://github.com/terragon-labs/terragon-oss>
- claude-flow/ruflo: <https://github.com/ruvnet/ruflo>
- ACP: <https://agentclientprotocol.com/overview/introduction>; acpx: <https://github.com/openclaw/acpx>; A2A: <https://a2a-protocol.org/latest/specification/>
- Layered-stack analysis (cmux / acpx / OMX): <https://codex.danielvaughan.com/2026/04/09/cmux-acpx-omx-three-layers-multi-agent-ux/>
