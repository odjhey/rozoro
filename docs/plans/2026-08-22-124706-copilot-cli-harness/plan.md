# Make GitHub Copilot CLI a first-class crew harness

Status: accepted implementation plan

Created: 2026-08-22 12:47:06 Asia/Manila

Scope: complete Copilot crew registration and lifecycle parity; no implementation in this PR

Implementation target: a separate Pi crew using `openai-codex/gpt-5.6-sol` at low reasoning effort

## Outcome

A configured GitHub Copilot CLI can be selected anywhere Rozoro currently selects
Claude, Codex, or Pi and can complete the whole crew lifecycle:

```text
preset/doctor -> start/spawn -> status/watch -> send/control -> link -> teardown -> exact resume
```

The implementation keeps Rozoro's existing boundary: Herdr owns the terminal and
normalized foreground state; Copilot owns its conversation and model routing;
Rozoro owns only the durable task/profile/session metadata and handoff contract.
It does not scrape Copilot's alternate-screen UI, parse private conversation
databases, emulate Copilot, or introduce a Copilot-specific process manager.

The implementation is intentionally based on the current executable contracts:
GitHub Copilot CLI 1.0.80 and Herdr 0.8.2. It capability-checks required CLI
flags instead of relying only on a numeric Copilot version, because the CLI is
self-updating and distribution package versions may lag the executable's
reported version.

## Decisions at a glance

- The no-personal-preset fallback for `--harness copilot` is model `auto`, no
  explicit reasoning effort, `fast:false`, and autonomous permission mode.
  `auto` is the only portable model choice across Copilot accounts and plans.
- A configured Copilot `model` and supported Rozoro `effort` pass through as
  `--model` and `--effort`. Explicit flags retain the existing precedence over a
  preset and fallback.
- Copilot crews always launch in autonomous mode with `--autopilot --yolo
  --no-ask-user`, regardless of an empty or weaker `permission_mode`, and record
  the normalized permission mode as `yolo`. This matches the existing Codex
  invariant that a crew must not stop at an approval dialog.
- Copilot launches also use `--no-auto-update`; a managed crew run must not
  mutate or replace its harness executable during startup.
- `fast:true` remains Codex-only. Copilot profiles with `fast:true` continue to
  fail before Herdr creates a tab.
- Rozoro preallocates a UUID and passes `--session-id <uuid>` on every fresh
  Copilot launch. Exact resume uses `--resume=<uuid>`.
- Copilot has no verified append-system-prompt flag. The rendered handoff
  protocol and preset rules remain prepended to the initial delivered prompt,
  separated from the caller's unchanged task body. Resume follow-ups get the
  existing explicit resumed-turn preamble.
- Copilot watchtower registration uses the validated generic Herdr wake backend.
  No Copilot-native wake channel is added.
- Status, watch, send, interrupt, cancel, key, stop, and restart remain generic
  Herdr operations. Copilot-specific UI/status parsing is forbidden.

## Current repository state

Master at planning time is `f7c42f8` (`Configure repository test command
(#41)`). The repository already contains a partial Copilot mapping, but the
public documentation correctly calls it unverified and the lifecycle is not
complete.

### What already works in principle

- `bin/rzr-lib.sh` includes `copilot` in `rzr_profile_validate`'s harness
  allowlist.
- `rzr_harness_args` can emit `--model <m> --mode autopilot --allow-all` when
  `permission_mode` is non-empty.
- Herdr 0.8.2 lists `copilot` as a supported `herdr agent start --kind` value.
- `rzr-status.sh`, `rzr-watch.sh`, `rzr-send.sh`, and most of
  `rzr-control.sh` address the recorded Herdr pane rather than branching on the
  harness. They do not need a Copilot transport fork.
- The initial prompt path already prepends the handoff protocol for harnesses
  without a dedicated system-prompt channel.
- `rzr-doctor.sh` checks the selected harness executable generically.

### Gaps that prevent first-class use

- The Copilot mapping drops `effort`, does not preallocate a native session id,
  does not suppress `ask_user`, and is conditional on the generic permission
  field being non-empty.
- The generic no-preset fallback gives Copilot an empty model instead of a
  deliberate portable fallback.
- `rzr-link.sh` supports only Claude, Codex, and Pi; a blessed Copilot
  `rozoro start` therefore spawns but cannot produce a durable resume link.
- `rzr-resume.sh` rejects `harness: copilot` descriptors.
- `rzr-register.sh` rejects Copilot even though its Herdr backend is
  harness-neutral and Herdr reports the harness accurately.
- `rzr-crew.sh` does not display Copilot's normalized autonomous permission
  posture.
- Deterministic tests contain no Copilot fake/cases, and the README and Rozoro
  skill still say Copilot is unverified or omit it from lifecycle parity lists.
- There is no opt-in live Copilot lifecycle smoke test.

## Installed Copilot and Herdr evidence

The following was verified on the planning machine without changing repository
files.

### CLI surface

`copilot --version` reports GitHub Copilot CLI 1.0.80. Its help advertises:

- `--model <model>`, including `auto`;
- `--effort` / `--reasoning-effort` with `none`, `minimal`, `low`, `medium`,
  `high`, `xhigh`, and `max` at the Copilot layer;
- `--autopilot` and `--mode autopilot`;
- `--allow-all` / `--yolo`;
- `--no-ask-user`;
- `--session-id <uuid>` to assign a new session id or address an existing one;
- `--resume[=value]` for an exact id, prefix, task id, or name;
- `--no-auto-update`; and
- `COPILOT_HOME` as the public override for configuration and state root.

Copilot persists a preallocated session beneath
`$COPILOT_HOME/session-state/<uuid>/` (default `~/.copilot/...`) and records the
same `id` and the launch `cwd` in `workspace.yaml`. This layout is useful live
evidence, not a Rozoro integration contract: the implementation must not parse
it to link or resume.

### Real Herdr lifecycle

A real Herdr tab launched successfully with:

```sh
herdr agent start rzr-copilot-probe \
  --kind copilot --pane <pane> --timeout 60000 -- \
  --model gpt-5.6-sol --effort low \
  --autopilot --yolo --no-ask-user \
  --session-id 81a53044-d1d7-4931-aae3-e06e1465c277
```

Observed behavior:

- `agent start` reached `interactive_ready:true` and `agent_status:idle`.
- A Herdr prompt produced a real `working -> done` turn.
- After the first prompt, `herdr agent get` reported
  `agent_session:{agent:"copilot",kind:"id",source:"herdr:copilot",value:<uuid>}`.
  That field was absent in the immediate post-start snapshot, so birth-time
  linking must not depend on it becoming visible before the first turn.
- Closing the tab and launching
  `copilot --resume=<same-uuid> --model auto --autopilot --yolo --no-ask-user`
  reopened the exact conversation. A follow-up returned
  `COPILOT_RESUME_OK` after the original `COPILOT_SPAWN_OK` turn.
- A later prompt reached `working`; sending Herdr's `esc` control key returned
  the Copilot pane to `done`, confirming the existing interrupt transport and
  postcondition wait work for this harness.
- The probe tabs were closed, and the plan worktree remained clean.

### Model availability is account-specific

The installed help's model catalog listed `gpt-5.6-sol`, but this Copilot
account did not currently entitle that model. Copilot did not fail its process.
It emitted a model error in its event stream and changed the session from the
requested `gpt-5.6-sol/low` to `auto`, which routed the probe to another model.

This is a critical compatibility fact:

- Help/catalog presence is not an entitlement check.
- Rozoro can validate fields and required flags, but cannot promise that an
  account accepts a requested model.
- Rozoro must not parse private `events.jsonl`, SQLite stores, or terminal text
  to police this fallback.
- The built-in Copilot fallback is therefore `auto`, not a named model.
- Metadata and documentation must call an explicit Copilot model the resolved
  **requested launch profile**, not independently verified provider execution.
  Copilot's visible warning remains the source of truth if it falls back.

## Supported profile contract

### Built-in Copilot fallback

Extend `rzr_crew_builtin_default` with:

```json
{
  "harness": "copilot",
  "model": "auto",
  "permission_mode": "yolo",
  "effort": "",
  "fast": false,
  "rules": []
}
```

This object is used only when there is no configured preset and the caller
explicitly selects `--harness copilot`. It does not change the repository's
overall no-flag Claude fallback or create/modify `$ROZORO_HOME/crew/default.json`.

### Precedence and normalization

Keep the existing profile precedence:

```text
explicit spawn/resume flag > configured crew preset > harness fallback
```

For Copilot:

- `model` may be `auto` or a Copilot model id and maps directly to `--model`.
- A non-empty Rozoro `effort` maps directly to `--effort`.
- The shared Rozoro effort schema remains `low|medium|high|xhigh|max` (or empty).
  Do not widen the cross-harness schema to Copilot-only `none|minimal` in this
  delivery.
- Normalize effective `permission_mode` to `yolo` after preset/flag resolution,
  exactly where Codex is normalized today. Display and persist the normalized
  value.
- `fast` must be false. Existing validation rejects true before any Herdr
  mutation.
- Unknown preset keys retain the existing forward-compatible behavior; malformed
  known fields still fail closed.

A named model is deliberately not hardcoded into the fallback. Users who know
their account catalog can create, for example:

```json
{
  "harness": "copilot",
  "model": "gpt-5.4-mini",
  "effort": "low",
  "permission_mode": "yolo",
  "fast": false,
  "rules": ["Do not merge pull requests."]
}
```

### Fresh launch argv

For a resolved profile, emit this argument order after Herdr's `--` separator:

```text
--no-auto-update
--autopilot
--yolo
--no-ask-user
--model <model>             # model is always non-empty for new supported launches
--effort <effort>           # only when non-empty
--session-id <uuid>
```

The exact order is made deterministic for tests; Copilot itself accepts these as
global options in any order. Do not pass the old `--mode autopilot --allow-all`
combination in addition to the canonical flags.

Preallocate the UUID with the same standard-library UUID mechanism used for Pi
and write it to `state/<id>.meta` as `session=<uuid>` before delivering the first
prompt. A fresh restart allocates a new UUID because restart is a new
conversation. An exact resume reuses the descriptor UUID.

### Prompt and rules behavior

Copilot has no verified append-system-prompt-file equivalent in 1.0.80. Preserve
the current no-system-channel payload:

```text
<rendered handoff protocol>
<standing preset rules, when present>

--- task ---
<caller's prompt or rendered brief, byte-for-byte>
```

The caller's task segment is unchanged and passed as one Herdr prompt argument;
it is not shell-expanded or rewritten. Tests may assert this generated prompt
contract. They must not claim that source text alone proves model compliance.

Do not use Copilot custom agents, plugins, hooks, global settings, or repository
instruction files to install the handoff protocol. Those are user/repository
state and would violate Rozoro's no-setup, no-config-mutation boundary.

## Session linking and exact resume

### Fresh link

Copilot supports caller-selected session ids, so linking is simpler than marker
scanning:

1. `rzr-spawn.sh` allocates and records the UUID before `agent start`.
2. `rzr-link.sh` reads the recorded `session` for `harness=copilot`.
3. It writes the current schema's durable descriptor without reading
   `$COPILOT_HOME`, `workspace.yaml`, `events.jsonl`, `session.db`, or
   `session-store.db`.
4. It omits `session_path` for this preallocated-id case rather than inventing a
   private storage path. Make the descriptor writer include `session_path` only
   when a harness branch has a real path.
5. It records the human diagnostic string
   `copilot --resume=<uuid>` consistently with the existing schema. The future
   capability-aware descriptor from issue #10 may replace this string with safe
   argv; this delivery must not require shell evaluation of the string.

Target descriptor on the current master schema:

```json
{
  "id": "issue-42--<ulid>",
  "harness": "copilot",
  "cwd": "/absolute/repo",
  "session_id": "<preallocated-uuid>",
  "resume": "copilot --resume=<preallocated-uuid>",
  "profile": {
    "harness": "copilot",
    "model": "auto",
    "effort": "",
    "permission_mode": "yolo",
    "fast": false
  }
}
```

No marker scan fallback is needed for legacy Copilot sessions: released Rozoro
versions could not link them in the first place. A hand-authored valid descriptor
with these fields remains resumable.

`rzr-link` stays idempotent for the matching harness/cwd and continues enriching
the descriptor from current live metadata after resume overrides. `--refresh`
after a fresh restart must replace the old UUID with the newly preallocated one.

### Resume argv

Allow `copilot` in `rzr-resume.sh`'s supported harness case and launch:

```text
--no-auto-update
--resume=<session-id>
--autopilot
--yolo
--no-ask-user
--model <persisted-or-overridden-model>   # when non-empty
--effort <persisted-or-overridden-effort> # when non-empty
```

The existing profile override rules remain in force. Resume records the same
normalized metadata, then delivers an optional follow-up through Herdr. The
follow-up uses the existing resumed-turn handoff preamble because Copilot has no
system-prompt reapplication channel.

If no follow-up is supplied, Copilot resumes to an idle prompt with its original
conversation. If the task is still tracked/live, `rzr-resume` must continue to
refuse before tab creation and direct the caller to `rozoro send`.

### Coordination with issue #10

Open issue #10 plans a generic capability-aware descriptor that prefers Herdr's
public `agent_session` identity and stores resume argv instead of a shell-like
string. This Copilot implementation does not need to block on that work because
the caller-selected UUID is already an exact identity and the current descriptor
is sufficient.

If #10 lands before implementation:

- use its new descriptor writer rather than restoring the old shape;
- record Copilot identity as kind `id`, value `<uuid>`, source
  `caller-preallocated` (and optionally confirm the eventually reported
  `herdr:copilot` value);
- store resume argv as `[
  "copilot", "--no-auto-update", "--resume=<uuid>", ...]` through the new
  capability interface; and
- retain read compatibility with the current descriptor sample above.

Do not duplicate a second generic `agent_session` parser in this feature merely
to anticipate #10.

## Spawn, status, control, and registration semantics

### Spawn/start

- Capability and profile validation happen before `herdr tab create`.
- `rozoro start` still reserves the durable task folder and brief first; on an
  incompatible/missing Copilot binary it may leave that durable input record,
  but must not create a Herdr tab or live metadata.
- Successful `agent start` follows the existing transient
  `agent_pane_busy`/`agent_not_ready` retry behavior.
- A failed Copilot process records `agent_start=failed`, retains the inspectable
  tab, and prints the existing teardown/retry diagnostic.
- Initial delivery remains `herdr agent prompt`, so data transport and launch
  options stay separate.

### Status and watch

No Copilot branch belongs in `rzr-status.sh`, `rzr-runtime.py`, or
`rzr-watch.sh`.

- Herdr's normalized `idle|working|done|blocked|unknown` is the foreground
  source of truth.
- The append-only handoff remains the task/turn source of truth.
- `done` means the Copilot turn ended, not that the result is accepted.
- Missing handoff and unresolved input continue to be actionable through the
  schema-v2 reducer.
- Background-work certification remains unknown under Herdr 0.8.2 for Copilot
  just as for other harnesses; do not infer it from Copilot's footer or tasks UI.

### Data and control

No Copilot branch belongs in `rzr-send.sh` or the interrupt/cancel/key paths of
`rzr-control.sh`.

- `send` uses `herdr agent prompt` and fails closed for an unknown/dead/blocked
  target under the existing rules.
- `interrupt` sends `esc`; `cancel` sends `ctrl+c`; `key` sends the named key.
- Each action uses Herdr's existing postcondition wait and reports inability to
  verify rather than claiming success.
- `stop` delegates to teardown.
- `restart` preserves requested model/effort/yolo/fast-false/rules behavior,
  launches a fresh Copilot UUID, and refreshes any existing durable link.
- `resume` is distinct from restart and reuses the exact old UUID/context.

### Watchtower registration and wake

Add `copilot` to `rzr-register.sh`'s declared-harness allowlist and diagnostics.
The backend policy is:

- explicit/automatic Herdr backend validates `HERDR_PANE_ID`, reported harness
  `copilot`, and `interactive_ready:true`;
- `auto` selects Herdr for Copilot even if the environment contains a stale
  `CODEX_THREAD_ID`;
- the Codex native queue backend remains legal only for `harness=codex`; and
- wake delivery remains the fixed content-free reconciliation nudge through the
  durable ledger.

This enables a Copilot-hosted driver to register safely, but does not add a
Copilot watchtower extension or native remote-control integration. Crew sensing
itself is unchanged and works regardless of driver harness.

## Capability checks and failure handling

Add one narrow Copilot capability helper used by spawn and doctor. It invokes
the public, non-interactive `copilot --help` interface and requires the option
names used by the mapping:

```text
--model --effort --autopilot --yolo --no-ask-user
--no-auto-update --session-id --resume
```

This runtime help inspection is a legitimate capability check, not a test that
greps Rozoro implementation source. It avoids an unverifiable minimum-version
guess.

Failure policy:

| Condition | Required behavior |
| --- | --- |
| `copilot` missing | Doctor fails for a selected/default Copilot preset; spawn fails before Herdr mutation. |
| Required flag absent/help fails | Doctor names the missing capability; spawn fails before Herdr mutation and recommends upgrading Copilot CLI. |
| Authentication absent/expired | Do not inspect credentials. Copilot/Herdr surfaces login or startup failure; live smoke explains `copilot login`. No secret enters Rozoro state. |
| Invalid or unentitled explicit model | Pass through the requested model. Document Copilot 1.0.80's possible warning/fallback to `auto`; do not scrape private events to override it. |
| Unsupported Rozoro effort | Existing profile validation fails before mutation. Copilot-only `none|minimal` remain out of scope. |
| `fast:true` | Existing Codex-only validation fails before mutation. |
| Copilot CLI flag/API drift | Capability check fails early; deterministic fake test covers missing-capability diagnostics. |
| `agent_pane_busy` | Existing bounded retry. |
| `agent_not_ready` after process claim | Existing readiness wait; never start a duplicate process. |
| Session already live/in-use elsewhere | Rozoro refuses its own tracked task; otherwise Copilot start failure is surfaced and the created tab remains inspectable. |
| Missing/corrupt `session.json` | Existing exact-resume diagnostics; never silently cold-spawn. |
| Missing Copilot local session for a descriptor UUID | Copilot's resume startup fails; Rozoro reports agent-start failure and never scans/fuzzily chooses another session. |
| `COPILOT_HOME` override | Inherited by the harness; linking remains correct because it uses the preallocated UUID, not a hardcoded store. |
| Copilot self-update | Managed launches pass `--no-auto-update`; Rozoro does not persistently edit Copilot settings. |
| Herdr omits `agent_session` initially | No impact; the preallocated UUID is authoritative. |
| Copilot asks for user input | `--no-ask-user` removes the native ask tool; the handoff protocol's `needs-action`/`inputs-needed` is the crew escalation channel. |
| Copilot autopilot continues unexpectedly | Keep Copilot's documented bounded default (currently five continuations); do not add an unbounded loop or a new preset field in this scope. |

## Exact file-level implementation scope

### `bin/rzr-lib.sh`

- Add the Copilot built-in fallback (`auto`, empty effort, yolo, false fast).
- Add a reusable Copilot help-capability check with precise diagnostics.
- Keep Copilot in the harness allowlist and existing shared profile validation.
- Update comments to distinguish requested profile from account-accepted model.
- Change the Copilot `rzr_harness_args` branch to emit the canonical autonomous,
  no-update, model, effort, and preallocated-session argv.

### `bin/rzr-spawn.sh`

- Update help/comments to list Copilot model/effort parity and forced autonomous
  posture.
- Normalize `PERMMODE=yolo` for both Codex and Copilot.
- Run the Copilot capability check after profile resolution/validation and
  before rendering/spawn mutation.
- Preallocate `SESSION_ID` for `pi|copilot`, persist it in live metadata, and pass
  it through `rzr_harness_args`.
- Keep Copilot on the no-system-channel prompt-prepend path.

### `bin/rzr-link.sh`

- Add Copilot to supported-link comments and dispatch.
- Build the link from the recorded preallocated session id with no filesystem
  scan.
- Make `session_path` optional in the serialized current-schema descriptor.
- Preserve idempotence, profile enrichment, refresh, and legacy descriptor reads.

### `bin/rzr-resume.sh`

- Add Copilot to help, diagnostics, and supported harness dispatch.
- Normalize resumed Copilot permission mode to yolo.
- Emit exact-id autonomous resume argv and reapply model/effort overrides.
- Preserve prompt preamble, readiness retry, metadata, and failure behavior.

### `bin/rzr-register.sh`

- Add Copilot to the accepted harness list/help/errors.
- Reuse validated Herdr backend selection; do not permit the Codex backend for
  Copilot.

### `bin/rzr-crew.sh`

- Show `yolo` as the effective permission mode for Copilot, as it already does
  for Codex.
- Update fallback/help prose to include Copilot `auto`.

### `bin/rzr-doctor.sh`

- When the resolved default harness is Copilot, run the capability helper after
  the executable-presence check.
- Report missing flags as a hard failed precondition without inspecting auth.

### Production files intentionally unchanged

- `bin/rzr-start.sh`: existing render/spawn/link sequencing and retry are enough.
- `bin/rzr-status.sh`, `bin/rzr-runtime.py`, `bin/rzr-watch.sh`: Herdr/status-v2
  behavior is harness-neutral.
- `bin/rzr-send.sh`: Herdr data plane is harness-neutral.
- `bin/rzr-control.sh`: existing generic controls/restart composition are enough;
  add tests rather than a Copilot branch.
- `bin/rzr-teardown.sh`: no harness-specific cleanup or Copilot-store deletion.
- Templates: the current handoff protocol is harness-neutral.

### `tests/fakes/copilot` and `tests/test_helper/common.bash`

- Add an executable fake that returns a minimal realistic `--help` surface and
  version without auth/network access.
- Add knobs to omit one capability or fail help for negative tests.
- Reset those knobs in common setup to prevent cross-test leakage.

### `tests/lifecycle.bats`

Add behavior-level cases for:

- no-preset Copilot fallback (`auto`, yolo, no fast, preallocated UUID);
- configured model/effort/rules mapping and exact generated prompt payload;
- capability failure before `tab create`;
- native preallocated link with no private Copilot fixture/store;
- descriptor profile enrichment and optional `session_path`;
- exact Copilot resume argv, follow-up preamble, and override persistence;
- legacy/hand-authored current-schema Copilot descriptor resume;
- restart preserving profile but replacing the session UUID and refreshed link;
- fast rejection before Herdr mutation; and
- generic send/interrupt postconditions against a fake pane reporting Copilot.

Assert executable output, fake Herdr argv, metadata, descriptors, and delivered
prompt contracts. Do not grep implementation source.

### `tests/register.bats`

- Register a fake ready Copilot pane through Herdr.
- Prove auto ignores a stale `CODEX_THREAD_ID` for Copilot.
- Prove explicit Codex backend is rejected for Copilot.

### `tests/doctor.bats`

- Prove a default Copilot preset passes with the capable fake.
- Prove missing executable and missing required flag produce distinct failures.

### `tests/live/copilot-lifecycle.sh`

Add an opt-in, cost-incurring smoke test guarded by
`RZR_LIVE_COPILOT=1`; otherwise exit 77 with a clear skip. It should:

1. print Copilot and Herdr versions;
2. require an already authenticated Copilot CLI but never print auth state;
3. use a temporary non-repository cwd and isolated temporary Rozoro task state;
4. start a Copilot `auto` crew through `./bin/rozoro start`;
5. verify real Herdr `working -> done`, a valid handoff block, normalized live
   metadata, descriptor UUID, and eventual matching Herdr `agent_session`;
6. send one live follow-up and verify another handoff turn;
7. exercise Escape interrupt on a bounded sleep/tool task and verify the pane
   leaves `working`;
8. force-teardown, exact-resume the descriptor UUID, and verify retained context
   plus another handoff;
9. optionally test a named model from `RZR_LIVE_COPILOT_MODEL`, treating a
   Copilot account fallback as documented evidence rather than false Rozoro
   success; and
10. close every created tab and remove temporary state in a trap.

This script is development/manual evidence only and must not run in networkless
CI.

### `README.md`

Update all parity lists and examples:

- requirements and command table link/resume text;
- built-in Copilot fallback and permission normalization;
- harness mapping table with canonical flags;
- prompt/rules channel distinction;
- session preallocation and exact resume;
- registration through generic Herdr backend;
- requested-model/account-fallback limitation;
- verified Herdr 0.8.2 list and the live-smoke invocation; and
- remove the statement that Copilot is unverified.

Do not present a named Copilot model as universally available.

### `.agents/skills/rozoro/SKILL.md`

Update operator guidance so control towers can correctly select, inspect,
continue, and resume Copilot crews:

- parity lists and exact-resume wording;
- fallback/permission/profile behavior;
- prompt-channel description;
- registration/wake backend selection; and
- gotchas for account-specific model fallback and no Copilot fast mode.

Do not make Copilot the repository-wide default or add model-selection policy to
the driver.

## Deterministic test plan

Run the full pinned, networkless suite through the repository command:

```sh
./tests/run.sh
```

The test image has no real Copilot binary, credentials, home, or service access.
All Copilot behavior in CI is exercised through the public Rozoro commands, fake
Herdr, and the new help-capability fake.

Required regression assertions:

1. Profile resolution precedes mutation and produces deterministic argv.
2. Copilot permission is yolo even when a preset omits or weakens
   `permission_mode`.
3. Model and effort overrides beat preset/fallback and survive link/resume.
4. Rules and protocol are prepended once; the task segment remains exact.
5. A fresh UUID is generated and persisted for spawn/restart, while resume reuses
   the linked UUID.
6. Link succeeds without any `$COPILOT_HOME` fixture or transcript scan.
7. A descriptor without `session_path` is valid and resumable.
8. Unknown/corrupt descriptors fail without tab mutation or fuzzy selection.
9. Missing binary/capability fails before Herdr tab creation.
10. `fast:true` fails before Herdr tab creation.
11. Registration validates Copilot's live Herdr identity and never chooses a
    stale Codex thread.
12. Generic status/send/control behavior remains unchanged for other harnesses.
13. Existing Claude, Codex, Pi, legacy descriptor, restart, doctor, register,
    watch, and status-v2 tests remain green.
14. Shell entry points still parse under stock macOS Bash 3.2; Python helpers
    still compile into the isolated cache root.

## Live validation matrix

Before the implementation PR is declared ready, record sanitized evidence for:

| Scenario | Required observation |
| --- | --- |
| Fresh default launch | `auto` requested; autonomous flags and preallocated UUID in Herdr argv; ready idle pane. |
| Initial task | Real working/settled edge and valid turn-1 handoff. |
| Live follow-up | Same pane/session id, new handoff turn, no cold spawn. |
| Interrupt | Escape while working; verified departure from working. |
| Teardown/resume | New pane, same Copilot UUID, retained context, resumed handoff. |
| Restart | New pane and new UUID; same requested profile; durable link refreshed. |
| Registration | Copilot declaration validates against Herdr and selects Herdr backend. |
| Named available model | Requested model/effort shown by Copilot or sanitized session-start evidence. |
| Named unavailable model | Copilot warning/fallback documented; Rozoro remains usable and does not misreport enforcement. |
| Missing capability | Early failure before tab mutation using a controlled fake/old executable. |
| Auth failure | Clear Copilot/Herdr failure or login state; no token in logs/state. |
| Custom `COPILOT_HOME` | Fresh and resumed UUID still work without Rozoro scanning the store. |

Evidence may include versions, task ids, UUIDs, Herdr argv/status JSON, normalized
handoff fields, and pass/fail output. It must not include tokens, private session
content beyond synthetic probe strings, raw account data, or unrelated user
conversation history.

## Documentation and compatibility promises

- Supported baseline is capability-based and live-verified on Copilot CLI 1.0.80
  plus Herdr 0.8.2.
- Existing personal preset files are never migrated or rewritten.
- Existing Claude/Codex/Pi fallback, launch, session, and resume behavior is
  unchanged.
- Existing current-schema descriptors remain readable. `session_path` becomes
  optional, not forbidden.
- Copilot descriptors created by this implementation remain adaptable to issue
  #10's future capability schema.
- Copilot's private state format is explicitly not a Rozoro API.
- Authentication and model entitlement remain Copilot concerns.
- `auto` is a routing policy, not a durable concrete model identity.
- Explicit model metadata records requested launch configuration; it is not
  evidence that Copilot's service honored the model.
- No Copilot-native queue/wake, background-job parser, or watchtower extension is
  promised.

## Non-goals

- Implementing any harness support in this planning PR.
- Making Copilot the global default crew or changing a user's default preset.
- Installing, authenticating, updating, or configuring Copilot CLI.
- Reading/writing Copilot credentials, settings, plugins, hooks, custom agents,
  or instruction files.
- Parsing Copilot alternate-screen output, footer, `events.jsonl`, SQLite, or
  `workspace.yaml` in production code.
- Validating account model entitlement or preventing Copilot's documented
  fallback behavior.
- Adding Copilot-only `none|minimal` effort values to the generic preset schema.
- Supporting fast/priority tier for Copilot.
- Adding a Copilot-specific wake queue, background process, daemon, ACP path, or
  remote-control integration.
- Refactoring all harness cases into a new registry abstraction.
- Completing the generic capability-aware session descriptor in issue #10.
- Changing status-v2, handoff, teardown policy, or the DATA/CONTROL split.

## Implementation sequence

### Phase 1: characterization and capability guard

- Add the fake Copilot help executable and isolated environment knobs.
- Add failing behavior tests for fallback resolution, argv, missing capability,
  and pre-mutation failure.
- Implement the fallback, permission normalization, capability helper, and
  launch argv until those tests pass.

Checkpoint: a fake fresh Copilot spawn is deterministic, autonomous, session-id
preallocated, and incapable binaries fail before `tab create`.

### Phase 2: durable session lifecycle

- Add link tests for preallocated identity and optional path.
- Implement Copilot descriptor writing without store scanning.
- Add resume, override/relink, and restart tests.
- Implement exact resume and ensure fresh restart replaces the UUID.

Checkpoint: fake start/link/teardown/resume and restart paths preserve the right
profile and conversation identity semantics.

### Phase 3: registration and generic lifecycle proof

- Add Copilot register backend tests and update the allowlist.
- Add Copilot-labeled status/send/control characterization cases without adding
  harness branches.
- Run targeted Bats files, then the full suite.

Checkpoint: Copilot is accepted everywhere a declared harness should be and no
generic lifecycle regression exists.

### Phase 4: documentation and live proof

- Update README and the Rozoro skill.
- Add the opt-in live script.
- Run the real default, named-model, follow-up, interrupt, teardown/resume,
  restart, and registration matrix on current Copilot/Herdr.
- Capture only sanitized evidence in the implementation PR.

Checkpoint: documentation claims no more than automated and live evidence proves.

### Phase 5: delivery

- Rebase on current `origin/master`, reconciling any issue #10 descriptor work as
  described above.
- Run `./tests/run.sh`, `git diff --check`, and stock-Bash syntax checks through
  the repository's delivery pipeline.
- Review for accidental private-store coupling, config mutation, secret output,
  and source-grep tests.
- Open a focused implementation PR referencing this plan PR and include the live
  matrix evidence.

## Acceptance criteria

- `copilot` is a documented, tested option for preset resolution, doctor, spawn,
  link, resume, registration, and the generic lifecycle commands.
- An explicit `--harness copilot` with no personal preset launches the portable
  `auto` fallback in autonomous yolo mode.
- Configured Copilot model and non-empty supported effort map to CLI flags and
  persist through link, resume overrides, relink, and restart.
- Copilot always receives `--autopilot --yolo --no-ask-user --no-auto-update`;
  preset permission cannot weaken the autonomous crew contract.
- Every fresh launch/restart receives a new preallocated UUID. Exact resume uses
  the linked UUID and preserves conversation context.
- Linking and resume do not read or scan Copilot's private state stores and work
  with `COPILOT_HOME` overrides.
- Current-schema descriptors may omit `session_path`; all existing descriptors
  and Claude/Codex/Pi paths remain compatible.
- Copilot receives the handoff protocol and rules before an unchanged task
  segment and appends valid handoff turns in the live smoke.
- Status/watch use Herdr state plus the common handoff reducer; no Copilot UI
  scraping or status fork exists.
- Send, interrupt, cancel, key, stop, restart, and resume have the semantics in
  this plan and fail closed on unresolved/dead targets.
- `rzr-register --harness copilot` validates the resident Copilot pane and uses
  Herdr, never a stale Codex queue identity.
- Missing binary or required capability and invalid fast/effort profiles fail
  before Herdr mutation with actionable diagnostics.
- Documentation clearly distinguishes requested model from account-honored
  model and names `auto` as the portable fallback.
- Deterministic CI remains networkless and green; opt-in live evidence covers
  real spawn, turn status, follow-up, interrupt, exact resume, restart,
  registration, and model fallback behavior.
- No Copilot credentials, account data, private conversation data, or persistent
  settings are added to Rozoro state or test evidence.
- The implementation remains small and harness-adapter-shaped; it does not
  expand Rozoro into a manager, model router, or Copilot wrapper.

## Immediate handoff to the implementation crew

Start from the merged/current version of this file and current `origin/master`.
Use a repository worktree under `./.worktrees/` and a Pi crew configured as
`openai-codex/gpt-5.6-sol` with low reasoning effort. The first implementation
turn should:

1. read this plan completely;
2. inspect `bin/rzr-lib.sh`, `bin/rzr-spawn.sh`, `bin/rzr-link.sh`,
   `bin/rzr-resume.sh`, `bin/rzr-register.sh`, `bin/rzr-crew.sh`, and
   `bin/rzr-doctor.sh` at the current tip;
3. check whether issue #10 or another session-descriptor PR landed and choose the
   compatibility branch above;
4. add behavior-first fake/tests before production changes;
5. keep the built-in Copilot model `auto` even though the implementing Pi model
   is `gpt-5.6-sol`; those are unrelated choices;
6. avoid all private Copilot state parsing even though the planning evidence
   identified its current files; and
7. finish with the deterministic suite, opt-in live matrix, documentation,
   delivery pipeline, and an implementation PR.

The live planning probe already established that current Herdr can launch,
observe, interrupt, and exactly resume Copilot, and that a requested model can
silently fall back based on account entitlement. The implementation crew should
not repeat broad discovery; it should turn the contracts and tests above into a
small adapter completion.
