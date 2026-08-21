---
name: rozoro
description: >-
  Delegate work to a fleet of agent sessions using the rozoro CLI over the herdr
  terminal backend. Use this when you are acting as a "control tower" / driver and
  the user wants you to spawn one or more agents (crew) to work tasks in parallel
  — e.g. "resolve these issues/PRs", "spin up an agent to do X in repo Y", "fan
  out this work", "boot a crew", "watch/steer/reap the crew". rozoro spawns and
  observes; it does NOT do repo-specific work itself.
---

# rozoro — driving a fleet of agent sessions

You are the **driver** (control tower). rozoro is your hands: a tiny CLI that
**spawns, watches, messages, and reaps** agent sessions as herdr tabs. Each task
is one tab → one pane → one agent ("crew member"). All state is on disk under
`$ROZORO_HOME` (default `~/.rozoro`), so nothing is lost if you restart.

## The one rule that shapes everything

**rozoro is a spawner, not a manager.** It knows nothing about worktrees, PR
resolution, delivery, or merge authority — those are **repo-specific** and belong
to the **crew agent**, which loads the target repo's own rules (`AGENTS.md`,
skills, `CLAUDE.md`) from its `--cwd`. So:

- **You** (the driver) read the issues/PRs, decide model by complexity, spawn
  crew, watch, and judge completion — using rozoro + `gh` as tools.
- **The crew** does the repo-specific work its own way, and may spawn its own
  harness-native subagents.
- **Task prompts are verbatim.** rozoro never edits what you tell a crew to do.

## Setup

The tools ship in their **own** repo's `bin/` (e.g. `~/proj/rozoro/bin`) — **not**
inside this skill folder. On a set-up machine that `bin/` is already on `$PATH`, so
you can call them by bare name; otherwise add it to `PATH` or call by absolute
path. Every command has two forms: the dispatcher `rozoro <verb>` (or short `rzr
<verb>`) and the underlying `rzr-<verb>.sh` script — `rozoro start …` ≡ `rzr-start.sh
…`. This doc uses the `rzr-*.sh` form; substitute the dispatcher freely. Still
requires `herdr` (running server, and you inside a herdr session), `jq`, and
`python3`. Run `rozoro doctor` to verify everything at once (deps, herdr server
reachable, `bin/` on PATH, default preset) — it seeds nothing you must pre-create,
since `$ROZORO_HOME` and its subdirs self-create on first use.

## Trigger vocabulary

| Intent | Command |
|---|---|
| **Start** a task (blessed) | `rzr-start.sh <id> --body <file> --cwd <repo> [rzr-spawn flags]` — renders a durable brief, spawns, and links the session in one unskippable step |
| **Start** (low-level) | `rzr-spawn.sh <id> --crew <preset> --cwd <repo> --prompt "<task>"` (or `--brief <file>`) — raw spawn; no task folder, no handoff protocol, no session link |
| **Steer / interrupt** | `rzr-send.sh <id> "<text>"` · `rzr-send.sh <id> --key Escape` |
| **Stop / reap** | `rzr-teardown.sh <id>` |
| **Read verdict** | `rzr-status.sh <id>` — latest handoff verdict + whether a NEW block appeared (the done-vs-needs-action signal; the miss-detector) |
| **Sense** (don't block) | `rzr-watch.sh --once <ids>` in a background task (push stream, wakes you on an edge) · `rzr-list.sh` to poll · read `state/<id>.status` (written BY rzr-watch) |

`<id>` is a short unique slug you choose (e.g. `issue-123`, `pr-88`). It names the
state files and the tab.

## Picking a crew (model by complexity)

Crew presets bundle *how* an agent boots (harness, model, permission mode, effort,
standing rules) — never the task. Inspect them with `rzr-crew.sh list`.

- Default preset = **sonnet claude, `auto` permission** (i.e.
  `claude --model sonnet --permission-mode auto`). Good for routine work.
- Harder task → override the model: `rzr-spawn.sh <id> --model opus --cwd … --prompt …`.
- Presets live at `$ROZORO_HOME/crew/<name>.json`; create new ones (e.g. a
  `senior` opus preset, or one whose `rules` say "open a draft PR, never push").
- `rules` in a preset are crew-behavioral and apply only to `claude` (appended to
  its system prompt). Repo-specific rules stay in the repo, not the preset.

Precedence: explicit flag > preset > default.

## How to run a batch (the loop)

1. Gather the work (e.g. `gh pr list`, `gh issue view NNN`) and decide, per task,
   a unique id, the repo `--cwd`, and the model/preset.
2. Write each task body to a file (the scratchpad or under `$ROZORO_HOME`) and
   `rzr-start.sh <id> --body <file> --cwd <repo> [--model opus]`. This renders a
   **durable brief** (with the handoff protocol) into `tasks/<id>/`, spawns the
   crew, and links its session — all verbatim, no shell escaping. Prefer this over
   raw `rzr-spawn.sh`, which skips the task folder, protocol, and session link.
3. **Do not sit in a poll loop.** Run `rzr-watch.sh --once <ids>` as a
   **background task** — it blocks on herdr's native `pane.agent_status_changed`
   PUSH stream at ~0% CPU and returns (waking you, the driver) only on a real
   edge; reconcile, then re-arm another `--once` if the crew is still live.
   `rzr-list.sh` polling is the fallback when no background waiter is available.
   `state/<id>.status` is **produced by** `rzr-watch` — it is not maintained by an
   always-on daemon, and the file is absent until a watcher has run. Either way,
   `done`/`idle` means the agent *ended a turn* — not that the task is correct or
   landed.
4. On each edge, run `rzr-status.sh <id>` — read the **handoff verdict**, not herdr's
   raw `done`: `done` → verify the result (pane, repo, `gh`) then reap;
   `needs-action` → answer via `rzr-send.sh`; a `[same]`/no-new-block on an idle edge
   means the crew ended a turn without reporting (e.g. backgrounded work) — nudge it.
5. Steer any crew that needs it with `rzr-send.sh`; the user can also click the tab
   and type directly. Also call `rzr-link.sh <id> <cwd>` here if the birth-time link
   was not yet captured (idempotent).
6. `rzr-teardown.sh <id>` when a task is finished and its result is captured. The
   `tasks/<id>/` folder (brief + handoff + session link) survives teardown, so
   nothing is lost — a follow-up crew rehydrates from it, or `claude --resume
   <session_id>` reopens the exact conversation as a last resort.

## Durable task folders & the handoff contract

`rzr-start` gives every task a folder under `$ROZORO_HOME/tasks/<id>/` — the durable
record that makes teardown non-lossy:

- `brief.md` — the INPUT, persisted predictably (rendered from `templates/brief.md`,
  which appends the handoff protocol and a unique `rozoro-task: <id>` marker).
- `handoff.md` — the OUTPUT, **append-only**. The protocol tells the crew to append
  a block before ending *every* turn, each carrying a `verdict:` line
  (`done | needs-action | failed | blocked`) and `inputs-needed:`. This is how you
  tell "done" from "needs more input", and it accumulates across multiple `rzr-send`
  rounds so context is never lost.
- `session.json` — the resume link (`claude --resume <session_id>`), captured by
  `rzr-link` via marker-grep (concurrency-safe, unlike "newest file" when crews share
  a `--cwd`).

The protocol is delivered *in the brief* (harness-neutral — no preset rules needed),
but a turn-1 instruction decays, so the reliability comes from the loop: detect the
miss with `rzr-status` (no new block on an idle edge) and nudge with `rzr-send`. The
folder lives in `$ROZORO_HOME` (data), never in this repo (code).

## Gotchas

- Spawning in a repo the crew hasn't trusted shows Claude Code's trust dialog;
  `rzr-spawn` reports the pane `blocked`. Accept it once with
  `rzr-send.sh <id> --key Enter`, then re-deliver the prompt.
- One live agent per unique name — always give each task a distinct `<id>`.
- Only `claude` is fully wired for model/effort/rules; `codex`/`copilot`/`pi` are
  mapped from known invocations but unverified. An unmapped harness fails loudly.
- Concurrent crew in the **same** checkout will clobber each other — worktree
  isolation is the *crew's* job (via repo rules), so prefer repos/tasks whose
  rules handle it, or spawn against separate checkouts.
- A crew can self-background its own long-running command (e.g. a `sleep`, a
  build) and **end its turn early** — the edge to `done` fires before the work
  is actually finished. The footer showing `1 shell`/`1 monitor` is the tell:
  read the pane and steer with `rzr-send.sh` to make it finish; don't assume
  `done` means complete.
