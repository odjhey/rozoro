# rozoro

> [!WARNING]
> **WIP.** Rozoro is used for real work, but it is changing fast. Commands, names, state formats, and architecture may change without notice.

Rozoro is a highly opinionated way to hand tasks to different coding harnesses such as Claude Code, Codex, Pi, and Copilot, while keeping each task visible, messageable, and resumable.

Today, Rozoro runs those sessions through [Herdr](https://herdr.dev). One task gets one harness session in a Herdr tab and pane. Rozoro keeps task state under `$ROZORO_HOME` and gives a watchtower or human a common set of commands to start, inspect, message, control, and resume that session.

If you're looking to adopt this approach today, start with these instead:

- [Agent Client Protocol (ACP)](https://github.com/agentclientprotocol/agent-client-protocol), a protocol for connecting clients and coding agents.
- [acpx](https://github.com/openclaw/acpx), a headless client for persistent ACP sessions.

Rozoro is still an experiment built around a specific workflow. Do not treat its current internals as the general-purpose base for a new system.

We are not extracting a new `rozoro-core` right now. The next step is to test ACP and acpx against the things Rozoro already depends on, then decide what is still worth keeping here. See [PR #77](https://github.com/odjhey/rozoro/pull/77).

## What Rozoro does today

One coding session is easy to manage. Ten parallel tasks across several repositories are not. The annoying part is usually not starting the agents. It is remembering which session owns which task, checking what changed, sending follow-ups to the right place, and keeping the same conversation when a process restarts.

Rozoro currently gives you this:

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

It provides:

- durable task keys, so callers do not need to track native harness session IDs;
- separate Herdr tabs and panes that a human can inspect;
- `rozorod` for lifecycle events and status on managed paths;
- separate DATA and CONTROL commands;
- exact conversation resume where the harness supports it;
- durable handoffs and reconciliation for watchtower use;
- launch support for Claude, Codex, Pi, and Copilot.

## The workflow is opinionated

Rozoro assumes this style of work:

1. Hand a task to an independent coding session.
2. Let that session load the target repository's own rules.
3. Check its state without blocking the operator.
4. Send follow-ups to the same conversation.
5. Keep the task and session around until the result is accepted or deliberately torn down.

A watchtower can coordinate several of these tasks. Repository rules still belong in the repository. Child-agent behavior belongs in the coding harness.

If Claude, Pi, Codex, or another harness can handle subagents, teams, trees, worktrees, or fan-out on its own, Rozoro should use that capability instead of copying it.

## What may change

The Herdr-backed path is the one that works today:

```text
Rozoro CLI / watchtower
          |
       rozorod
          |
        Herdr
          |
 Claude / Codex / Pi / Copilot
```

ACP and acpx already cover much of the session protocol and persistence work that we were considering building ourselves. That is why the `rozoro-core` extraction is paused.

The next experiment is simple. Test whether ACP and acpx can replace enough of this lower layer without breaking the Rozoro workflow we already use.

The part that may still belong in Rozoro is smaller:

```text
watchtower / human / GitHub / CI / scripts
                  |
          task address / mailbox
                  |
              ACP / acpx
                  |
          coding harness sessions
```

Things worth testing include:

- a stable task name such as `pr-63` that does not depend on an ACP or native session ID;
- a mailbox where GitHub, CI, background jobs, humans, or scripts can send information to that task;
- ordering, attribution, acknowledgement, and supersession for those messages;
- keeping the same task address when the underlying coding session is resumed or replaced;
- keeping the current watchtower workflow usable.

If ACP and acpx already handle these well enough, Rozoro should get smaller.

## What belongs elsewhere

| Concern | Owner |
|---|---|
| nested subagents, teams, trees, fan-out and fan-in | coding harness |
| worktree, branch, PR, test, and merge rules | target repository or harness tooling |
| task decomposition and cross-task priority | watchtower, client, or operator |
| correctness and final acceptance | reviewer, operator, or application policy |
| review, test, docs, lint, PR, and CI delivery gate | [no-mistakes](https://github.com/kunchenguid/no-mistakes) or repository tooling |
| task/session transport, lifecycle, messages, and resume | Rozoro today, with ACP and acpx under evaluation |

A useful rule for future changes:

> If a feature has to decide what work should happen next, it probably does not belong in the low-level Rozoro code.

## Requirements

The current implementation needs:

- `herdr` 0.8.x on `PATH` with a running server;
- `jq`;
- Python 3.11 or newer as `python3`;
- Bash. Stock macOS Bash 3.2 is supported;
- at least one supported coding harness, `claude`, `codex`, `copilot`, or `pi`.

Run Rozoro inside a Herdr session so new task tabs land in the current workspace.

## Install and preflight

```sh
git clone git@github.com:odjhey/rozoro.git
cd rozoro
./bin/rozoro doctor
```

`doctor` checks the current dependencies, Herdr connection, and selected harness configuration.

## Typical use

Start a task:

```sh
./bin/rozoro start fix-auth --body /tmp/task.md --cwd ~/src/my-repo
```

The command prints the exact task key. Use that key for later commands.

Check it:

```sh
./bin/rozoro status <task-key>
```

Send a follow-up to the same conversation:

```sh
./bin/rozoro send <task-key> "Re-check the failing macOS case."
```

Interrupt or restart the runtime without sending chat text to the model:

```sh
./bin/rozoro control <task-key> interrupt
./bin/rozoro control <task-key> restart
```

Resume a supported conversation after teardown:

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
| `./bin/rozoro start` | reserve a task key, render the brief, spawn, and link the session |
| `./bin/rozoro spawn` | lower-level task and session spawn |
| `./bin/rozoro status` | read daemon-backed lifecycle, task, and report state |
| `./bin/rozoro send` | send DATA text to the coding agent |
| `./bin/rozoro control` | interrupt, cancel, send a key, stop, or restart the runtime |
| `./bin/rozoro resume` | reopen the exact linked conversation where supported |
| `./bin/rozoro reconcile` | reconcile the current wake generation |
| `./bin/rozoro ack` | advance task open-item acknowledgement |
| `./bin/rozoro list` | list known tasks and live state |
| `./bin/rozoro monitor start\|status\|stop` | operate and inspect `rozorod` |
| `./bin/rozoro crew list\|show` | inspect launch presets |
| `./bin/rozoro teardown` | close live hosting while keeping the task folder |
| `./bin/rozoro doctor` | check dependencies and harness support |

`watch` is for diagnostics and legacy compatibility. Managed Pi and supported Claude sessions use the resident event bus.

## DATA and CONTROL are different

```text
send      = tell the coding agent something
control   = tell the runtime/process something
```

`send` gives text to the model.

`control` executes a fixed runtime action such as interrupt, cancel, key, stop, or restart. Rozoro does not turn those actions into chat messages.

## Durable task state

State lives under `$ROZORO_HOME`, which defaults to `~/.rozoro`. Task folders remain after live hosting is torn down.

A task currently stores files such as:

- `brief.md`, the task input;
- `handoff.md`, append-only reports used by the watchtower flow;
- `session.json`, the native session link used for resume;
- metadata that maps the Rozoro task key to the current host and harness session.

These files are part of the current implementation. Their format is not a stable public API yet.

## Launch presets

Presets live under `$ROZORO_HOME/crew/<name>.json`. They describe how to start a harness: harness, model, effort, permission mode, fast tier, and optional standing rules.

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

`crew` is the current command and file name. We may rename it later if the ACP and acpx work points to a simpler launch-profile model. There is no reason to break compatibility just to clean up the name.

## Operator artifact skills

Project skills under `.agents/skills/` can persist two owner-private, dated operator records under `$ROZORO_HOME/artifacts`:

- `watchtower-policy-snapshot` copies the current launch-time Watchtower policy source with hashes and Git provenance;
- `watchtower-progress-report` records a conservative fleet summary from durable task folders without treating `done` as verified or accepted.

Invoke them with Pi's `/skill:<name>` commands or run their bundled Python scripts directly. Each run gets a new unambiguous UTC path and is retained until explicitly deleted. See [Dated Watchtower artifacts](docs/dated-watchtower-artifacts.md) for schemas, privacy boundaries, and examples.

## Testing

The test suite does not touch your real Rozoro home, Herdr session, harness state, or working checkout. It uses a fake Herdr implementation and local socket fixtures for protocol and lifecycle tests.

Run the same containerized suite used by CI:

```sh
./tests/run.sh
```

The runner uses the first running container engine it finds, preferring Podman over Docker. Tests cover shell and Python protocol parsing, event transport, lifecycle and reconciliation behavior, and locking. Tests against a real Herdr server are still manual integration checks.

## Next experiment

This is not a rewrite plan.

The next work is:

1. Keep the current Rozoro workflow working.
2. Test ACP and acpx for create, send, status, cancel, resume, and persistence across the harnesses we use.
3. Compare the result with current Rozoro.
4. Test whether a separate durable task address and mailbox are still useful above ACP sessions.
5. Build only what is still missing.

Herdr stays supported while we do this. We are not assuming a new `rozoro-core`, tmux host layer, or replacement harness adapter until the spike shows a real need.

## Project stance

Rozoro exists because this workflow has been useful in practice. That does not mean every layer it currently owns should stay here.

If a coding harness, ACP, acpx, Herdr, no-mistakes, or another tool already does part of the job better, use it. Keep Rozoro for the parts that are still useful.