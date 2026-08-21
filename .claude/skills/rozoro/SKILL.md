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

The tools live in `rozoro/bin` (this repo). Either add it to `PATH` or call by
absolute path. Requires `herdr` (running server, and you inside a herdr session),
`jq`, and `python3`. Verify the backend with `herdr tab list`.

## Trigger vocabulary

| Intent | Command |
|---|---|
| **Start** a task | `fl-spawn.sh <id> --crew <preset> --cwd <repo> --prompt "<task>"` |
| **Steer / interrupt** | `fl-send.sh <id> "<text>"` · `fl-send.sh <id> --key Escape` |
| **Stop / reap** | `fl-teardown.sh <id>` |
| **Sense** (don't block) | read `state/<id>.status`, or `fl-list.sh`; `fl-watch.sh` for live edges |

`<id>` is a short unique slug you choose (e.g. `issue-123`, `pr-88`). It names the
state files and the tab.

## Picking a crew (model by complexity)

Crew presets bundle *how* an agent boots (harness, model, permission mode, effort,
standing rules) — never the task. Inspect them with `fl-crew.sh list`.

- Default preset = **sonnet claude, `auto` permission** (i.e.
  `claude --model sonnet --permission-mode auto`). Good for routine work.
- Harder task → override the model: `fl-spawn.sh <id> --model opus --cwd … --prompt …`.
- Presets live at `$ROZORO_HOME/crew/<name>.json`; create new ones (e.g. a
  `senior` opus preset, or one whose `rules` say "open a draft PR, never push").
- `rules` in a preset are crew-behavioral and apply only to `claude` (appended to
  its system prompt). Repo-specific rules stay in the repo, not the preset.

Precedence: explicit flag > preset > default.

## How to run a batch (the loop)

1. Gather the work (e.g. `gh pr list`, `gh issue view NNN`) and decide, per task,
   a unique id, the repo `--cwd`, and the model/preset.
2. `fl-spawn.sh` each task with a **verbatim, self-contained** prompt, e.g.
   `--prompt "Resolve issue #123."` The crew will follow that repo's own rules.
3. **Do not block.** Poll `state/<id>.status` (the watcher keeps it current) or
   run `fl-watch.sh <ids…>` in a background pane. `done`/`idle` means the agent
   *ended a turn* — not that the task is correct or landed; inspect the result
   (the pane, the repo, `gh`) before declaring success.
4. Steer any crew that needs it with `fl-send.sh`; the user can also click the tab
   and type directly.
5. `fl-teardown.sh <id>` when a task is finished and its result is captured.

## Gotchas

- Spawning in a repo the crew hasn't trusted shows Claude Code's trust dialog;
  `fl-spawn` reports the pane `blocked`. Accept it once with
  `fl-send.sh <id> --key Enter`, then re-deliver the prompt.
- One live agent per unique name — always give each task a distinct `<id>`.
- Only `claude` is fully wired for model/effort/rules; `codex`/`copilot`/`pi` are
  mapped from known invocations but unverified. An unmapped harness fails loudly.
- Concurrent crew in the **same** checkout will clobber each other — worktree
  isolation is the *crew's* job (via repo rules), so prefer repos/tasks whose
  rules handle it, or spawn against separate checkouts.
