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
3. **send to sessions** — submit a follow-up, or drop keys to interrupt
4. **lockfile** — single-driver safety around the spawn mutation

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
- **The intelligence is the driver's.** "Read the PRs, pick a model by
  complexity, assign, judge done" is the driver session using rozoro + `gh` as
  tools. rozoro is the hands.

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
answers, that `bin/` is on PATH, and seeds the default crew preset. Green means
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
| `rzr-link.sh <id> <cwd>` | capture `tasks/<id>/session.json` (`claude --resume <id>`) via marker-grep; idempotent |
| `rzr-status.sh <id>` | read the latest handoff `verdict` + whether a new block appeared (done vs needs-action; miss-detector) |
| `rzr-watch.sh [--once] [id…]` | subscribes to herdr's `pane.agent_status_changed` push stream; prints one line per real state change; zero polling |
| `rzr-send.sh <id> <text>` | `herdr agent prompt` (submit); also `--key <name>` / `--text <literal>` for interrupts and unsubmitted composition; `--wait` blocks until settled |
| `rzr-crew.sh list\|show <name>` | inspect crewmember presets (spawn profiles) |
| `rzr-lock.sh status\|acquire` | inspect/hold the home lock (atomic `mkdir`, stale-pid reclaim) |
| `rzr-list.sh` | known tasks + live agent state |
| `rzr-doctor.sh` | preflight: deps (`herdr`/`jq`/`python3`), herdr server reachable, `bin/` on PATH, default preset — exits non-zero on a missing hard dep |
| `rzr-teardown.sh <id>` | close the tab, remove the record (the `tasks/<id>/` folder survives) |

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

## Crewmember presets

A **preset** bundles *how* a crew agent is booted — harness, model, effort,
permission mode, and standing `rules` — never *what* its task is. Presets are one
JSON file per name under `$ROZORO_HOME/crew/<name>.json`:

```json
{
  "harness": "claude",
  "model": "sonnet",
  "permission_mode": "auto",
  "effort": "",
  "rules": ["Open a draft PR and stop; never push."]
}
```

- The built-in **`default`** (sonnet claude, `auto` permission, no rules) is
  written on first use and reproduces `claude --model sonnet --permission-mode auto`.
- Spawn from one with `rzr-spawn.sh <id> --crew <name> …`.
- **Precedence** for harness/model/effort/permission-mode: explicit flag > preset
  > default. `rules` come only from the preset.
- `rules` are **crew-behavioral** (e.g. "never push"), deliberately distinct from
  **repo** rules, which the agent auto-loads from `--cwd`.

**Harness mapping** (preset fields → the underlying binary's flags, via herdr's
`agent start … -- <arg>` passthrough):

| harness | maps to | notes |
|---|---|---|
| `claude` | `--model --effort --permission-mode --append-system-prompt` | verified on this machine |
| `codex`  | `--yolo --model <m>` | wired from the known invocation; not verified here |
| `copilot`| `--model <m> --mode autopilot --allow-all` | wired; not verified here |
| `pi`     | *(no flags)* | `pi` takes none; model/effort/rules ignored |

Only `claude` supports `effort` and `rules`; other harnesses warn and ignore
them. An unmapped harness fails loudly rather than launching with wrong flags.

## Instructing rozoro (the control tower)

The driver's whole vocabulary is small:

| Trigger | Call |
|---|---|
| **Start** a task | `rzr-start.sh <id> --body <file> --cwd <repo> [--crew <preset>] [--model opus]` |
| **Steer / interrupt** | `rzr-send.sh <id> "<text>"` · `rzr-send.sh <id> --key Escape` |
| **Stop** | `rzr-teardown.sh <id>` |
| *(sense, not trigger)* | `rzr-status.sh <id>` (handoff verdict) · `rzr-watch.sh` · `rzr-list.sh` · `rzr_status_get` (disk `state/<id>.status`) |

Put `bin/` on `PATH` (or drive it via the bundled skill) so the driver session
can reach these from anywhere. Read crew state from the on-disk
`state/<id>.status` (the watcher keeps it current) rather than blocking on
`rzr-watch`.

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
- **send** — `herdr agent prompt <pane> <text>` types and submits atomically, and
  is rejected up front if the agent is blocked. `--key` / `--text` drop to
  `pane send-keys` / `pane send-text`.
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
# 1. spawn a crew from the default preset (sonnet claude, auto permission):
bin/rzr-spawn.sh t1 --cwd /some/repo --prompt 'List the files in this repo, then stop.'

# …or override the model for a harder task:
bin/rzr-spawn.sh t2 --cwd /some/repo --model opus --prompt 'Resolve issue #42.'

# 2. watch the fleet event-driven (blocks, prints on each real transition):
bin/rzr-watch.sh t1 t2
#    06:01:03  t1  working
#    06:01:07  t1  done

# 3. send a follow-up; --wait blocks until it settles:
bin/rzr-send.sh t1 'Now count the lines in README.' --wait

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
- ✅ `rzr-send.sh --text` delivery and `--wait` settle
- ✅ presets: default reproduces sonnet+auto; `--model opus` override boots Opus
- ✅ lock: live-holder refusal, stale-pid reclaim, release
- ✅ runs on stock bash 3.2 (no `declare -A` / `mapfile`)

Not verified here: `codex` (not installed), `copilot`, `pi` harness launches —
their flag mappings are wired from known invocations but untested on this machine.
