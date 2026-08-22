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

The control tower runs from the rozoro checkout and invokes its local dispatcher
as `./bin/rozoro <verb>`. Keep the driver in that checkout; select every fresh
crew's target repository explicitly with `--cwd <repo>`. Rozoro itself does not
need to be registered on `PATH`. External dependencies still do: `herdr` (with a
running server, and the driver inside a herdr session), `jq`, `python3`, and the
selected harness. Run `./bin/rozoro doctor` to verify them and the resolved
default harness. It does not create or rewrite the optional
`$ROZORO_HOME/crew/default.json`.

## Trigger vocabulary

| Intent | Command |
|---|---|
| **Start** a task (blessed) | `./bin/rozoro start <display-name> --body <file> --cwd <repo> [spawn flags]` — reserves and prints an immutable task key, renders a durable brief, spawns, and links the session in one unskippable step |
| **Start** (low-level) | `./bin/rozoro spawn <id> --crew <preset> --cwd <repo> --prompt "<task>"` (or `--brief <file>`) — raw spawn; no task folder, no handoff protocol, no session link |
| **Steer** (DATA — text the agent reads) | `./bin/rozoro send <id> "<text>"` |
| **Interrupt / cancel / key press / restart** (CONTROL — a closed verb list the harness *executes*, never text the agent might interpret as chat) | `./bin/rozoro control <id> interrupt` · `./bin/rozoro control <id> cancel` · `./bin/rozoro control <id> key <name>` · `./bin/rozoro control <id> restart` |
| **Resume** a reaped task | `./bin/rozoro resume <id> [--prompt "<follow-up>"]` — reopens the *exact* Claude, Codex, or Pi conversation as a fresh tab; for a task torn down before a follow-up arrived. If the crew is still live, use **send**, not resume |
| **Stop / reap** | `./bin/rozoro teardown <id>` (≡ `./bin/rozoro control <id> stop`) — refuses if the crew's `cwd` has unlanded work (uncommitted/untracked changes, unpushed commits); `--force` to discard anyway |
| **Read verdict** | `./bin/rozoro status <id>` — latest handoff verdict + whether a NEW block appeared (miss-detector) **and any unresolved OPEN items** — every block with a `needs-action`/`blocked`/`failed` verdict or a set `inputs-needed` keeps surfacing until acked, so a later `done` can't bury an earlier open question |
| **Resolve open items** | `./bin/rozoro ack <id> [--through <n>]` — after you've handled the open items status surfaced, ack them so status stops resurfacing them (advances a cursor; never edits the append-only handoff) |
| **Sense** (don't block) | Pi watchtowers use the project `rozoro-watchtower` extension, which injects actionable Herdr edges without occupying a tool call. Codex/Claude watchtowers register once (`./bin/rozoro register --harness <h>`) then run `./bin/rozoro watch --once --wake <ids>` in a genuinely external background task; the wake is durable (at-least-once ledger) and the driver runs `./bin/rozoro reconcile` on the nudge. Read `state/<id>.status` for the latest watcher-produced snapshot. |

`<id>` is a short unique slug you choose (e.g. `issue-123`, `pr-88`). It names the
state files and the tab.

**Never conflate DATA and CONTROL.** `./bin/rozoro send` is free text the crew reads
and reasons about — a prompt or follow-up. `./bin/rozoro control` is a lifecycle
action from a closed verb list that the harness *executes* directly — it never
passes through the agent as something to interpret. Sending a lifecycle command
as chat text (hoping the agent "reads" it and stops) is the failure this split
prevents. `./bin/rozoro control` also fails closed: an unresolved task id or a pane
that's already gone is refused loudly rather than guessed at, and every verb
verifies its own postcondition (e.g. `interrupt` confirms the agent actually
left `working`) instead of trusting the send call's exit code alone.

## Picking a crew

**Default to the default preset.** Don't grade tasks by complexity to pick a
model — that's an upfront investigation, and the crew is capable on the default.
Only override when the **user explicitly** asks for a specific crew/model (or has
a standing preference). Inspect presets with `./bin/rozoro crew list`.

Crew presets bundle *how* an agent boots (harness, model, permission mode, effort, fast tier,
standing rules) — never the task.

- `$ROZORO_HOME/crew/default.json` is authoritative when present. The recommended
  personal default is **gpt-5.6-sol Codex at `high` effort**.
- Without that file, the hardcoded default is Claude/Sonnet/`auto`; an explicit
  `--harness codex` selects gpt-5.6-sol/`low`. Every Codex spawn and resume is
  forced to `--yolo`, including presets whose `permission_mode` is empty.
- User asked for another model → override: `./bin/rozoro spawn <id> --model <model> --cwd … --prompt …`.
- Presets live at `$ROZORO_HOME/crew/<name>.json`; create new ones (e.g. a
  `senior` opus preset, or one whose `rules` say "open a draft PR, never push").
- `rules` in a preset are crew-behavioral. Claude and Pi receive them through
  system-prompt channels; other harnesses receive them in the delivered prompt.
  Repo-specific rules stay in the repo, not the preset.

Precedence: explicit flag > preset file > hardcoded harness fallback. Codex
permission mode is the exception: the spawner always uses `--yolo`.

The optional boolean `fast` is independent of reasoning effort. In the supported
Codex Stage 1 path, `fast:true` is valid only with `gpt-5.6-sol` and maps to the
priority service tier; use `--fast`/`--no-fast` to override it. Pi fast mode is
not yet supported and fails closed. Resolved model, effort, and fast values are
persisted for restart and exact resume.

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
   `./bin/rozoro start <display-name> --body <file> --cwd <repo>` (add `--model <model>` only if the
   user asked for it). Use the immutable key it prints for all later operations.
   The command writes the **durable brief** (with the
   handoff protocol) into `tasks/<task-key>/`, spawns the
   crew, and links its session — all verbatim, no shell escaping. Prefer this over
   raw `./bin/rozoro spawn`, which skips the task folder, protocol, and session link.
   Keep the body **intent + pointer**, not a dossier: what outcome you want and
   where to look (`issue #NNN`, a PR, a path) — the crew investigates from there.
   Front-load only the constraints the crew *can't* discover on its own (a merge
   rule, a "don't touch X", a preferred approach). If you catch yourself pasting
   issue comments or repro steps into the brief, you're doing the crew's job.
3. **Do not sit in a poll loop or occupy a foreground tool call with a watcher.**
   A foreground `./bin/rozoro watch` blocks the watchtower's model turn, so operator
   messages queue behind it. In Pi, the project-local `rozoro-watchtower`
   extension owns a long-lived Herdr push subscriber and injects
   `[rozoro event]` messages on actionable edges; `/rozoro-monitor status`
   reports it and `/rozoro-monitor on` repairs it. In a resident Codex or Claude
   watchtower, register the validated target once (`./bin/rozoro register --harness
   <h>`), then run `./bin/rozoro watch --once --wake <ids>` from a genuinely external
   background task: it delivers a fixed, content-free nudge on settled `idle`,
   `done`, or `blocked` edges through the registered backend (Codex queue, or the
   Herdr pane for Claude — deferred while the driver is working/blocked), backed by
   a durable at-least-once ledger. On the nudge run `./bin/rozoro reconcile` to read
   verdicts and ack the generation. `./bin/rozoro list` polling is
   only a fallback. `state/<id>.status` is produced by the active watcher. Either
   way, `done`/`idle` means the agent ended a turn — not that the task is correct
   or landed.
4. On each edge, run `./bin/rozoro status <id>` — read the **handoff verdict**, not herdr's
   raw `done`: `done` → verify the result (pane, repo, `gh`); `needs-action` →
   answer via `./bin/rozoro send`; a `[same]`/no-new-block on an idle edge means the crew
   ended a turn without reporting (e.g. backgrounded work) — nudge it. Status also
   prints any **unresolved OPEN items** (an earlier `needs-action`/`blocked`/`failed`
   or an unanswered `inputs-needed`): a `done` verdict with an OPEN list means the
   crew finished *this* turn but an earlier question is still hanging — handle it,
   then `./bin/rozoro ack <id>` so it stops resurfacing. **`done` is an invitation to
   review, not a signal to reap** — a done crew sits idle at ~0 cost, so leave it
   alive (see step 6).
5. Steer any crew that needs it with `./bin/rozoro send`; the user can also click the tab
   and type directly. Also call `./bin/rozoro link <id> <cwd>` here if the birth-time link
   was not yet captured (idempotent).
6. **Keep crews alive until the result is accepted; reap conservatively.** A `done`
   verdict is not acceptance — the user still has to review it, and review comes
   *after* a delay. Tearing down on `done` throws away the crew's live context, so
   when follow-up arrives you'd have to re-spawn cold. Instead:
   - **Follow-up continues the same crew.** More feedback on a task the crew
     already worked is *never* a fresh `./bin/rozoro start` with a new id — it's a
     `./bin/rozoro send <id>` to the **live** crew, which still holds the full
     conversation. Same id, same agent, same context.
   - **If the crew was already reaped,** don't spawn a cold replacement either:
     `./bin/rozoro resume <id> [--prompt "<follow-up>"]` reopens the *exact*
     Claude, Codex, or Pi conversation as a fresh crew tab from
     `tasks/<id>/session.json` and can deliver your follow-up in the same call.
     A brand-new `./bin/rozoro start` rehydrating from `handoff.md` is the last resort, not
     the default — it starts cold.
   - **Reap (`./bin/rozoro teardown <id>`) only once** the result is captured **and**
     accepted (landed/merged, or the user explicitly signs off), or the user says
     to drop it. When unsure whether more is coming, leave it idle — an idle crew
     costs nothing; a prematurely reaped one costs a cold re-spawn.
   - **Teardown itself refuses on unlanded work.** If the crew's `cwd` still has
     uncommitted/untracked changes or unpushed commits, `./bin/rozoro teardown` exits
     with an error instead of closing the tab — the standard behavior only
     verifying `done` on the handoff should not accidentally cover. Land the
     work (or have the crew do so) and retry; `--force` is the explicit override
     for a deliberate discard, not the default path.

   The `tasks/<id>/` folder (brief + handoff + session link) survives teardown, so
   even a reaped task is recoverable — but recovery is strictly worse than a crew
   you never closed. Prefer *not closing* over *closing and resuming*.

## Durable task folders & the handoff contract

`./bin/rozoro start` atomically reserves a globally unique key for every display name and
gives it a folder under `$ROZORO_HOME/tasks/<task-key>/` — the durable
record that makes teardown non-lossy:

- `brief.md` — the INPUT, persisted predictably (rendered from `templates/brief.md`,
  which appends the handoff protocol and a unique `rozoro-task: <id>` marker).
- `handoff.md` — the OUTPUT, **append-only**. The protocol tells the crew to append
  a block before ending *every* turn, each carrying a `verdict:` line
  (`done | needs-action | failed | blocked`) and `inputs-needed:`. This is how you
  tell "done" from "needs more input", and it accumulates across multiple `./bin/rozoro send`
  rounds so context is never lost. Because it is append-only, reading only the last
  block would let a later `done` bury an earlier open question — so `./bin/rozoro status`
  scans *all* blocks and keeps surfacing any OPEN item until you `./bin/rozoro ack` it (the
  ack cursor `.acked-blocks` is separate from the miss-detector's `.seen-blocks` and
  advances only on an explicit ack).
- `session.json` — the Claude/Codex/Pi resume link. Pi uses its preallocated
  native session UUID; Claude and Codex use marker discovery.

The protocol is delivered through Claude and Pi **system prompts** or folded
into the prompt for harnesses without that channel. It is rendered per task to
`tasks/<id>/handoff-protocol.md` and re-injected into resume follow-ups. A
standing system rule is more durable than a turn-1 instruction, but reliability
still comes from the loop: detect a miss with
`./bin/rozoro status` (no new block on an idle edge), surface buried opens the same way, and
nudge with `./bin/rozoro send`. The folder lives in `$ROZORO_HOME` (data), never in this repo.

## Gotchas

- Spawning in a repo the crew hasn't trusted shows Claude Code's trust dialog;
  `./bin/rozoro spawn` reports the pane `blocked`. Accept it once with
  `./bin/rozoro control <id> key enter` (a key press is CONTROL, not chat text), then
  re-deliver the prompt.
- One live agent per unique name — always give each task a distinct `<id>`.
- Claude, Codex, and Pi are wired for model and effort. Claude and Pi receive
  rules through system-prompt channels; Codex receives them in the delivered
  prompt. Copilot remains mapped from a known invocation but unverified. An
  unmapped harness fails loudly.
- Concurrent crew in the **same** checkout will clobber each other — worktree
  isolation is the *crew's* job (via repo rules), so prefer repos/tasks whose
  rules handle it, or spawn against separate checkouts.
- A crew can self-background its own long-running command (e.g. a `sleep`, a
  build) and **end its turn early** — the edge to `done` fires before the work
  is actually finished. The footer showing `1 shell`/`1 monitor` is the tell:
  read the pane and steer with `./bin/rozoro send` to make it finish; don't assume
  `done` means complete.
