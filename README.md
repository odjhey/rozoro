# rozoro

A deliberately tiny agent-session orchestrator over the [herdr](https://herdr.dev)
terminal backend. A **driver** (the "control tower" — usually a powerful model in
its own session) uses rozoro to **spawn, watch, message, and reap** a fleet of
agent sessions. Each **task** is one herdr **tab** holding one **pane** running
one agent. All state lives on disk under `$ROZORO_HOME` (default `~/.rozoro`), so
killing the driver loses nothing — the next command reconciles from disk.

The core mechanics:

1. **spawn sessions as tabs** — one crew agent per tab, from a reusable preset
2. **event-driven updates** — a push subscriber to herdr's status stream, no polling
3. **send to sessions** — a DATA-plane follow-up the agent reads, or a
   CONTROL-plane verb (interrupt, cancel, a key press, stop, restart) the
   harness executes — never conflated
4. **lockfile** — single-driver safety around the spawn mutation

## What rozoro is for

The problem: one agent session is easy to run, but the moment you want three or
five tasks worked in parallel — across different repos — you become a tab-juggler,
babysitting sessions and copy-pasting context. rozoro's goal is to let **one
driver session run a fleet** without that overhead. The driver talks to you and
dispatches; each crew agent works its task in its own tab; the driver watches,
steers, and reaps.

Concretely, rozoro aims to be:

- **The smallest useful spawn/watch/message/reap layer over herdr** — four verbs,
  not a framework. If herdr already does it, rozoro doesn't wrap it.
- **Crash-safe by being stateless in-process.** All state is files under
  `$ROZORO_HOME`; there is no daemon. Kill the driver and the next command
  reconciles from disk — nothing in flight is lost.
- **A leverage multiplier for the driver.** The driver dispatches *eagerly* and
  delegates *discovery* (reading issues, reproducing bugs, weighing approaches) to
  the crew, rather than pre-solving work itself. rozoro is the hands; the crew is
  the domain expert; the driver is the judgment.

## What rozoro is *not* (non-goals)

These are deliberate. rozoro stays small by refusing to grow into them:

- **Not a manager or workflow engine.** It knows nothing about worktrees, PR
  resolution, delivery, testing, or merge authority — and never will. Those are
  repo-specific and belong to the crew agent (see the design boundary below).
- **Not a harness or a model.** It *launches* harnesses (`claude`, `codex`, …);
  it doesn't replace or wrap their reasoning.
- **Not a policy layer over the crew.** rozoro is a *transport, not a gatekeeper*
  — a dumb spawner, not a manager. Task prompts pass through verbatim; it never
  rewrites, filters, or approves what you tell the crew. The only injection is a
  preset's standing `rules`, and only as a separate appended system prompt.
- **Not a daemon or always-on service.** No background process maintains state;
  `state/<id>.status` exists only after a watcher has run.
- **Not a replacement for repo rules.** The crew loads the target repo's own
  `AGENTS.md` / `CLAUDE.md` / skills from its `--cwd`; rozoro never re-encodes them.
- **Not a doer of domain work.** rozoro spawns "Resolve issue #NNN" and stays out
  of the way. It does not read the code, pick approaches, or judge correctness —
  that intelligence is the driver's and the crew's.

## rozoro is a spawner, not a manager (the design boundary)

rozoro is intentionally dumb. It does **not** know about worktrees, PR
resolution, delivery, or merge authority — and it never will. Those are
**repo-specific** and belong to the **spawned agent**, which loads the target
repo's own rules (`AGENTS.md`, skills, `CLAUDE.md`) from its `--cwd`. rozoro
spawns "Resolve issue #NNN" and stays out of the way; the crew agent — and any
harness-native subagents it spawns — does everything domain-specific.

Consequently:

- **Task prompts are passed verbatim.** rozoro never edits what you tell a crew
  to do. The only thing it injects is a preset's standing `rules`, and only as an
  *appended system prompt*, never into the task.
- **The intelligence is the driver's.** "Identify the work, dispatch, steer,
  judge done" is the driver session using rozoro + `gh` as tools — spawning on the
  default crew unless you ask for a specific one, and leaving the investigation to
  the crew. rozoro is the hands.

## Requirements

- `herdr` 0.8.x on `PATH`, a running server, and you running **inside** a herdr
  session (so new tabs land in your workspace). Verify: `herdr tab list`.
- `jq`
- `python3` (stdlib only) — for the event-stream watcher
- `bash` — runs on stock macOS `/bin/bash` 3.2 (no bash-4 features)

## Install

There is nothing to build and no dir to create — `$ROZORO_HOME` (default
`~/.rozoro`) and its `state/`, `crew/`, `tasks/` subdirs are created lazily on
first use. To set up a machine:

```sh
git clone git@github.com:odjhey/rozoro.git
export PATH="$PWD/rozoro/bin:$PATH"     # add to your shell rc to persist
rozoro doctor                           # verify deps, herdr server, PATH, preset
```

`rozoro doctor` is the preflight — it checks the binaries, that the herdr server
answers, that `bin/` is on PATH, and the resolved default harness. Green means
you can `rozoro start` a task.

Two ways to call every command: the friendly dispatcher `rozoro <verb>` (or the
short `rzr <verb>`), or the underlying `rzr-<verb>.sh` script directly — e.g.
`rozoro start …` ≡ `rzr start …` ≡ `rzr-start.sh …`.

## The tools (`bin/`)

| Command | What it does |
|---|---|
| `rozoro <verb> [args]` (or `rzr <verb>`) | dispatcher: `rozoro start …` runs `rzr-start.sh …`; `rozoro help` lists verbs |
| `rzr-start.sh <id> --body <file> [opts]` | blessed start: `rzr-render` → `rzr-spawn` → `rzr-link` in one unskippable step; passes extra flags through to `rzr-spawn` |
| `rzr-spawn.sh <id> [opts]` | `herdr tab create` → `agent start` (from a crew preset) → optional verbatim first prompt; records `state/<id>.meta` |
| `rzr-render.sh <id> <body>` | render `tasks/<id>/brief.md` from `templates/brief.md` (handoff protocol + `rozoro-task:` marker); prints its path |
| `rzr-link.sh <id> <cwd>` | capture `tasks/<id>/session.json` for Claude or Codex via marker-grep; idempotent |
| `rzr-status.sh <id>` | latest handoff `verdict` + new-block miss-detector, plus any unresolved OPEN items (needs-action/blocked/failed or a set `inputs-needed`) that a later `done` would otherwise bury — surfaced until acked |
| `rzr-ack.sh <id> [--through n]` | mark a task's surfaced OPEN items resolved (advances a read cursor; never edits the append-only handoff) |
| `rzr-watch.sh [--once] [id…]` | subscribes to herdr's `pane.agent_status_changed` push stream; prints one line per real state change; zero polling |
| `rzr-send.sh <id> <text>` | **DATA plane only**: `herdr agent prompt` (submit) — text the agent reads and reasons about; `--wait` blocks until settled |
| `rzr-control.sh <id> <verb>` | **CONTROL plane only**: a closed, EXECUTED verb list — `interrupt` \| `cancel` \| `key <name>` \| `stop` \| `restart` — never text the agent might interpret as chat; fails closed on an unresolved target and verifies its own postcondition (`herdr agent wait`) |
| `rzr-resume.sh <id> [--prompt <t>]` | reopen a reaped Claude or Codex task's *exact* conversation as a fresh tab (from `tasks/<id>/session.json`); optionally deliver a follow-up. Refuses if the task is still live (use `rzr-send`) |
| `rzr-crew.sh list\|show <name>` | inspect crewmember presets (spawn profiles) |
| `rzr-lock.sh status\|acquire` | inspect/hold the home lock (atomic `mkdir`, stale-pid reclaim) |
| `rzr-list.sh` | known tasks + live agent state |
| `rzr-doctor.sh` | preflight: deps (`herdr`/`jq`/`python3`), herdr server reachable, `bin/` on PATH, default preset — exits non-zero on a missing hard dep |
| `rzr-teardown.sh <id> [--force]` | close the tab, remove the record (the `tasks/<id>/` folder survives); refuses if the recorded `cwd` has unlanded work (uncommitted/untracked changes, unpushed commits) unless `--force` |

`rzr-lib.sh` is the shared library (paths, herdr invocation, meta, status,
presets, lock); it is sourced, not run. `herdr-eventwait.py` is the raw-socket
subscriber `rzr-watch.sh` drives. `templates/brief.md` is the handoff-protocol seed
`rzr-render` fills in.

### Durable task folders

`rzr-start` gives each task a folder under `$ROZORO_HOME/tasks/<id>/` so teardown is
non-lossy: `brief.md` (the input), `handoff.md` (append-only output — each turn the
crew appends a `verdict:` block, so `done` is distinguishable from `needs-action`
and context accumulates across `rzr-send` rounds), and `session.json` (the resume
link). It is **data** — it lives in `$ROZORO_HOME`, never in this repo.

That covers the task *record*; teardown separately guards the crew's actual
work: it refuses to close a task whose recorded `cwd` has uncommitted,
untracked, or unpushed changes, so a crew's real output is never discarded
silently (`--force` overrides).

## Crewmember presets

A **preset** bundles *how* a crew agent is booted — harness, model, effort,
permission mode, and standing `rules` — never *what* its task is. Presets are one
JSON file per name under `$ROZORO_HOME/crew/<name>.json`. For example, the
personal `$ROZORO_HOME/crew/default.json` can select gpt-5.6-sol/high:

```json
{
  "harness": "codex",
  "model": "gpt-5.6-sol",
  "permission_mode": "",
  "effort": "high",
  "rules": []
}
```

- `$ROZORO_HOME/crew/default.json` is authoritative when present. Rozoro never
  creates, migrates, or rewrites it.
- If that file is absent, the hardcoded fallback is Claude/Sonnet/`auto`.
  Passing `--harness codex` instead selects gpt-5.6-sol/`low` with the harness's
  normal permission behavior.
- Spawn from one with `rzr-spawn.sh <id> --crew <name> …`.
- **Precedence** for harness/model/effort/permission-mode: explicit flag > preset
  file > hardcoded harness fallback. `rules` come only from the preset file.
- `rules` are **crew-behavioral** (e.g. "never push"), deliberately distinct from
  **repo** rules, which the agent auto-loads from `--cwd`.

**Harness mapping** (preset fields → the underlying binary's flags, via herdr's
`agent start … -- <arg>` passthrough):

| harness | maps to | notes |
|---|---|---|
| `claude` | `--model --effort --permission-mode --append-system-prompt` | verified on this machine |
| `codex`  | `--yolo --model <m> --config model_reasoning_effort=<e>` | model and effort verified against the local CLI |
| `copilot`| `--model <m> --mode autopilot --allow-all` | wired; not verified here |
| `pi`     | *(no flags)* | `pi` takes none; model/effort/rules ignored |

Claude and Codex support `effort`; only Claude has a dedicated system-prompt
channel for `rules`. Harnesses without one receive the protocol and rules in the
delivered prompt. An unmapped harness fails loudly rather than launching with
wrong flags.

## Instructing rozoro (the control tower)

The driver's whole vocabulary is small:

| Trigger | Call |
|---|---|
| **Start** a task | `rzr-start.sh <id> --body <file> --cwd <repo> [--crew <preset>] [--model <model>]` |
| **Steer** (DATA — text the agent reads) | `rzr-send.sh <id> "<text>"` |
| **Interrupt / cancel / key / restart** (CONTROL — executed, never read) | `rzr-control.sh <id> interrupt` · `rzr-control.sh <id> cancel` · `rzr-control.sh <id> key <name>` · `rzr-control.sh <id> restart` |
| **Resume** a reaped task | `rzr-resume.sh <id> [--prompt "<follow-up>"]` |
| **Stop** | `rzr-teardown.sh <id>` (≡ `rzr-control.sh <id> stop`; refuses on unlanded work in the crew's `cwd`, `--force` to discard anyway) |
| *(sense, not trigger)* | `rzr-status.sh <id>` (handoff verdict) · `rzr-watch.sh` · `rzr-list.sh` · `rzr_status_get` (disk `state/<id>.status`) |

**DATA vs CONTROL, and why it's split.** A crew must receive two clearly
distinct kinds of message, never conflated: DATA is free text the agent reads
and reasons about (`rzr-send.sh`); CONTROL is a lifecycle action from a closed
verb list that the harness *executes* (`rzr-control.sh`) — never text the agent
might interpret as chat. The failure this prevents: a lifecycle command
arriving as chat the agent "reads" instead of the harness carrying out. Control
verbs also fail closed on target resolution (an unresolved task/pane is refused
loudly, never guessed at) and verify their own postcondition rather than
trusting a herdr call's exit code alone.

Put `bin/` on `PATH` (or drive it via the bundled skill) so the driver session
can reach these from anywhere. Read crew state from the on-disk
`state/<id>.status` (the watcher keeps it current) rather than blocking on
`rzr-watch`.

### Launching the driver

The driver is just a capable agent session with the rozoro skill in reach and a
system prompt that keeps it in the control tower. That prompt is versioned in this
repo at [`templates/watchtower.md`](templates/watchtower.md) — maintain it there,
not inline. Launch the driver **inside a herdr session**, from a repo whose skills
path ships the skill (this repo's `.claude/skills/rozoro/` does):

```sh
claude --append-system-prompt-file templates/watchtower.md
```

Editing `templates/watchtower.md` and committing it is how you evolve the driver's
standing behavior; every watchtower booted from the file inherits the change. Keep
it short — the rozoro skill carries the detailed loop. The one idea it must anchor
is the boundary: **the driver spawns and judges; the crew does the domain work.**
(rozoro-the-tool is the dumb spawner; the driver is the judgment.)

## Examples

The blessed flow is `rozoro start` (durable brief + spawn + session link in one
step); reach for raw `rzr-spawn` only for throwaway probes. All verbs work as
`rozoro <verb>`, `rzr <verb>`, or `rzr-<verb>.sh`.

**Fan out several issues in parallel** — one id + body per task, dispatched
eagerly, then one event-driven watcher over the fleet:

```sh
for n in 42 57 61; do
  printf 'Resolve issue #%s in this repo — investigate, fix, and open a PR.\n' "$n" \
    > /tmp/task-$n.md
  rozoro start issue-$n --body /tmp/task-$n.md --cwd ~/proj/acme
done
rozoro watch issue-42 issue-57 issue-61     # wakes on each real edge; no polling
```

On each edge, read the **handoff verdict** — not herdr's raw `done` — then reap:

```sh
rozoro status issue-42        # done → verify the result, then reap
rozoro teardown issue-42      #   (tasks/issue-42/ survives teardown)
```

**Steer a live crew (DATA)** — a follow-up is submitted as text the agent reads:

```sh
rozoro send issue-57 "Skip the refactor — smallest fix that closes the issue."
```

**Interrupt a runaway turn (CONTROL)** — executed, never handed to the agent as
chat; verifies the agent actually left `working` before reporting success:

```sh
rozoro control issue-57 interrupt
```

**Dispatch a scout (investigation only, no PR)** — knowledge, not a change:

```sh
printf 'Investigate why CI flakes on the auth suite. Write findings; change no code.\n' \
  > /tmp/scout.md
rozoro start scout-ci-flake --body /tmp/scout.md --cwd ~/proj/acme
```

**Override the crew when you explicitly want a bigger model:**

```sh
rozoro start issue-99 --body /tmp/task-99.md --cwd ~/proj/acme --model opus
```

**Use a custom preset** — e.g. a "draft PR, never push" crew, defined once under
`$ROZORO_HOME/crew/`, then reused:

```sh
rozoro crew list                                   # see available presets
rozoro start issue-77 --body /tmp/t.md --cwd ~/proj/acme --crew draft-only
```

**Follow up after `done` without losing context.** `done` is an invitation to
review, not a signal to reap — a done crew sits idle at ~0 cost. If it's still
live, just continue it (same agent, full context):

```sh
rozoro send issue-42 "Reviewed — also handle the null-token case, then re-push."
```

**Resume a task you already reaped** — if it was torn down before your follow-up
arrived, reopen the *exact* conversation (not a cold re-spawn) and hand it the
feedback in one step:

```sh
rozoro resume issue-42 --prompt "Also handle the null-token case, then re-push."
#   → new tab, harness resumes <uuid>, crew picks up with full memory
```

(Only reap once the result is accepted; `resume` is the safety net for when you
reaped too early. Prefer *not closing* over *closing and resuming*.)

## How each mechanism maps to herdr 0.8.2

- **spawn/tab** — `herdr tab create --cwd … --label … --no-focus [--workspace <ws>]`
  returns `.result.root_pane.pane_id` and `.result.tab.tab_id`; new tabs default
  to the driver's own workspace so they are sibling tabs you can click to. The
  agent comes up with `herdr agent start <id> --kind <harness> --pane <p> -- <profile args…>`.
  The agent **name is the task id** (unique) — herdr rejects a reused live name,
  so naming every crew after the harness would cap the fleet at one. `tab create`
  can return before the pane's shell is ready, so `agent start` is retried on the
  transient `agent_pane_busy`.
- **event-driven** — `rzr-watch.sh` subscribes to herdr's native
  `pane.agent_status_changed` push stream over the control socket (via
  `herdr-eventwait.py`). Every message is a real edge, so there is no polling and
  nothing to spin. Each edge is deduped against `state/<id>.status`; only real
  changes are printed and persisted.
- **send (DATA)** — `herdr agent prompt <pane> <text>` types and submits
  atomically, and is rejected up front if the agent is blocked.
- **control (CONTROL)** — `interrupt`/`cancel`/`key` drop to
  `herdr agent send-keys <pane> <key>` (esc / ctrl+c / any named key); `stop`
  reuses `rzr-teardown.sh`; `restart` composes teardown + `rzr-spawn.sh` under
  the same id. Every verb confirms its result with
  `herdr agent wait <pane> --until <states> --timeout <ms>` rather than trusting
  the send's exit code alone. `restart` deliberately passes `--force` to
  teardown's unlanded-work guard: teardown only drops the tab + state record,
  never the working tree, so restart re-spawns into the *same* cwd with any
  prior work still on disk — nothing is lost by skipping the guard here.
- **lock** — atomic `mkdir state/.lock`, holder pid recorded; a dead holder is
  reclaimed on the next acquire. `rzr-spawn.sh` holds it around the
  create-tab/write-meta mutation.

## Configuration (env)

- `ROZORO_HOME` / `RZR_HOME` — home (default `~/.rozoro`). Holds `state/` (task
  meta, status, locks) and `crew/` (presets). `ROZORO_HOME` wins; `RZR_HOME` is
  the legacy name.
- `RZR_WORKSPACE` — herdr workspace for new tabs (default `$HERDR_WORKSPACE_ID`).
- `RZR_SESSION` — herdr `--session` name (default: the single local server).

## Try it

```sh
# 1. spawn from $ROZORO_HOME/crew/default.json (if configured):
bin/rzr-spawn.sh t1 --cwd /some/repo --prompt 'List the files in this repo, then stop.'

# With no default.json, explicitly select the Codex low fallback:
bin/rzr-spawn.sh t2 --cwd /some/repo --harness codex --prompt 'Resolve issue #42.'

# 2. watch the fleet event-driven (blocks, prints on each real transition):
bin/rzr-watch.sh t1 t2
#    06:01:03  t1  working
#    06:01:07  t1  done

# 3. send a follow-up (DATA); --wait blocks until it settles:
bin/rzr-send.sh t1 'Now count the lines in README.' --wait

# 3b. …or interrupt a runaway turn (CONTROL) — executed, never read as chat:
bin/rzr-control.sh t1 interrupt

# 4. inspect presets / reap:
bin/rzr-crew.sh list
bin/rzr-teardown.sh t1
```

## Verified on herdr 0.8.2 (macOS)

- ✅ tab create + pane/tab id parsing, meta on disk; `agent start` with per-preset
  passthrough (`-- --model/--effort/--permission-mode/--append-system-prompt`)
- ✅ unique-name spawn → multiple live crew concurrently
- ✅ push-stream watcher: real `working`/`idle`/`done` edges, deduped, no flood,
  clean process teardown; concurrent multi-pane attribution
- ✅ `rzr-send.sh` (DATA) delivery and `--wait` settle
- ✅ `rzr-control.sh` (CONTROL) `interrupt`/`cancel`/`key`/`stop`/`restart`, each
  against a live throwaway task, each verifying its own postcondition
- ✅ presets: personal default.json wins; absent-file harness fallbacks resolve
- ✅ lock: live-holder refusal, stale-pid reclaim, release
- ✅ runs on stock bash 3.2 (no `declare -A` / `mapfile`)

Not verified here: `copilot` and `pi` harness launches — their flag mappings are
wired from known invocations but untested on this machine.
