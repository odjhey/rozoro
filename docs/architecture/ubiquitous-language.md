---
name: ubiquitous_language
description: "Canonical Rozoro terms for code, prompts, issues, reviews, and docs — verified against the current implementation."
type: reference
tags: [architecture, language]
status: current
generated: "Claude Fable 5, 2026-08-28"
created_at: 2026-08-28T00:00:00+08:00
---

# Ubiquitous language

Use these terms consistently in code, docs, prompts, issues, and reviews. Prefer the product term even when one implementation exposes a differently named field. Every term below is verified against the current implementation; terms that exist only in policy prose (no code representation) are marked **(prose-only)**.

## Identity and hosting

| Term | Meaning | Do not collapse into |
|---|---|---|
| **Operator** | Human who supplies intent, business priority, and final acceptance. | watchtower, technical severity |
| **Watchtower** | Primary coordinating agent session that decomposes, dispatches, reconciles, presents facts, and steers crews. | Rozoro daemon, workflow engine |
| **Crew** | Independent agent session assigned a durable task. | harness-native subagent |
| **Harness** | Agent runtime: `claude`, `codex`, `copilot`, or `pi`. | Herdr |
| **Harness-native subagent** | Child/background work owned inside a crew's harness context. | separate Rozoro crew/task |
| **Task key** | Immutable globally unique task identity, `<display>--<ULID26>`, naming both `state/<key>.meta` and `tasks/<key>/`. Reserved by atomic `mkdir`. | pane, display name |
| **Display name** | Caller-chosen concise label (≤80 chars), recorded in `identity.json`; also the default tab label. | task key |
| **Herdr agent name** | Transport identity `rzr-<sha256(task_key)[:28]>` (Herdr caps agent names at 32 chars). | task key, native session |
| **Pane** | Herdr pane id (`wX:pN`) — the addressing authority for a live agent. | task identity |
| **Tab** | Herdr tab id (`wX:tN`) — the container holding exactly one pane. | pane, task |
| **Host binding** | Current Herdr tab/pane location for a live session (`state/<key>.meta`). | task identity, native session |
| **Native session** | Harness-owned resumable conversation identity (UUID). | host binding |
| **Session link** | Durable record (`tasks/<key>/session.json`) needed to reopen the exact native session. | current pane |
| **Home** | The one shared data namespace: `ROZORO_HOME` > `RZR_HOME` > `~/.rozoro`, owner-private (0700). | checkout, repo |

## Task lifecycle

| Term | Meaning | Do not collapse into |
|---|---|---|
| **Task** | Durable unit of delegated work with identity, brief, handoff history, and session linkage. Exists as `tasks/<key>/`; is *live* only while `state/<key>.meta` exists. | pane, turn, PR |
| **Brief** | Rendered task input: `rozoro-task:` marker line, folder pointer, verbatim operator body. Never overwritten. | system prompt, handoff protocol |
| **Handoff** | The crew's append-only outbound report log (`tasks/<key>/handoff.md`). | chat transcript |
| **Handoff block** | One `## turn <n>` report with `verdict`/`reason`/`did`/`pending`/`inputs-needed`/`artifacts`. | turn event |
| **Verdict** | Handoff field: `done`, `waiting`, `needs-action`, `failed`, or `blocked`. | availability, acceptance |
| **Turn** | One conversational work interval inside a harness session. | task, handoff block |
| **Task ACK** | Advancing the per-task acknowledged-block cursor (`.acked-blocks-v2`). | generation ACK |
| **Reap / teardown** | Remove live hosting (tab, meta, runtime state) while retaining durable task artifacts. | delete task history |
| **Resume** | Reopen the exact durable native conversation into a new live host binding. Refused while the task is still tracked. | restart, new task |
| **Restart** | Teardown plus fresh spawn from recorded meta — the same task key but a **new** conversation. | resume |
| **Lineage** | Derived, read-only merge of inbound prompts, handoff blocks, attention decisions, and turn boundaries into one ordered view per task. | stored state, attempt counters |
| **Drift** | Lineage inequality `inbound == blocks == turns` failing: a prompt produced no report, or a report landed outside a turn. | protocol error |

## Events and projections

| Term | Meaning | Do not collapse into |
|---|---|---|
| **Event** | Normalized lifecycle fact accepted by the event bus (protocol v1): `session.register`, `turn.start`, `turn.stop`, `background.start`, `background.stop`, `background.snapshot`, `session.end`. | notification |
| **Event log** | Durable append-only history of accepted events (`monitor.db.events`). | current state |
| **Projection** | Reduced current truth derived from durable evidence (`task_projections`). | event history |
| **Producer sequence** | Strictly contiguous per-session event ordering; gaps buffer and de-certify availability. | Herdr `state_change_seq` (a different ordering domain) |
| **Spool** | The durable producer outbox (`$ROZORO_HOME/spool/`); spool publication precedes sequence-cursor advance, removal follows a matching ACK. | queue, cache |
| **Availability** | Harness-neutral runtime state: `busy`, `waiting-background`, `quiescent`, `blocked`, `gone`, `unknown`. | Herdr `idle`, verdict |
| **Quiescent** | Semantically settled state certified by structured lifecycle evidence (foreground stopped **and** background clear). | terminal idle alone |
| **Background activity** | The independent axis `active`/`clear`/`unknown`; `clear` requires an authoritative snapshot, never inference from a stop edge. | foreground status |
| **Report state** | Mechanical handoff parse status: `missing`, `malformed`, `valid`. | verdict |
| **Actionable reason** | One of the 14 whitelisted `(report_state, verdict, actionable_reason)` combinations — the frozen report tuple matrix. | business priority |

## Delivery and attention

| Term | Meaning | Do not collapse into |
|---|---|---|
| **Generation** | Immutable delivery batch used to coalesce and reconcile wake work; membership is frozen at bump time. | attention item, task, open item |
| **Wake / nudge** | The single fixed, content-free injection: `Rozoro notification pending; run ./bin/rozoro reconcile.` | event data, instructions |
| **Delivery offer** | One generation offered to a specific registered watchtower epoch. | successful handling |
| **Reconcile** | Read the changed-since-last-ACK snapshot (full on request) and advance the generation ACK to exactly the snapshotted generation. | task resolution, daemon repair |
| **Generation ACK** | Durable acknowledgement that a delivery generation was reconciled. Invariant: `acked ≤ delivered ≤ latest`. | task ACK |
| **Attention item** | Durable per-`(task, reason)` file in the attention ledger with stable identity, status, and handling log. | generation membership row |
| **Attention ledger** | The watchtower's driver-surviving decision notebook (`watchtowers/attention/items/*.md`). | event log, mailbox implementation commitment |
| **Watchtower Mailbox** | Product shorthand for stable task-scoped attention identity with independent handling. The attention ledger is the interim implementation. | general actor mailbox, prompt queue |

## Supervision and policy

| Term | Meaning | Do not collapse into |
|---|---|---|
| **Driver identity** | Transport-derived stable identity (`<backend>-<sanitized identity>`, e.g. `herdr-w1_p1`, `claude-<uuid>`) used to reattach a watchtower registration to its wake target. | watchtower name, native session |
| **Registration** | The validated wake-delivery target: `watchtowers/<driver>/target.json` (commit point) plus `registrations.jsonl` (append-only history). | launch, authority |
| **Authority** | Which delivery path owns a driver: the `.event-bus-authority` marker (`event-bus-v1\n`) makes the daemon authoritative and hard-fences every legacy ledger writer. | registration |
| **Incarnation** | Per-launch identity component (Claude watchtower: `<native>.<incarnation>`); exact resume reuses the driver but mints a new incarnation. | driver identity |
| **Crew preset** | Spawn profile (`crew/<name>.json`): harness, model, effort, permission mode, fast, rules. Describes HOW an agent boots, never WHAT its task is. | watchtower preset, task |
| **Watchtower preset** | Versioned launch metadata (`watchtower-presets/<name>.json`, harness `claude`/`pi` only); its bytes are attributable by hash. Deliberately no virtual default. | crew preset |
| **Mission** | Policy file naming what a watchtower's fleet is for; exactly one resolves (shipped `templates/missions/` xor operator `watchtower-missions/`), composed after the mechanics core. | mechanics core, preset |
| **Policy digest** | `policy_sha256 = sha256(core_bytes ‖ mission_bytes)` — the attributable identity of the composed policy a driver launched under. | preset sha |
| **Live gate** | The quiescent-only injection discipline: a wake reaches a resident driver only when its availability is `quiescent`, and delivery is confirmed only after the backend succeeds. | polling loop |
| **Workset** **(prose-only)** | Mission vocabulary: the group of tasks that together produce one integrated outcome. No file, schema, or CLI verb models it. | task, generation |
| **Attempt budget** **(prose-only)** | Cumulative coder-attempt/replan counters (`10 → 20 → 30`, ≤3 replans) derived from durable history by policy, not stored by Rozoro. | lifecycle field |
| **Acceptance** | Operator decision that the result is satisfactory. | crew `done`, quiescence |

## Non-equivalences (review checklist)

```text
Herdr idle                != quiescent
runtime availability      != task verdict
crew done                 != operator acceptance
technical severity        != operator priority
event persisted           != notification delivered
notification delivered    != generation reconciled
generation reconciled     != task open item resolved
attention item handled    != task open item resolved
host binding              != native session
task key                  != pane != tab != herdr agent name != native session
task                      != PR / branch / worktree
harness-native subagent   != Rozoro crew
send (data plane)         != control (command plane)
producer_seq              != herdr state_change_seq
```

## Implementation names vs product terms

The current SQLite schema (v6) uses `pending_generations`, `pending_generation_tasks`, `generation_task_snapshots`, `watchtower_deliveries`, `delivery_offers`, `generation_membership_snapshots`, `disabled_drivers`. Those names accurately describe the shipped delivery substrate.

Do **not** casually rename generation membership to `attention item`: the attention ledger provides the stable-identity/independent-handling semantics as a skill-owned interim implementation, and the daemon's generation machinery deliberately does not.
