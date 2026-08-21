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

### Terminology: "crew" vs "subagent"

Keep these distinct — they are not synonyms:

- **crew / crew member / crew agent** — a *rozoro-spawned* agent session: one herdr
  tab/pane that you `start`, `watch`, `send` to, and `teardown`. Spawning several
  rozoro sessions is **"spawning crew"**, never "spawning subagents".
- **subagent** — ALWAYS the *harness-native* subagent a crew spawns **inside its
  own session** (e.g. Claude Code's Task/Agent tool). It is the crew's own tool,
  lives in the crew's context, and is invisible to rozoro — rozoro neither spawns,
  sees, nor reaps it.

So when you or the user say "subagent" (e.g. "have the crew spawn a subagent to
inspect X"), it means the crew uses its native Task/Agent tool — **not** that you
start another rozoro crew member. If a rozoro session is wanted, the word is
"crew".

## The one rule that shapes everything

**rozoro is a spawner, not a manager.** It knows nothing about worktrees, PR
resolution, delivery, or merge authority — those are **repo-specific** and belong
to the **crew agent**, which loads the target repo's own rules (`AGENTS.md`,
skills, `CLAUDE.md`) from its `--cwd`. So:

- **You** (the driver) identify the work, spawn crew, watch, and judge
  completion — using rozoro + `gh` as tools. Route **eagerly**: gather only
  enough to pick an id and a `--cwd`, then spawn on the **default crew** — *not*
  enough to pre-solve the task. Don't grade the task and hand-pick a model; that's
  its own upfront investigation. Use the default unless the user explicitly asked
  for a specific crew/model. Naming the issue and its repo is dispatch;
  reading every comment and reproducing the bug is not your job.
- **The crew** does the repo-specific work its own way — **including the
  investigation** — and may spawn its own harness-native subagents. Trust it to
  dig. A thin brief that points at the work beats a fat one you assembled by hand:
  the crew reads faster in-context than you can relay, and a dossier you pre-chew
  goes stale the moment the crew opens the repo.
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
| **Resume** a reaped task | `rzr-resume.sh <id> [--prompt "<follow-up>"]` — reopens the *exact* conversation (via `claude --resume`) as a fresh tab; for a task torn down before a follow-up arrived. If the crew is still live, use **send**, not resume |
| **Stop / reap** | `rzr-teardown.sh <id>` |
| **Read verdict** | `rzr-status.sh <id>` — latest handoff verdict + whether a NEW block appeared (miss-detector) **and any unresolved OPEN items** — every block with a `needs-action`/`blocked`/`failed` verdict or a set `inputs-needed` keeps surfacing until acked, so a later `done` can't bury an earlier open question |
| **Resolve open items** | `rzr-ack.sh <id> [--through <n>]` — after you've handled the open items status surfaced, ack them so status stops resurfacing them (advances a cursor; never edits the append-only handoff) |
| **Sense** (don't block) | `rzr-watch.sh --once <ids>` in a background task (push stream, wakes you on an edge) · `rzr-list.sh` to poll · read `state/<id>.status` (written BY rzr-watch) |

`<id>` is a short unique slug you choose (e.g. `issue-123`, `pr-88`). It names the
state files and the tab.

## Picking a crew

**Default to the default preset.** Don't grade tasks by complexity to pick a
model — that's an upfront investigation, and the crew is capable on the default.
Only override when the **user explicitly** asks for a specific crew/model (or has
a standing preference). Inspect presets with `rzr-crew.sh list`.

Crew presets bundle *how* an agent boots (harness, model, permission mode, effort,
standing rules) — never the task.

- Default preset = **sonnet claude, `auto` permission** (i.e.
  `claude --model sonnet --permission-mode auto`). This is the right choice for
  routine *and* hard work unless told otherwise.
- User asked for a bigger model → override: `rzr-spawn.sh <id> --model opus --cwd … --prompt …`.
- Presets live at `$ROZORO_HOME/crew/<name>.json`; create new ones (e.g. a
  `senior` opus preset, or one whose `rules` say "open a draft PR, never push").
- `rules` in a preset are crew-behavioral and apply only to `claude` (appended to
  its system prompt). Repo-specific rules stay in the repo, not the preset.

Precedence: explicit flag > preset > default.

## Intake: decide policy, delegate discovery

Before you spawn, resolve only what the crew **cannot** discover for itself, and
declare everything else its job. The upfront decisions are small and finite:

- **the id** — a short unique slug per task,
- **the `--cwd`** — which repo/checkout the crew works in,
- **the task shape** (ship vs scout, below), and
- any **posture the crew can't infer** — a merge/delivery rule, a "don't touch X",
  a required approach. State these; they're the constraints, not the content.

Everything past that line — reading the issue, reproducing the bug, reading the
code, weighing approaches — is **discovery**, and discovery belongs to the crew.
Don't pre-solve to build a brief. Deciding policy is your job; digging is theirs.

### Two task shapes: ship (default) and scout

- **Ship** is the default. It produces a change (fix, feature, PR — however the
  repo delivers). **Keep the investigation *inside* the ship task.** Bounded
  research — repro, root-cause, reading the code — is the crew's first move, not
  something you do upfront and hand over. Only pull research out into its own task
  when unresolved uncertainty could materially change *whether or what* to build.
- **Scout** produces *knowledge*, not a change — a written finding/report, no PR.
  Dispatch a scout **only** when the user explicitly asks for a standalone
  investigation/plan/audit, or when that could-change-what-to-build uncertainty
  is real. Don't reflexively scout before every ship; that's the pre-gathering
  habit wearing a different hat. And never both hand over a good-enough answer
  *and* launch a parallel scout that isn't expected to change it.

### Reuse-check before you scout

A scout is expensive and often redundant. Before dispatching one, check whether
the answer already exists: prior `tasks/<id>/handoff.md` blocks, existing reports
or notes in the target repo, an earlier scout's output, or established evidence
you already have. If it's already answered, relay it — don't re-run the
investigation. This is the *one* cheap thing worth gathering upfront: not the
answer itself, but whether the answer already exists.

## How to run a batch (the loop)

1. Identify the work (e.g. `gh pr list`/`gh issue list` for the *set* of ids) and
   run **Intake** (above) per task: id, `--cwd`, task shape (ship/scout), and any
   posture the crew can't infer. Leave the crew on the default preset unless the
   user named a model. Stop there — you don't need `gh issue view NNN` digested
   into the brief. The moment you can name a task and point at it, dispatch; let
   the crew do the reading. Reach for deeper `gh` inspection only when you
   genuinely can't route without it (e.g. which repo an issue belongs to, or
   splitting one id into several) — or for the reuse-check before a scout.
2. Write each task body to a file (the scratchpad or under `$ROZORO_HOME`) and
   `rzr-start.sh <id> --body <file> --cwd <repo>` (add `--model opus` only if the
   user asked for it). This renders a
   **durable brief** (with the handoff protocol) into `tasks/<id>/`, spawns the
   crew, and links its session — all verbatim, no shell escaping. Prefer this over
   raw `rzr-spawn.sh`, which skips the task folder, protocol, and session link.
   Keep the body **intent + pointer**, not a dossier: what outcome you want and
   where to look (`issue #NNN`, a PR, a path) — the crew investigates from there.
   Front-load only the constraints the crew *can't* discover on its own (a merge
   rule, a "don't touch X", a preferred approach). If you catch yourself pasting
   issue comments or repro steps into the brief, you're doing the crew's job.
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
   raw `done`: `done` → verify the result (pane, repo, `gh`); `needs-action` →
   answer via `rzr-send.sh`; a `[same]`/no-new-block on an idle edge means the crew
   ended a turn without reporting (e.g. backgrounded work) — nudge it. Status also
   prints any **unresolved OPEN items** (an earlier `needs-action`/`blocked`/`failed`
   or an unanswered `inputs-needed`): a `done` verdict with an OPEN list means the
   crew finished *this* turn but an earlier question is still hanging — handle it,
   then `rzr-ack.sh <id>` so it stops resurfacing. **`done` is an invitation to
   review, not a signal to reap** — a done crew sits idle at ~0 cost, so leave it
   alive (see step 6).
5. Steer any crew that needs it with `rzr-send.sh`; the user can also click the tab
   and type directly. Also call `rzr-link.sh <id> <cwd>` here if the birth-time link
   was not yet captured (idempotent).
6. **Keep crews alive until the result is accepted; reap conservatively.** A `done`
   verdict is not acceptance — the user still has to review it, and review comes
   *after* a delay. Tearing down on `done` throws away the crew's live context, so
   when follow-up arrives you'd have to re-spawn cold. Instead:
   - **Follow-up continues the same crew.** More feedback on a task the crew
     already worked is *never* a fresh `rzr-start` with a new id — it's a
     `rzr-send.sh <id>` to the **live** crew, which still holds the full
     conversation. Same id, same agent, same context.
   - **If the crew was already reaped,** don't spawn a cold replacement either:
     `rzr-resume.sh <id> [--prompt "<follow-up>"]` reopens the *exact*
     conversation as a fresh crew tab (via `claude --resume` from
     `tasks/<id>/session.json`) and can deliver your follow-up in the same call.
     A brand-new `rzr-start` rehydrating from `handoff.md` is the last resort, not
     the default — it starts cold.
   - **Reap (`rzr-teardown.sh <id>`) only once** the result is captured **and**
     accepted (landed/merged, or the user explicitly signs off), or the user says
     to drop it. When unsure whether more is coming, leave it idle — an idle crew
     costs nothing; a prematurely reaped one costs a cold re-spawn.

   The `tasks/<id>/` folder (brief + handoff + session link) survives teardown, so
   even a reaped task is recoverable — but recovery is strictly worse than a crew
   you never closed. Prefer *not closing* over *closing and resuming*.

## Durable task folders & the handoff contract

`rzr-start` gives every task a folder under `$ROZORO_HOME/tasks/<id>/` — the durable
record that makes teardown non-lossy:

- `brief.md` — the INPUT, persisted predictably (rendered from `templates/brief.md`,
  which appends the handoff protocol and a unique `rozoro-task: <id>` marker).
- `handoff.md` — the OUTPUT, **append-only**. The protocol tells the crew to append
  a block before ending *every* turn, each carrying a `verdict:` line
  (`done | needs-action | failed | blocked`) and `inputs-needed:`. This is how you
  tell "done" from "needs more input", and it accumulates across multiple `rzr-send`
  rounds so context is never lost. Because it is append-only, reading only the last
  block would let a later `done` bury an earlier open question — so `rzr-status`
  scans *all* blocks and keeps surfacing any OPEN item until you `rzr-ack` it (the
  ack cursor `.acked-blocks` is separate from the miss-detector's `.seen-blocks` and
  advances only on an explicit ack).
- `session.json` — the resume link (`claude --resume <session_id>`), captured by
  `rzr-link` via marker-grep (concurrency-safe, unlike "newest file" when crews share
  a `--cwd`).

The protocol is delivered as the claude crew's **system prompt** (rendered per task
to `tasks/<id>/handoff-protocol.md`, passed via `--append-system-prompt-file`; on
resume it's re-injected into the follow-up prompt, since `claude --resume` doesn't
re-apply system-prompt flags). A standing system rule is more durable than a turn-1
instruction, but reliability still comes from the loop: detect a miss with
`rzr-status` (no new block on an idle edge), surface buried opens the same way, and
nudge with `rzr-send`. The folder lives in `$ROZORO_HOME` (data), never in this repo.

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
