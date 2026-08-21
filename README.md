# firstmate-light

A deliberately tiny agent-session orchestrator over the [herdr](https://herdr.dev)
terminal backend. It is a stripped-down demonstrator of the four mechanics at the
core of firstmate, nothing more:

1. **spawn sessions as tabs**
2. **event-driven updates** (no polling)
3. **send to sessions**
4. **lockfile** (single-orchestrator safety)

Each **task** is one herdr **tab** holding one **pane** running one agent. All
state lives on disk under `state/`, so killing the orchestrator loses nothing —
the next command reconciles from `state/<id>.meta`.

This is a scratch harness for exploring the mechanism. It is NOT firstmate: no
worktrees, no delivery modes, no supervision policy, no merge authority. Grow
those in only if you decide to.

## Requirements

- `herdr` 0.8.x on `PATH`, with a running server, and you running **inside** a
  herdr session (so new tabs land in your workspace). Verify: `herdr tab list`.
- `jq`
- `bash` (the scripts are bash; your interactive shell can be anything)

## The tools (`bin/`)

| Command | Criterion | What it does |
|---|---|---|
| `fl-spawn.sh <id> [opts]` | 1 spawn as tab | `herdr tab create` → `herdr agent start` → optional first prompt; records `state/<id>.meta` |
| `fl-watch.sh [--once] [id…]` | 2 event-driven | blocks on herdr's native `agent wait`, prints one line per state change, re-arms; zero polling |
| `fl-send.sh <id> <text>` | 3 send | `herdr agent prompt` (submit); also `--key <name>` and `--text <literal>` |
| `fl-lock.sh status\|acquire` | 4 lockfile | inspect/hold the home lock (atomic `mkdir`, stale-pid reclaim) |
| `fl-list.sh` | — | known tasks + live agent state |
| `fl-teardown.sh <id>` | — | close the tab, remove the record |

`fl-lib.sh` is the shared library (paths, herdr invocation, meta, lock, status);
it is sourced, not run.

### How each mechanism maps to herdr 0.8.2

- **spawn/tab** — `herdr tab create --cwd … --label … --no-focus [--workspace <ws>]`
  returns `.result.root_pane.pane_id` and `.result.tab.tab_id`. New tabs default
  to the orchestrator's own workspace (`$HERDR_WORKSPACE_ID`) so they are sibling
  tabs you can click to. The agent is then brought up with
  `herdr agent start <kind> --kind <kind> --pane <id>`, which waits for interactive
  readiness.
- **event-driven** — `herdr agent wait <pane> --until <state>…` blocks until the
  pane's agent reaches one of the named states, pushed from herdr's control
  socket. `fl-watch.sh` arms it as an **edge detector**: "wait until state ≠
  current" (`--until` every state except the current one), so it never returns
  immediately and never busy-waits. On each event it prints and re-arms.
- **send** — `herdr agent prompt <pane> <text>` types and submits atomically, and
  is rejected up front if the agent is blocked. `--key` / `--text` drop to
  `pane send-keys` / `pane send-text` for interrupts and unsubmitted composition.
- **lock** — atomic `mkdir state/.lock`, holder pid recorded; a holder whose pid
  is dead is reclaimed on the next acquire so a crash never wedges the home.
  `fl-spawn.sh` holds it around the create-tab/write-meta mutation.

## Configuration (env)

- `FL_HOME` — orchestrator home (default: the repo root). State goes in `$FL_HOME/state`.
- `FL_WORKSPACE` — herdr workspace for new tabs (default: `$HERDR_WORKSPACE_ID`).
- `FL_SESSION` — herdr `--session` name (default: the single local server).

## Try it (acceptance walk-through)

Run from inside a herdr session. `export FL_HOME=$(pwd)` first.

**Plumbing only, no agent** (verifies spawn-tab + send + teardown mechanically):

```sh
export FL_HOME=$(pwd)
bin/fl-spawn.sh demo --no-agent           # a new tab labeled "demo" appears
bin/fl-list.sh                            # demo … shell …
bin/fl-send.sh demo --text 'echo hi'      # types into the tab (not submitted)
bin/fl-teardown.sh demo                   # closes the tab, clears state
```

**Full end-to-end with a real agent** (verifies the event-driven path):

```sh
export FL_HOME=$(pwd)
# 1. spawn a real agent in a tab, with a first task:
bin/fl-spawn.sh t1 --harness claude --cwd /some/repo \
  --prompt 'list the files in this repo, then stop'

# 2. in another shell, watch it event-driven (blocks, prints on each transition):
bin/fl-watch.sh t1
#    e.g.  05:40:01  t1  working
#          05:40:07  t1  idle       <- agent finished the turn

# 3. send a follow-up; --wait blocks until it settles again:
bin/fl-send.sh t1 'now count the lines in README' --wait

# 4. clean up:
bin/fl-teardown.sh t1
```

**Lock (criterion 4):**

```sh
bin/fl-lock.sh status                     # free
bin/fl-lock.sh acquire                    # hold it (Enter to release)
# ...in another shell while it's held:
bin/fl-lock.sh status                     # held by pid N since …
bin/fl-spawn.sh x --no-agent              # waits up to 30s, then refuses if still held
```

## Verified vs. not

Built and mechanically verified on herdr 0.8.2 (macOS):

- ✅ tab create + pane/tab id parsing, meta on disk
- ✅ `fl-send.sh --text` delivery into a pane
- ✅ `fl-list.sh` state (`shell` vs `gone`)
- ✅ `fl-teardown.sh` tab close
- ✅ lock: live-holder refusal, stale-pid reclaim, release

Left for the trying agent to exercise (needs a real agent, deliberately not run
here):

- ⏳ `herdr agent start <kind>` bringing up a real agent (arg shape assumed
  `<name> --kind <kind> --pane <id>`; confirm against `herdr agent start --help`)
- ⏳ `fl-watch.sh` transitions on a live agent (`working`↔`idle`/`done`/`blocked`)
- ⏳ `fl-send.sh … --wait` settle behavior

If `agent start` needs a different argument shape, that's the one line to adjust
in `bin/fl-spawn.sh` (the `fl_herdr agent start …` call).
