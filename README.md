# rozoro

> [!WARNING]
> **WIP / fast-moving project.** Rozoro is being actively used and actively redesigned at the same time. Interfaces, terminology, and architecture can change quickly. Treat the current CLI and state formats as working software, not as a stable public contract.

Rozoro is a **highly opinionated way to deliver tasks to different coding harnesses** such as Claude Code, Codex, Pi, and Copilot while keeping each task independently visible, messageable, and resumable.

Today it does that through [Herdr](https://herdr.dev): one task becomes one harness session in an inspectable Herdr tab/pane, with durable local task state under `$ROZORO_HOME` and a watchtower-oriented workflow on top.

The current experience is useful and is intentionally being preserved while the project evaluates how much of the underlying session/runtime layer should instead be delegated to existing standards and tooling—especially:

- [Agent Client Protocol (ACP)](https://github.com/agentclientprotocol/agent-client-protocol) — a protocol for connecting clients and coding agents; and
- [acpx](https://github.com/openclaw/acpx) — a headless client for stateful ACP sessions.

We are **not** currently extracting a new `rozoro-core`. The next architecture step is to spike ACP/acpx against the capabilities Rozoro already relies on, then keep only the gaps that are actually worth owning. See [PR #77](https://github.com/odjhey/rozoro/pull/77) for the current decision direction.

## What Rozoro is today

The practical problem is simple: one coding-agent session is easy; many simultaneous tasks across repositories are not. You end up juggling terminals, remembering which session owns which task, copying follow-ups between places, and losing continuity when processes restart.

Rozoro gives an opinionated operating model around that problem:

```text
operator / watchtower
        |
        | start / status / send / control / resume
        v
     Rozoro
        |
      Herdr
        |
   +----+----+---------+---------+
   |         |         |         |
 Claude    Codex      Pi      Copilot
```

The current implementation provides:

- **durable task identity** — commands address a Rozoro task key rather than forcing the caller to track native harness session IDs;
- **parallel, inspectable sessions** — tasks live in Herdr tabs/panes that a human can inspect;
- **event-driven status** — `rozorod` owns durable lifecycle/event projections for managed paths;
- **two distinct communication planes** — DATA messages go to the coding agent; CONTROL actions operate the runtime/process;
- **exact-session continuation** — supported harness sessions can be linked and resumed rather than cold-started;
- **watchtower-friendly reporting** — durable handoffs and reconciliation make many simultaneous tasks easier to coordinate;
- **multiple coding harnesses** — Claude, Codex, Pi, and Copilot can be selected through launch presets/flags.

## Opinionated by design

Rozoro is not trying to be a universal multi-agent framework.

It currently assumes a particular style of work:

1. give a task to an independent coding-harness session;
2. let that session load and follow the target repository's own rules;
3. observe it without blocking the operator;
4. send follow-ups to the same conversation when needed;
5. preserve task/session continuity until the result is accepted or intentionally torn down.

A watchtower can use these primitives to coordinate many tasks, but repository-specific engineering policy belongs in the target repository and harness-native child-agent orchestration belongs in the harness.

If Claude/Pi/Codex can delegate internally using their own subagents, teams, trees, worktrees, or workflows, Rozoro should prefer those capabilities rather than reimplementing them.

## Architecture is under active evaluation

The current implementation is deliberately **not** being torn down while the architecture changes.

### Current operational path

```text
Rozoro CLI / watchtower
          |
       rozorod
          |
        Herdr
          |
 Claude / Codex / Pi / Copilot
```

This is the path to use today.

### Direction being tested

ACP and acpx already cover a substantial amount of the coding-session protocol and persistence problem that a hypothetical `rozoro-core` would otherwise need to implement.

The working hypothesis is therefore much thinner:

```text
watchtower / human / GitHub / CI / scripts
                  |
        stable task / mailbox layer ?
                  |
              ACP / acpx
                  |
          coding harness sessions
```

The `?` is intentional. The project first needs evidence that Rozoro adds enough value above ACP/acpx to justify owning that layer.

Potentially unique gaps include:

- a durable application/task address such as `pr-63` independent of native/ACP session identity;
- a mailbox for GitHub, CI, background jobs, humans, or other processes to deliver information to that task;
- attribution, ordering, acknowledgement, and supersession across many simultaneous tasks;
- continuity when the underlying coding-harness process/session is replaced or resumed;
- compatibility with the current watchtower experience.

If ACP/acpx already solves those sufficiently, Rozoro should shrink rather than rebuild them.

## What belongs elsewhere

Rozoro should not become the owner of every part of the engineering workflow.

| Concern | Owner |
|---|---|
| nested subagents, teams, trees, fan-out/fan-in | coding harness |
| worktree/branch/PR/test/merge rules | target repository / harness tooling |
| task decomposition and cross-task prioritization | watchtower/client/operator |
| correctness and final acceptance | reviewer/operator/application policy |
| review/test/docs/lint/PR/CI delivery gate | [no-mistakes](https://github.com/kunchenguid/no-mistakes) or repo delivery tooling |
| task/session transport, lifecycle, messages, resume | current Rozoro; ACP/acpx under evaluation |

A useful boundary is:

> If a feature needs to understand **what work should happen next**, it probably does not belong in the low-level Rozoro substrate.

## Requirements

The current implementation requires:

- `herdr` 0.8.x on `PATH` with a running server;
- `jq`;
- Python 3.11 or newer as `python3`;
- Bash (stock macOS Bash 3.2 is supported);
- at least one supported coding harness (`claude`, `codex`, `copilot`, or `pi`).

Run inside a Herdr session so new task tabs land in the current workspace.

## Install / preflight

```sh
git clone git@github.com:odjhey/rozoro.git
cd rozoro
./bin/rozoro doctor
```

`doctor` checks the current operational dependencies and selected harness configuration.

## Typical use

Start a durable task:

```sh
./bin/rozoro start fix-auth --body /tmp/task.md --cwd ~/src/my-repo
```

The command prints the exact task key. Use that key for later operations.

Inspect it:

```sh
./bin/rozoro status <task-key>
```

Send a follow-up to the same coding conversation:

```sh
./bin/rozoro send <task-key> "Re-check the failing macOS case."
```

Operate the runtime separately from conversational input:

```sh
./bin/rozoro control <task-key> interrupt
./bin/rozoro control <task-key> restart
```

Resume an already reaped supported conversation:

```sh
./bin/rozoro resume <task-key> --prompt "Continue from the previous result."
```

List known tasks:

```sh
./bin/rozoro list
```

## Main commands

| Command | Purpose |
|---|---|
| `./bin/rozoro start` | reserve a durable task key, render the brief, spawn, and link the session |
| `./bin/rozoro spawn` | lower-level task/session spawn |
| `./bin/rozoro status` | read daemon-backed lifecycle/task/report projection |
| `./bin/rozoro send` | DATA-plane prompt/follow-up |
| `./bin/rozoro control` | CONTROL-plane interrupt/cancel/key/stop/restart |
| `./bin/rozoro resume` | reopen the exact linked conversation when supported |
| `./bin/rozoro reconcile` | reconcile the current immutable wake generation |
| `./bin/rozoro ack` | advance task open-item acknowledgement |
| `./bin/rozoro list` | list known tasks and live state |
| `./bin/rozoro monitor start\|status\|stop` | operate/diagnose `rozorod` |
| `./bin/rozoro crew list\|show` | inspect current launch presets |
| `./bin/rozoro teardown` | close/remove live hosting while preserving the task folder |
| `./bin/rozoro doctor` | current dependency/capability preflight |

`watch` remains a diagnostics/legacy path; managed Pi and supported Claude use the resident event-bus path.

## DATA and CONTROL are deliberately different

```text
send      = tell the coding agent something
control   = tell the runtime/process something
```

`send` delivers text for the model to interpret.

`control` uses a closed set of runtime actions such as interrupt, cancel, key, stop, and restart. Rozoro does not encode a control request as chat text and hope the model obeys it.

## Durable task state

State lives under `$ROZORO_HOME` (default `~/.rozoro`). A task folder preserves the task's durable artifacts even after its live hosting is torn down.

Current task state includes artifacts such as:

- `brief.md` — task input;
- `handoff.md` — append-only application-level reports used by the current watchtower flow;
- `session.json` — linkage used to reopen the exact supported native conversation;
- identity/state metadata used to map the durable Rozoro task to current hosting/session identifiers.

These formats are part of the current working implementation but should not yet be treated as long-term stable public protocol contracts.

## Launch presets

Current presets live under `$ROZORO_HOME/crew/<name>.json` and describe how a harness is launched: harness, model, effort, permission mode, fast tier, and optional standing rules.

Example:

```json
{
  "harness": "codex",
  "model": "gpt-5.6-sol",
  "permission_mode": "yolo",
  "effort": "high",
  "fast": true,
  "rules": []
}
```

The `crew` terminology is historical/current UX. Whether this eventually becomes a simpler launch-profile concept depends on the ACP/acpx spike; no compatibility-breaking rename is planned merely for architectural cleanliness.

## Testing

The regression suite isolates itself from the real Rozoro home, Herdr session, harness stores, and working checkouts. It uses fake Herdr and local socket fixtures for protocol/lifecycle coverage.

Run the same containerized suite used by CI:

```sh
./tests/run.sh
```

Podman is preferred when available; Docker is the fallback. The suite covers shell/Python protocol parsing, event transport, lifecycle/reconciliation behavior, and locking. Real-Herdr checks remain manual integration smoke tests.

## Near-term direction

The next architecture experiment is **not** a rewrite.

The plan is:

1. keep current Rozoro usable;
2. exercise ACP/acpx for create/send/status/cancel/resume/persistence across supported harnesses;
3. compare that evidence against current Rozoro;
4. separately prove or disprove the need for durable task/mailbox indirection above ACP sessions;
5. build only the missing layer.

Until that experiment is complete, Herdr remains the current supported host and no new `rozoro-core`, tmux host abstraction, or replacement harness-adapter layer should be assumed.

## Project stance

Rozoro is intentionally experimental.

It is built around a real operating workflow, not around a claim that its abstractions are final. When a coding harness, ACP/acpx, Herdr, no-mistakes, or another existing tool solves a problem better, Rozoro should integrate with it, delegate to it, or delete the duplicate layer.

The goal is not to own the most framework. The goal is to keep multi-harness task delivery and follow-up practical.