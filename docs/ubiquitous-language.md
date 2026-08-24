# Ubiquitous language

Use these terms consistently in code, docs, prompts, issues, and reviews. Prefer the product term even when one implementation exposes a differently named field.

| Term | Meaning | Do not collapse into |
|---|---|---|
| **Operator** | Human who supplies intent, business priority, and final acceptance. | watchtower, technical severity |
| **Watchtower** | Primary coordinating agent/session that decomposes, dispatches, reconciles, presents facts, and steers crews. | Rozoro daemon, workflow engine |
| **Crew** | Independent agent session assigned a durable task. | harness-native subagent |
| **Task** | Durable unit of delegated work with identity, brief, handoff history, and session linkage. | pane, turn, PR |
| **Turn** | One conversational work interval inside a harness session. | task |
| **Harness** | Agent runtime such as Pi, Claude, Codex, or Copilot. | Herdr |
| **Harness-native subagent** | Child/background work owned inside a crew's harness context. | separate Rozoro crew/task |
| **Host binding** | Current Herdr tab/pane/process location for a live session. | task identity, native session |
| **Native session** | Harness-owned resumable conversation identity. | host binding |
| **Session link** | Durable Rozoro record needed to reopen the exact native session. | current pane |
| **Event** | Normalized lifecycle fact accepted by `rozorod`. | notification |
| **Event Log** | Durable append-only history of accepted normalized events. | current state |
| **Projection** | Reduced current truth derived from durable evidence. | event history |
| **Availability** | Harness-neutral runtime state such as `busy`, `waiting-background`, `quiescent`, or `unknown`. | Herdr `idle`, task verdict |
| **Quiescent** | Semantically safe settled state supported by adapter evidence. | terminal idle alone |
| **Actionable change** | Projection/report transition that warrants watchtower attention/delivery. | business priority |
| **Technical severity** | Factual classification such as blocked/failed/needs-action/ready. | operator priority |
| **Generation** | Immutable delivery batch used to coalesce and reconcile wake work. | mailbox item, task, open item |
| **Generation membership** | Tasks/actionable reasons captured in one generation. | independent per-item handling |
| **Delivery offer** | One generation offered to a specific registered watchtower epoch. | successful handling |
| **Reconcile** | Read the exact durable generation snapshot/current facts and advance generation ACK according to protocol. | task resolution |
| **Generation ACK** | Durable acknowledgement that a delivery generation was reconciled. | task ACK, mailbox handled state |
| **Task open item** | Unresolved report/handoff item belonging to a task. | wake generation |
| **Task ACK** | Resolution/acknowledgement of surfaced task open-item state. | generation ACK |
| **Watchtower Mailbox** | Target durable collection of task-scoped attention items for a watchtower. | general actor mailbox, prompt queue |
| **Mailbox item** | Target stable identity for one task-scoped reason requiring attention. | generation membership row |
| **Mailbox handled state** | Target per-item observed/handled status. | task resolution |
| **Acceptance** | Operator decision that the result is satisfactory. | crew `done`, quiescence |
| **Reap** | Remove live hosting while retaining durable task/session artifacts. | delete task history |
| **Resume** | Reopen the exact durable native conversation into a new live host binding. | start a new task |

## Preferred distinctions

Use these non-equivalences as a review checklist:

```text
Herdr idle                != quiescent
runtime availability      != task verdict
crew done                 != operator acceptance
technical severity        != operator priority
event persisted           != notification delivered
notification delivered    != generation reconciled
generation reconciled     != task open item resolved
mailbox item handled      != task open item resolved
host binding              != native session
task                      != PR / branch / worktree
harness-native subagent   != Rozoro crew
```

## Current implementation names vs product terms

The current SQLite schema uses `pending_generations`, `pending_generation_tasks`, `generation_task_snapshots`, `watchtower_deliveries`, and `delivery_offers`. Those names describe the shipped delivery substrate accurately.

Do **not** casually rename generation membership to `mailbox item`: the target mailbox adds identity and independent handling semantics that generation membership does not yet provide.
