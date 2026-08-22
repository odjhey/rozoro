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
- `jq` on `PATH`
- `python3` on `PATH` (stdlib only) — for the event-stream watcher
- `bash` — runs on stock macOS `/bin/bash` 3.2 (no bash-4 features)
- The selected coding harness (`claude`, `codex`, `copilot`, or `pi`) on `PATH`

## Automated tests

The regression suite is isolated from your real home, Rozoro state, Herdr
session, harness stores, and working checkouts. It uses a PATH-injected fake
Herdr and standard-library Unix socket fixtures, so neither a running Herdr
server nor an installed coding harness is needed.

Install Podman or Docker, then run the same command used by CI:

```sh
./tests/run.sh
```

The runner prefers Podman when both engines are available and falls back to
Docker. Set `CONTAINER_ENGINE=docker` (or an executable path) to select one
explicitly. It builds a small cached test image from the official Bats 1.14.0
image pinned by digest, copying `jq` and Python from separately pinned images.
The first run pulls those immutable images; later builds reuse the container
engine's cache. Tests run without network access against a read-only checkout,
using only a temporary writable filesystem inside the disposable container. No
host Bats, `jq`, or Python installation is required. CI runs the full suite this
way on Linux and keeps a stock macOS Bash 3.2 syntax check.

The automated suite covers shell/Python protocol parsing, event transport,
watch reconciliation, lifecycle glue, and locking. Checks against a real Herdr
0.8.x server remain optional manual integration smoke tests; they are not part
of the automated correctness evidence.

## Install

There is nothing to build and no dir to create — `$ROZORO_HOME` (default
`~/.rozoro`) and its `state/`, `crew/`, `tasks/` subdirs are created lazily on
first use. To set up a machine:

```sh
git clone git@github.com:odjhey/rozoro.git
cd rozoro
./bin/rozoro doctor                     # verify external deps, server, preset
```

`./bin/rozoro doctor` is the preflight — it checks the external binaries, that
the herdr server answers, and the resolved default harness. Green means you can
`./bin/rozoro start` a task.

Run commands from this checkout through the local dispatcher:
`./bin/rozoro <verb>`. The underlying `rzr-<verb>.sh` scripts remain internal
entry points, but setup and control-tower workflows do not require Rozoro's own
`bin/` directory on `PATH`.

## The tools (`bin/`)

| Command | What it does |
|---|---|
| `./bin/rozoro <verb> [args]` | checkout-local dispatcher; `./bin/rozoro help` lists verbs |
| `./bin/rozoro start <display-name> --body <file> --cwd <repo> [opts]` | blessed start: atomically reserve a unique task key → render → spawn → link; prints the key used by every later command |
| `./bin/rozoro spawn <id> --cwd <repo> [opts]` | low-level `herdr tab create` → `agent start` (from a crew preset) → optional verbatim first prompt; records `state/<id>.meta` |
| `./bin/rozoro render <id> <body>` | render `tasks/<id>/brief.md` from `templates/brief.md` (handoff protocol + `rozoro-task:` marker); prints its path |
| `./bin/rozoro link <id> <cwd> [--refresh]` | capture `tasks/<id>/session.json` for Claude, Codex, Copilot, or Pi; Copilot and Pi use preallocated native session UUIDs; idempotent unless `--refresh` replaces the link after restart |
| `./bin/rozoro status <id>` | pure schema-v2 projection separating persisted runtime, foreground, background, task, turn-report, and action state; unresolved items remain until explicitly acked |
| `./bin/rozoro ack <id> [--through n]` | mark a task's surfaced OPEN items resolved (advances a read cursor; never edits the append-only handoff) |
| `./bin/rozoro register --harness <h>` | pin this watchtower's ONE validated wake target (`watchtowers/<driver-id>/target.json`); validates the declared harness against live herdr state so a stale inherited env var can't wake the wrong session. For a Claude watchtower, run this by hand as `!./bin/rozoro register --harness claude` at your first idle prompt (see `templates/watchtower.md`) — herdr only reports `interactive_ready` once Claude reaches idle, so this is the one documented registration path, not a fallback. `ROZORO_ROLE=watchtower` marks session identity independently of registration |
| `./bin/rozoro watch [--once] [--wake\|--wake-codex\|--wake-herdr] [id…]` | subscribes to herdr's `pane.agent_status_changed` push stream; prints one line per real state change; `--wake` delivers a fixed nudge through the REGISTERED backend via a durable at-least-once ledger (bursts coalesce; the Herdr backend defers while the driver is working/blocked). `--wake-codex`/`--wake-herdr` force an explicit backend |
| `./bin/rozoro reconcile [--driver <id>]` | process the driver's pending wake ledger: report affected tasks' v2 projections, flag vanished tasks, and ack exactly the snapshotted generation (never resolves OPEN items) |
| `./bin/rozoro send <id> <text>` | **DATA plane only**: `herdr agent prompt` (submit) — text the agent reads and reasons about; `--wait` blocks until settled |
| `./bin/rozoro control <id> <verb>` | **CONTROL plane only**: a closed, EXECUTED verb list — `interrupt` \| `cancel` \| `key <name>` \| `stop` \| `restart` — never text the agent might interpret as chat; fails closed on an unresolved target and verifies its own postcondition (`herdr agent wait`) |
| `./bin/rozoro resume <id> [--prompt <t>]` | reopen a reaped Claude, Codex, Copilot, or Pi task's *exact* conversation as a fresh tab (from `tasks/<id>/session.json`); optionally deliver a follow-up. Refuses if the task is still live (use `./bin/rozoro send`) |
| `./bin/rozoro crew list\|show <name>` | inspect crewmember presets (spawn profiles) |
| `./bin/rozoro lock status\|acquire` | inspect/hold the home lock (atomic `mkdir`, stale-pid reclaim) |
| `./bin/rozoro list` | known tasks + live agent state |
| `./bin/rozoro doctor` | preflight: external deps (`herdr`/`jq`/`python3` and the selected harness), herdr server reachable, default preset — exits non-zero on a missing hard dep |
| `./bin/rozoro teardown <id> [--force]` | close the tab, remove the record (the `tasks/<id>/` folder survives); refuses if the recorded `cwd` has unlanded work (uncommitted/untracked changes, unpushed commits) unless `--force` |

`rzr-lib.sh` is the shared library (paths, herdr invocation, meta, status,
presets, lock); it is sourced, not run. `herdr-eventwait.py` is the raw-socket
subscriber `rzr-watch.sh` drives. `templates/brief.md` is the handoff-protocol seed
`rzr-render` fills in.

### Durable task folders

`./bin/rozoro start` treats its first argument as a concise display name and generates a
time-sortable, globally collision-safe key such as
`test-foundation--01K3A7Y8M4N2ABCDEFGHJKMNPQ`. It prints that key at startup;
use the exact key for `send`, `status`, `ack`, `control`, `resume`, and
`teardown`. The display name remains the tab label. Names may contain letters,
digits, `.`, `_`, and `-` (maximum 80 characters);
path separators and traversal components are rejected.

The key is reserved with an atomic directory creation before any brief or
handoff file is rendered. Repeated names, concurrent starts, and starts from
different repositories therefore always receive different folders. Repository
context is recorded in `identity.json` for discovery, but is not the uniqueness
boundary. Because Herdr agent names have a stricter 32-character lowercase
syntax, `identity.json` also records a separate collision-safe transport name.
The durable task key remains the lifecycle address and the display name remains
the tab label; fresh spawn and resume reuse the transport name internally.

Each task has a folder under `$ROZORO_HOME/tasks/<task-key>/` so teardown is
non-lossy: `brief.md` (the input), `handoff.md` (append-only output — each turn the
crew appends a `verdict:` block, so `done` is distinguishable from `needs-action`
and context accumulates across `./bin/rozoro send` rounds), and `session.json` (the resume
link). It is **data** — it lives in `$ROZORO_HOME`, never in this repo.

Compatibility: existing safe, unsuffixed keys such as `issue-42` remain valid
exact addresses. All lifecycle commands, including `resume`, continue to read
their existing `tasks/issue-42/` and `state/issue-42.meta` records without
migration or rewriting. Only new `./bin/rozoro start` calls allocate suffixed keys.

That covers the task *record*; teardown separately guards the crew's actual
work: it refuses to close a task whose recorded `cwd` has uncommitted,
untracked, or unpushed changes, so a crew's real output is never discarded
silently (`--force` overrides).

## Crewmember presets

A **preset** bundles *how* a crew agent is booted — harness, model, effort,
fast service tier, permission mode, and standing `rules` — never *what* its task is. Presets are one
JSON file per name under `$ROZORO_HOME/crew/<name>.json`. For example, the
personal `$ROZORO_HOME/crew/default.json` can select gpt-5.6-sol/high:

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

- `$ROZORO_HOME/crew/default.json` is authoritative when present. Rozoro never
  creates, migrates, or rewrites it. For safety against stale personal presets,
  Codex is the one launch-time exception: its effective permission mode is
  always normalized to `yolo`.
- If that file is absent, the hardcoded fallback is Claude/Sonnet/`auto`.
  Passing `--harness codex` selects gpt-5.6-sol/`low`; `--harness copilot` selects portable `auto` with no explicit effort. Codex and Copilot always use normalized `yolo` permission. Codex always passes
  `--yolo`.
- Spawn from one with `./bin/rozoro spawn <id> --cwd <repo> --crew <name> …`.
- **Precedence** for harness/model/effort/fast/permission-mode: explicit flag > preset
  file > hardcoded harness fallback. Codex permission mode is the exception: the
  spawner always uses `yolo`. `rules` come only from the preset file.
- `rules` are **crew-behavioral** (e.g. "never push"), deliberately distinct from
  **repo** rules, which the agent auto-loads from `--cwd`.

**Harness mapping** (preset fields → the underlying binary's flags, via herdr's
`agent start … -- <arg>` passthrough):

| harness | maps to | notes |
|---|---|---|
| `claude` | `--model --effort --permission-mode --append-system-prompt-file` | verified on this machine |
| `codex`  | `--yolo --model <m> --config model_reasoning_effort=<e> [--config service_tier=priority]` | `--yolo` is unconditional; `fast:true` selects the gpt-5.6-sol priority tier |
| `copilot`| `--no-auto-update --autopilot --yolo --no-ask-user --model <m> [--effort <e>] --session-id <uuid>` | capability-checked; fresh UUID is preallocated; exact resume uses `--resume=<uuid>` |
| `pi`     | `--model <m> --thinking <e> --approve --append-system-prompt <file> --session-id <uuid>` | project trust is approved when permission mode is non-empty; native UUID enables exact linking/resume |

Claude, Codex, Copilot, and Pi support `effort` (Pi names it `thinking`). Claude and Pi
receive the handoff protocol and preset `rules` through dedicated system-prompt
channels, leaving the task prompt verbatim. Harnesses without one receive the
protocol and rules in the delivered prompt. An unmapped harness fails loudly
rather than launching with wrong flags.

`fast` is separate from reasoning effort: `high` controls how much reasoning the
model uses, while `fast:true` requests Codex's `priority` service tier (higher
speed and increased usage). Stage 1 supports this only for Codex with
`gpt-5.6-sol`; other harness/model combinations fail before a tab is created.
Use `--fast` or `--no-fast` to override a preset for spawn and resume. The
resolved profile is stored in `session.json`, so restart and exact resume reapply
the model, effort, and service tier instead of depending on user defaults.

## Instructing rozoro (the control tower)

The driver's whole vocabulary is small:

| Trigger | Call |
|---|---|
| **Start** a task | `./bin/rozoro start <display-name> --body <file> --cwd <repo> [--crew <preset>] [--model <model>] [--fast]` (prints the immutable task key) |
| **Steer** (DATA — text the agent reads) | `./bin/rozoro send <id> "<text>"` |
| **Interrupt / cancel / key / restart** (CONTROL — executed, never read) | `./bin/rozoro control <id> interrupt` · `./bin/rozoro control <id> cancel` · `./bin/rozoro control <id> key <name>` · `./bin/rozoro control <id> restart` |
| **Resume** a reaped task | `./bin/rozoro resume <id> [--effort <e>] [--fast|--no-fast] [--prompt "<follow-up>"]` |
| **Stop** | `./bin/rozoro teardown <id>` (≡ `./bin/rozoro control <id> stop`; refuses on unlanded work in the crew's `cwd`, `--force` to discard anyway) |
| *(sense, not trigger)* | `./bin/rozoro status <id>` (handoff verdict) · `./bin/rozoro watch` · `./bin/rozoro list` · `rzr_status_get` (disk `state/<id>.status`) |

**DATA vs CONTROL, and why it's split.** A crew must receive two clearly
distinct kinds of message, never conflated: DATA is free text the agent reads
and reasons about (`./bin/rozoro send`); CONTROL is a lifecycle action from a closed
verb list that the harness *executes* (`./bin/rozoro control`) — never text the agent
might interpret as chat. The failure this prevents: a lifecycle command
arriving as chat the agent "reads" instead of the harness carrying out. Control
verbs also fail closed on target resolution (an unresolved task/pane is refused
loudly, never guessed at) and verify their own postcondition rather than
trusting a herdr call's exit code alone.

Keep the driver in the Rozoro checkout and call `./bin/rozoro`; point each fresh
task at its own repository with `--cwd`. Read crew state from the on-disk
`state/<id>.status` (the watcher keeps it current) rather than blocking on
`./bin/rozoro watch`.

### Launching the driver

The driver is just a capable agent session with the rozoro skill in reach and a
system prompt that keeps it in the control tower. That prompt is versioned in this
repo at [`templates/watchtower.md`](templates/watchtower.md) — maintain it there,
not inline. Launch the driver **inside a herdr session** from this Rozoro checkout,
where the bundled skill and checkout-local dispatcher remain available:

From the Rozoro checkout:

```sh
# Pi watchtower (recommended)
pi \
  --approve \
  --append-system-prompt "$PWD/templates/watchtower.md"

# Or Claude
ROZORO_ROLE=watchtower claude \
  --append-system-prompt-file "$PWD/templates/watchtower.md"
```

`ROZORO_ROLE=watchtower` marks this Claude session's identity as a
watchtower, distinct from a rozoro-spawned crew or a plain dev session opened
in the same checkout. Nothing reads it yet, but it's reserved for
watchtower-scoped tooling, such as the planned long-lived monitor daemon
(#25). A Claude watchtower still registers its wake target by hand at its
first idle prompt (`!./bin/rozoro register --harness claude`, see the
`./bin/rozoro register` row below and `templates/watchtower.md`) — there is no
automatic registration to opt into.

Running plain `pi` opens a normal coding session, not a watchtower. The watchtower
command supplies the control-tower prompt and approves the project-local
extension for this run; the driver calls the dispatcher from the checkout.

The Pi launch also loads [`.pi/extensions/rozoro-watchtower.ts`](.pi/extensions/rozoro-watchtower.ts).
When it detects the watchtower system prompt, the extension starts the repo-local watcher
as an owned asynchronous child, keeps the editor responsive, and injects a
`[rozoro event]` message on actionable crew edges. This is deliberately different
from calling `./bin/rozoro watch` through Pi's foreground bash tool, which would occupy the
agent turn and queue operator messages. Use `/rozoro-monitor status|on|off` to
inspect or control the monitor.

Editing `templates/watchtower.md` and committing it is how you evolve the driver's
standing behavior; every watchtower booted from the file inherits the change. Keep
it short — the rozoro skill carries the detailed loop. The one idea it must anchor
is the boundary: **the driver spawns and judges; the crew does the domain work.**
(rozoro-the-tool is the dumb spawner; the driver is the judgment.)

## Examples

The blessed flow is `./bin/rozoro start` (durable brief + spawn + session link in
one step); reach for raw `./bin/rozoro spawn` only for throwaway probes.

**Fan out several issues in parallel** — one id + body per task, dispatched
eagerly, then one event-driven watcher over the fleet:

```sh
for n in 42 57 61; do
  printf 'Resolve issue #%s in this repo — investigate, fix, and open a PR.\n' "$n" \
    > /tmp/task-$n.md
  ./bin/rozoro start issue-$n --body /tmp/task-$n.md --cwd ~/proj/acme
done
./bin/rozoro watch issue-42 issue-57 issue-61  # streams each real edge; no polling
```

On each edge, read the **handoff verdict** — not herdr's raw `done` — then reap:

```sh
./bin/rozoro status issue-42        # done → verify the result, then reap
./bin/rozoro teardown issue-42      #   (tasks/issue-42/ survives teardown)
```

**Steer a live crew (DATA)** — a follow-up is submitted as text the agent reads:

```sh
./bin/rozoro send issue-57 "Skip the refactor — smallest fix that closes the issue."
```

**Interrupt a runaway turn (CONTROL)** — executed, never handed to the agent as
chat; verifies the agent actually left `working` before reporting success:

```sh
./bin/rozoro control issue-57 interrupt
```

**Dispatch a scout (investigation only, no PR)** — knowledge, not a change:

```sh
printf 'Investigate why CI flakes on the auth suite. Write findings; change no code.\n' \
  > /tmp/scout.md
./bin/rozoro start scout-ci-flake --body /tmp/scout.md --cwd ~/proj/acme
```

**Override the crew when you explicitly want a bigger model:**

```sh
./bin/rozoro start issue-99 --body /tmp/task-99.md --cwd ~/proj/acme --model opus
```

**Use a custom preset** — e.g. a "draft PR, never push" crew, defined once under
`$ROZORO_HOME/crew/`, then reused:

```sh
./bin/rozoro crew list                            # see available presets
./bin/rozoro start issue-77 --body /tmp/t.md --cwd ~/proj/acme --crew draft-only
```

**Follow up after `done` without losing context.** `done` is an invitation to
review, not a signal to reap — a done crew sits idle at ~0 cost. If it's still
live, just continue it (same agent, full context):

```sh
./bin/rozoro send issue-42 "Reviewed — also handle the null-token case, then re-push."
```

**Resume a task you already reaped** — if it was torn down before your follow-up
arrived, reopen the *exact* conversation (not a cold re-spawn) and hand it the
feedback in one step:

```sh
./bin/rozoro resume issue-42 --prompt "Also handle the null-token case, then re-push."
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
  nothing to spin. Each edge is deduped against this watch process's last-seen
  state; only real changes are printed and persisted. Buffered stdout from a
  background watcher cannot wake a driver after its turn has completed, so a wake
  option adds a fixed, content-free reconciliation nudge on settled (`idle`,
  `done`, `blocked`) edges. `--wake` delivers through the watchtower's REGISTERED
  target (see `./bin/rozoro register`): the backend is chosen by the validated
  registration, never by env-var priority, so a Claude/Pi process that inherited a
  stale `CODEX_THREAD_ID` can't wake the wrong conversation. Codex uses its native
  `codex queue`; Claude, Copilot, and Pi are prompted through the resident Herdr pane, and
  that path DEFERS while the driver is `working` and retains while `blocked` rather
  than injecting into its turn. `--wake-codex`/`--wake-herdr` force one backend.
  Every wake routes through a durable per-driver ledger: the actionable generation
  is persisted BEFORE the backend call, a burst of edges coalesces to one
  outstanding nudge (deliver iff `generation > ack` and `delivered <= ack`), and
  `./bin/rozoro reconcile` acks exactly the generation it processed — so delivery is
  at-least-once and a crash never loses an actionable edge. Initial reconciliation
  and `working` edges never wake the driver, and no handoff or event contents are
  ever queued.
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
- `RZR_HANDOFF_DELAY_MS` — bounded retry delay (default `200`) the watcher sleeps
  once before re-reading the handoff when a foreground settle event races its
  append; `0` disables the retry.

## Try it

```sh
# 1. spawn from $ROZORO_HOME/crew/default.json (if configured):
./bin/rozoro spawn t1 --cwd /some/repo --prompt 'List the files in this repo, then stop.'

# With no default.json, explicitly select the Codex low fallback:
./bin/rozoro spawn t2 --cwd /some/repo --harness codex --prompt 'Resolve issue #42.'

# Pi gets the same model/effort/rules/session lifecycle support as Claude:
./bin/rozoro spawn t3 --cwd /some/repo --harness pi --model openai-codex/gpt-5.6-sol --effort low --prompt 'Resolve issue #43.'

# 2. watch the fleet event-driven (blocks, prints on each real transition):
./bin/rozoro watch t1 t2
#    06:01:03  t1  working
#    06:01:07  t1  done

# From a resident watchtower, register the validated wake target once, then wake:
./bin/rozoro register --harness pi        # validates this pane/thread, pins target.json
./bin/rozoro watch --once --wake t1 t2 &  # durable ledger; backend from the registration
# On the nudge, the driver reconciles and acks the generation it processed:
./bin/rozoro reconcile

# 3. send a follow-up (DATA); --wait blocks until it settles:
./bin/rozoro send t1 'Now count the lines in README.' --wait

# 3b. …or interrupt a runaway turn (CONTROL) — executed, never read as chat:
./bin/rozoro control t1 interrupt

# 4. inspect presets / reap:
./bin/rozoro crew list
./bin/rozoro teardown t1
```

## Verified on herdr 0.8.2 (macOS)

- ✅ tab create + pane/tab id parsing, meta on disk; `agent start` with per-preset
  harness-specific model/effort/permission/system-prompt passthrough
- ✅ unique-name spawn → multiple live crew concurrently
- ✅ push-stream watcher: real `working`/`idle`/`done` edges, deduped, no flood,
  clean process teardown; concurrent multi-pane attribution
- ✅ `rzr-send.sh` (DATA) delivery and `--wait` settle
- ✅ `rzr-control.sh` (CONTROL) `interrupt`/`cancel`/`key`/`stop`/`restart`, each
  against a live throwaway task, each verifying its own postcondition
- ✅ presets: personal default.json wins; absent-file harness fallbacks resolve
- ✅ Pi with gpt-5.6-sol/low: model/thinking/trust/system-prompt passthrough,
  native session linking, teardown, exact resume, and continued handoff context
- ✅ Pi watchtower monitor: Herdr push subscription runs outside tool execution,
  preserving interactive operator input while actionable edges trigger a turn
- ✅ lock: live-holder refusal, stale-pid reclaim, release
- ✅ runs on stock bash 3.2 (no `declare -A` / `mapfile`)

Copilot CLI 1.0.80 with Herdr 0.8.2 was live-verified for launch, prompt, interrupt, and exact resume. Run the opt-in, cost-incurring smoke with `RZR_LIVE_COPILOT=1 tests/live/copilot-lifecycle.sh`. Copilot model availability is account-specific: persisted model metadata is the requested profile, and Copilot may warn and route an unavailable named model through `auto`.

### Status v2 and background-work boundary

`rozoro status` is read-only: it never contacts Herdr and never writes any
cursor (the old `.seen-blocks` miss-detector it used to advance is gone). The
watcher owns `state/<id>.runtime.json`, while the append-only handoff and
`.acked-blocks-v2` own task reporting and FIFO acknowledgement.
`runtime_status`, `foreground_status`, `background_activity`, `task_status`, and
`turn_report_status` are independent axes; `done` is a runtime/crew assertion,
not user acceptance.

A crew may report `verdict: waiting` only with useful reason/pending text and no
requested input. **Herdr 0.8.2 does not expose normalized background jobs**, so
this Stage 1 release reports background support/count as unknown and treats every
waiting report as `inconsistent-wait` (actionable). It does not inspect terminal
text or Claude footers. Certified wait suppression and final-job wake are Stage
2, gated on a Herdr release providing harness-neutral capability discovery,
synchronized active counts/opaque job IDs, ordered revisions and final-zero
success/failure/cancellation events. Acceptance and timeouts remain driver/user
policy.
