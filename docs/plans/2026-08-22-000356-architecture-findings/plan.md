# Restore rozoro's lifecycle, status, and conversation boundaries

Status: proposed implementation plan

Created: 2026-08-22 00:03:56 Asia/Manila

Scope: issues #8, #9, #10, and #11

Delivery shape: a sequence of small implementation PRs; this document does not
implement the changes

## Issue references

Restore the spawner boundary: remove Git/upstream policy from teardown

https://github.com/odjhey/rozoro/issues/8

Make handoff status pure, turn-aware, and explicit about runtime vs task state

https://github.com/odjhey/rozoro/issues/9

Make conversation linking capability-aware and prefer Herdr-reported session
identity

https://github.com/odjhey/rozoro/issues/10

Add a lightweight automated regression suite for protocol parsing and lifecycle
glue

https://github.com/odjhey/rozoro/issues/11

## Outcome

After this plan is implemented, rozoro remains a small task-envelope and
lifecycle layer over Herdr:

```text
driver policy: acceptance, delivery, Git and PR judgment
                         |
rozoro: task identity, brief/handoff, runtime projection, resume capability
                         |
Herdr: pane, tab, agent process, runtime events, reported session identity
                         |
harness: Claude, Codex, Copilot, Pi, ...
```

The implementation must establish four properties together:

1. Teardown acts only on rozoro-owned runtime metadata and Herdr tabs. It never
   gates cleanup on checkout-wide Git policy.
2. Status reads are pure. Runtime state, task/handoff state, and turn-report
   observations are named separately and cannot be changed by a reader.
3. Conversation identity is a harness capability. Herdr's public session
   metadata is preferred; vendor-private discovery is a bounded fallback.
4. All of these protocols are exercised without a real Herdr server, harness
   installation, user home, or developer checkout.

This work does not add durable acceptance, a workflow engine, a database,
task-owned worktrees, Git attribution, retry policy, or generalized harness
management. Acceptance stays a driver/user judgment. Herdr remains the owner of
terminals and processes. `brief.md` and append-only `handoff.md` remain the
portable task interface.

## Current-state evidence

The plan is based on `master` at `e6348d9`.

| Area | Evidence in the repository | Consequence |
| --- | --- | --- |
| Teardown boundary | `bin/rzr-teardown.sh` calls `rzr_unlanded_reasons` and describes `--force` as allowing discard; `bin/rzr-lib.sh` examines the entire checkout; `bin/rzr-control.sh restart` bypasses the guard | One task can be blocked by unrelated changes, and a tab close is incorrectly presented as deleting Git work |
| Status purity | `bin/rzr-status.sh` writes `.seen-blocks` on every non-`--peek` read and infers a missed handoff from `new_block=false` without observing a runtime edge | A second read manufactures a missing-handoff claim, and readers suppress one another |
| State vocabulary | `bin/rzr-watch.sh` mirrors Herdr state to `state/<id>.status`; `bin/rzr-list.sh` labels live Herdr state as `STATE`; status JSON exposes only handoff-centric keys such as `verdict` and `new_block` | Machine consumers cannot distinguish runtime, task projection, and observer facts |
| Handoff parsing | `bin/rzr-status.sh` and `bin/rzr-ack.sh` count every `## ` heading as a block | A Markdown subheading can become a false turn; parser and acknowledgement counts can drift if changed independently |
| Linking | `bin/rzr-start.sh` always retries `bin/rzr-link.sh`; the linker scans `$HOME/.claude/projects`, writes `harness: claude`, and stores a shell command string | Non-Claude starts perform a bogus Claude lookup, alternate Claude config roots are missed, and the stored schema conflates identity with invocation |
| Resume | `bin/rzr-resume.sh` directly reads legacy `session_id`, rejects all non-Claude records, and constructs Claude arguments itself | Resume capability is implicit and schema evolution has no normalization point |
| Public Herdr metadata | Herdr 0.8.2 `agent get` returns an `agent_info` object at `.result.agent`; its public `AgentInfo` schema permits `agent_session` with `source`, `agent`, `kind`, and `value` | Rozoro can use a public integration contract before inspecting private transcript storage |
| Regression safety | There is no `tests/` directory or CI workflow; the README records manual behavior claims | Small protocol changes can regress lifecycle and concurrency behavior without deterministic evidence |

The current `.acked-blocks` behavior is intentionally not grouped with the
reader-relative `.seen-blocks` defect. Acknowledgement is an explicit state
mutation. The FIFO/block-index model remains sufficient until selective,
out-of-order resolution becomes a demonstrated requirement.

## Target architecture and invariants

### Ownership

- `state/<id>.meta` maps a rozoro task to Herdr runtime identity and the recorded
  launch profile.
- `state/<id>.runtime.json` is an ephemeral, watcher-maintained observation of
  Herdr runtime state. It is not acceptance or durable task truth.
- `state/<id>.turn.json` is an ephemeral, watcher-maintained result of one
  observed `working -> settled` edge. It records whether that turn appended a
  protocol block.
- `tasks/<id>/brief.md`, `handoff.md`, `handoff-protocol.md`, and `session.json`
  are durable task data and survive teardown.
- `.acked-blocks` remains a durable, explicit driver cursor. Ordinary status and
  list reads never update it.
- Legacy `state/<id>.status` is a compatibility mirror during migration, not the
  new source of structured runtime facts.

### Invariants

1. `rozoro status` is referentially transparent for unchanged files: repeated
   invocations produce the same task facts and write no files.
2. Only an observed transition from `working` to `idle`, `done`, or `blocked`
   may produce a missing-handoff observation. Initial level reconciliation and
   arbitrary reads cannot do so.
3. A later `done` block never hides an earlier unresolved open block. Only
   `rozoro ack` advances `.acked-blocks`.
4. A handoff protocol block begins only at a canonical heading matching
   `^## turn [1-9][0-9]*\b`. Other Markdown headings are content, not turns.
   Duplicate or decreasing turn numbers and missing/unknown verdicts surface a
   protocol error instead of being silently reinterpreted.
5. Herdr runtime `done` and crew handoff `verdict: done` are assertions, never
   acceptance.
6. Teardown may remove live metadata and close a Herdr tab, but it must not
   inspect or mutate the task checkout.
7. Rozoro task ID, Herdr pane/tab identity, and harness conversation identity
   remain separate namespaces.
8. A start succeeds even when exact conversation resume is unsupported or no
   session identity is available. Resume never silently starts a cold session.
9. Stored resume commands are structured argv, never shell text, and are
   dispatched only through an allowlisted harness capability.
10. Tests never resolve the real default `~/.rozoro`, connect to a real Herdr
    socket, or scan the developer's real harness data.

## State contracts

### Runtime observation

`rzr-watch.sh` writes `state/<id>.runtime.json` atomically on initial
reconciliation and every real status edge:

```json
{
  "schema_version": 1,
  "runtime_status": "idle",
  "observed_at": "2026-08-21T16:10:00Z",
  "source": "herdr-watch"
}
```

`runtime_status` uses Herdr-derived values currently understood by rozoro:
`idle`, `working`, `done`, `blocked`, `unknown`, `shell`, and `gone`. Status
reads this mirror rather than contacting Herdr, so it stays a non-blocking,
pure inspection command. If neither the new file nor the compatibility token
exists, JSON returns `runtime_status: null`, `runtime_observed_at: null`, and
`runtime_source: "unobserved"`; it must not invent `idle` or `gone`.

For one compatibility window, the watcher also writes the existing plain token
to `state/<id>.status`. `rzr_status_get` reads `runtime.json` first and falls
back to `.status`; direct consumers are documented to migrate to `rozoro status
--json`. Teardown removes both ephemeral files.

### Turn observation

Each watcher keeps its own in-process previous runtime state and handoff block
baseline. When it sees `working`, it captures the canonical block count. When
that same observed turn settles, it atomically writes this idempotent projection
to `state/<id>.turn.json`:

```json
{
  "schema_version": 1,
  "transition": "working->done",
  "report_status": "missing",
  "blocks_before": 3,
  "blocks_after": 3,
  "observed_at": "2026-08-21T16:11:00Z"
}
```

`report_status` is `reported` when `blocks_after > blocks_before` and `missing`
when they are equal. A decreasing count is a `protocol-error`, because
`handoff.md` is append-only. No file is written merely because the watcher's
initial level is already settled. A watcher started while the pane is already
`working` captures the current baseline so it can classify the eventual settle.

Overlapping watchers may write the same logical observation. Their writes use a
temporary file plus `mv`; there is no shared incrementing cursor, so they cannot
double-count or suppress each other. Status readers only read this result.

### Task projection and status JSON

Add an internal standard-library parser at `bin/rzr-handoff.py`. Both
`rzr-status.sh` and `rzr-ack.sh` use it so canonical block recognition, count,
field normalization, and protocol errors have one implementation.

The task projection has this precedence:

1. `protocol-error` when canonical blocks are malformed, have invalid order, or
   the cursor cannot be interpreted safely.
2. `no-handoff` when there are no canonical blocks.
3. `open-items` when any unacknowledged block has verdict
   `needs-action|blocked|failed` or a non-empty `inputs-needed` value.
4. `reported-done` when the latest verdict is `done` and no item is open.
5. `reported-failed` when the latest verdict is `failed` and the relevant item
   was explicitly acknowledged.
6. `reported-incomplete` for an acknowledged latest `needs-action` or `blocked`
   report that has not yet been followed by a final report.

The v2 JSON contract is:

```json
{
  "schema_version": 2,
  "id": "task-1",
  "runtime_status": "idle",
  "runtime_source": "watcher-mirror",
  "runtime_observed_at": "2026-08-21T16:10:00Z",
  "task_status": "open-items",
  "handoff_verdict": "done",
  "blocks": 2,
  "acked_through": 0,
  "unresolved": 1,
  "open_items": [],
  "turn_report_status": "reported",
  "turn_observed_at": "2026-08-21T16:10:00Z",
  "protocol_errors": []
}
```

`open_items` retains its current detailed records; it is shortened above only
for readability. Existing descriptive keys such as `heading`, `reason`,
`pending`, `inputs_needed`, and `artifacts` remain. `verdict` remains for one
compatibility window as an alias of `handoff_verdict`.

`new_block` and `--peek` are removed because their reader-relative contract is
the defect. They are replaced by `turn_report_status`; the JSON version bump and
README call this out as a deliberate compatibility break. Existing
`.seen-blocks` files are ignored in place and can be removed manually; no eager
migration is required.

Human output labels each axis explicitly, for example
`runtime=idle task=open-items verdict=done`, and prints a missing-handoff warning
only when the latest turn observation says `missing`. `rzr-list.sh` changes its
ambiguous `STATE` heading to `RUNTIME` and adds a `TASK` column. Its runtime
column remains a live Herdr read; its task column uses the same pure parser.

### Conversation descriptor

New links use schema v2:

```json
{
  "schema_version": 2,
  "task_id": "issue-42",
  "harness": "claude",
  "cwd": "/repo",
  "session": {
    "kind": "id",
    "value": "9b92...",
    "source": "herdr-integration",
    "integration_source": "herdr:claude"
  },
  "resume": {
    "supported": true,
    "argv": ["claude", "--resume", "9b92..."]
  }
}
```

For an unsupported harness or absent identity, `session` may be `null` and
`resume` contains `supported: false` plus a stable reason such as
`unsupported-harness` or `session-unavailable`. This is a successful description
of a capability limit, not a failed task start.

`rzr-link.sh` obtains the recorded pane, harness, and cwd from
`state/<id>.meta`. Its existing positional cwd remains accepted as a deprecated
compatibility override. It parses Herdr 0.8.x defensively from
`.result.agent.agent_session`, with fallbacks for response shapes already
handled elsewhere, and validates that the reported agent matches the recorded
harness before persisting it.

Claude is the only initially enabled exact-resume capability. If Herdr does not
report its identity yet, the linker searches the marker under
`${CLAUDE_CONFIG_DIR:-$HOME/.claude}/projects/<cwd-slug>`. Non-Claude harnesses
never scan Claude storage. Session identity reported for another harness may be
recorded for future support, but `resume.supported` remains false until its
command and Herdr start behavior have dedicated fixtures and verification.

`rzr-lib.sh` owns a small allowlisted capability table that validates a
descriptor and emits argv safely. `rzr-resume.sh` never evaluates stored text;
it passes a validated argument array to `herdr agent start`. Legacy descriptors
with top-level `session_id`, `harness`, and `cwd` are normalized at read time to
the v2 shape and remain resumable. Existing files are not rewritten merely by a
read. New writes are atomic.

## Implementation phases

### Phase 1: land the test foundation from #11

Land the reusable harness before behavior changes. This first PR should leave
#11 open because later phases add its required coverage.

Add:

- `tests/run.sh`: the single documented entry point, deterministic ordering,
  concise per-test output, non-zero exit on failure.
- `tests/lib/testlib.sh`: `run_test`, temporary-environment setup, assertions,
  process registration, and cleanup traps compatible with Bash 3.2.
- `tests/fakes/herdr`: a PATH-injected fake driven by fixture files/environment;
  it records argv and serves tab, pane, agent, wait, and socket-discovery
  responses, including ordered transient failures.
- `tests/test_handoff.sh`: characterization tests for current append-only parsing
  and acknowledgement behavior, including a named characterization that proves
  the current reader-relative mutation and whose expected result is replaced by
  the purity assertion in Phase 3.
- `tests/test_watch.sh`: initial reconciliation, per-process deduplication, and
  overlapping `--once` watcher characterization.
- `tests/test_eventwait.py`: a standard-library Unix socket fixture for request,
  acknowledgement, event attribution, timeout, malformed ack, close, and broken
  pipe paths.
- `tests/test_lifecycle.sh`: spawn failure, unknown/dead target, teardown folder
  preservation, and legacy resume characterization.
- `tests/test_lock.sh`: live-holder refusal, stale-holder reclaim, and release.
- `.github/workflows/test.yml`: Linux and macOS jobs invoking `./tests/run.sh`.

Every shell test creates a temporary `HOME` and `ROZORO_HOME`, prepends
`tests/fakes` to `PATH`, points any socket use at a temporary path, and registers
children for cleanup. Tests needing Git create a disposable repository inside
the test temporary directory. They never inherit a real Herdr socket or Claude
config root. Syntax checks run `bash -n` on every shell script and compile
`bin/herdr-eventwait.py` with a temporary `PYTHONPYCACHEPREFIX`.

The macOS job is required because Bash 3.2 compatibility is an explicit README
promise. Do not use Bats, GNU-only utilities, associative arrays, `mapfile`, or a
package-manager install in the test harness.

Exit gate:

- The runner is green from a clean clone on Linux and macOS.
- The suite proves isolation by installing a sentinel in the fake home and
  failing if a command resolves the invoking user's real home.
- Known behavior is characterized without weakening assertions to accommodate
  the bugs addressed in later phases.

### Phase 2: restore teardown ownership for #8

This is a small boundary correction and can begin in parallel with Phase 3/4
development after the Phase 1 harness lands.

Change:

- `bin/rzr-teardown.sh`: remove the `rzr_unlanded_reasons` call and all
  checkout-policy messaging. Continue resolving an exact task, optionally close
  its tab, remove live meta/runtime/turn files, and preserve `tasks/<id>/`.
- `bin/rzr-lib.sh`: delete `rzr_unlanded_reasons` when its final caller is gone.
- `bin/rzr-control.sh`: restart calls teardown without `--force`; update comments
  to say the same checkout is preserved because teardown never touches it.
- `README.md`, `templates/watchtower.md`, and
  `.agents/skills/rozoro/SKILL.md`: remove claims that teardown proves work is
  landed or that force discards work; state that acceptance and delivery remain
  driver/repository policy.

Keep accepting `--force` for one compatibility window as a deprecated no-op
that warns `--force is no longer required; teardown does not inspect Git`.
Remove it from documented usage. `--keep-tab` is unchanged.

Add lifecycle tests for a non-Git cwd, clean repository without upstream, dirty
repository, repository with an unpushed commit, unknown task, failed/already-gone
tab close, `--keep-tab`, durable task folder survival, and restart with preserved
profile/cwd. Assert that no Git command is invoked by teardown itself.

Exit gate: all #8 acceptance criteria pass through the fake Herdr and temporary
Git fixtures, and no remaining code or docs imply that tab lifecycle determines
delivery state.

### Phase 3: make status pure and turn-aware for #9

Build this phase on the handoff and watcher fixtures from Phase 1.

Change:

- Add `bin/rzr-handoff.py` as the single canonical parser/projector.
- `bin/rzr-status.sh`: remove `.seen-blocks`, `new_block`, and write-on-read
  behavior; combine the pure handoff projection with runtime and turn observation
  files; emit schema-v2 JSON and explicit human labels.
- `bin/rzr-ack.sh`: obtain canonical block count from the shared parser and write
  `.acked-blocks` with temp-file-plus-rename.
- `bin/rzr-lib.sh`: add atomic helpers for runtime and turn JSON, compatibility
  fallback for `.status`, and read-only helpers for their fields.
- `bin/rzr-watch.sh`: maintain a per-process working-turn baseline; write runtime
  facts on reconciliation/edges and turn facts only on observed
  `working -> settled` transitions. Preserve per-process event deduplication so
  overlapping `--once` watchers both wake.
- `bin/rzr-list.sh`: label `RUNTIME` and `TASK` separately.
- `bin/rzr-teardown.sh`: remove all ephemeral runtime/turn files during reap.
- `README.md`, `templates/watchtower.md`, and the rozoro skill: replace
  `NEW/same` guidance with the watcher-owned missing-report signal; consistently
  describe runtime done, handoff done, and acceptance as different facts.

Extend tests with:

- zero blocks, one done block, buried open item, FIFO acknowledgement, malformed
  fields, invalid verdict, non-turn H2 headings, duplicate/decreasing turn
  numbers, and cursor edge cases;
- byte-for-byte file snapshots around repeated human and JSON reads proving
  status purity;
- two independent readers returning equivalent facts;
- working-to-settled with and without a new canonical block;
- no missing report on initial settled reconciliation or settled-to-settled
  event;
- overlapping watchers writing a valid, non-torn turn projection;
- runtime mirror absent, legacy-only, and current cases;
- JSON schema/enum assertions and human warning assertions.

Exit gate: all #9 acceptance criteria pass, `.seen-blocks` is no longer read or
written, and no `status` invocation mutates the task or state tree.

### Phase 4: make linking capability-aware for #10

This phase can be implemented in parallel with Phase 3 once Phase 1 is merged.
Coordinate edits to `rzr-lib.sh`, `README.md`, the skill, and lifecycle tests;
rebase one phase before merging rather than duplicating helpers.

Change:

- `bin/rzr-lib.sh`: add session-descriptor normalization, atomic JSON writing,
  Herdr session response extraction, and the allowlisted resume capability table.
- `bin/rzr-link.sh`: read harness/pane/cwd from task metadata, prefer public
  `agent_session`, use the Claude marker fallback only for Claude, respect
  `CLAUDE_CONFIG_DIR`, and write schema v2 or an explicit unsupported descriptor.
- `bin/rzr-start.sh`: treat unsupported linking as a completed capability check;
  retry only a supported harness whose identity may not have appeared yet. Do
  not print a Claude transcript warning for Codex, Copilot, or Pi.
- `bin/rzr-resume.sh`: normalize v1/v2 descriptors, verify the descriptor against
  the capability table, dispatch validated argv, and fail with a precise
  unsupported/session-unavailable reason. Preserve live-task refusal and never
  fall back to cold spawn.
- `bin/rzr-spawn.sh`: keep harness metadata authoritative and clarify comments;
  do not move terminal restoration into `session.json`.
- `README.md` and the rozoro skill: distinguish portable handoff continuation
  from harness-specific exact conversation resume and document schema/capability
  diagnostics.

Add fixtures for the observed 0.8.x response shape
`.result.agent.agent_session` and defensive alternate nesting. Test Herdr-first
Claude linking without any transcript directory, delayed identity, Claude marker
fallback in default and alternate config roots, multiple same-cwd transcripts,
non-Claude starts with no Claude scan, mismatched reported agent, v1 descriptor
read compatibility, v2 Claude resume argv, malformed descriptors, unsupported
harnesses, and live-task refusal.

Exit gate: all #10 acceptance criteria pass; every new descriptor names its
capability explicitly; no non-Claude path touches Claude storage; legacy Claude
links resume unchanged.

### Phase 5: complete #11 and documentation

After Phases 2-4 merge, audit the issue #11 coverage list against tests rather
than assuming the feature PRs covered it. Add any missing transport and failure
fixtures, especially transient `agent_pane_busy`, terminal start failure,
data/control separation, malformed subscription acknowledgement, socket close,
and lock cleanup on failing commands.

Update `README.md` with one automated command, supported platforms, dependencies,
and a short table separating automated coverage from any retained manual Herdr
smoke checks. CI must use the same command developers run. Close #11 only when
its full acceptance criteria are present and green.

## Dependency and delivery order

```text
#11 foundation
    |
    +--> #8 teardown boundary ---------+
    |                                  |
    +--> #9 status/watch architecture -+--> #11 coverage closeout
    |                                  |
    +--> #10 session capabilities -----+
```

- Phase 1 is the only hard prerequisite. It establishes shared fixtures and CI.
- #8 and #10 have no behavioral dependency on #9 and can proceed in parallel.
- #9 owns runtime/turn file naming and the handoff parser; land it before any
  follow-up that consumes those structures.
- #9 and #10 both touch `rzr-lib.sh`, docs, and test helpers. Assign different
  implementation branches but serialize merges and re-run the full matrix after
  rebasing the second.
- #11 is intentionally delivered in slices: infrastructure first, coverage in
  each behavior PR, final audit last. Do not create a separate testing framework
  per issue.

Recommended PR boundaries:

1. `test: add isolated shell protocol harness` — references #11, does not close it.
2. `fix: remove Git policy from teardown` — closes #8 after its tests pass.
3. `fix: separate runtime, task, and turn status` — closes #9 after its tests pass.
4. `feat: make session linking capability-aware` — closes #10 after its tests pass.
5. `test: complete lifecycle regression coverage` — closes #11 after the audit.

## Compatibility and migration

- Existing task directories and append-only handoffs remain valid when they use
  the documented `## turn <n>` protocol headings.
- Existing `.acked-blocks` values retain FIFO semantics. The writer becomes
  atomic; the value format does not change.
- `.seen-blocks` is obsolete and ignored. Leaving the file is harmless; teardown
  or a later housekeeping release may remove it.
- `state/<id>.status` remains a plain compatibility token for one window while
  `runtime.json` becomes structured authority. No in-place conversion is needed.
- Status JSON moves to `schema_version: 2`. `verdict` is temporarily retained,
  but `new_block` is deliberately removed because preserving its meaning would
  preserve the bug. Consumers migrate to `handoff_verdict`, `task_status`,
  `runtime_status`, and `turn_report_status`.
- Existing schema-v1 `session.json` remains readable through normalization.
  Reads do not rewrite it; the next successful explicit link may create v2.
- `rzr-link.sh <id> <cwd>` remains accepted while callers migrate to metadata.
- `rzr-teardown.sh --force` remains accepted as a warning no-op for one window.
  It is no longer shown in help or docs.
- The Herdr requirement remains 0.8.x. Missing `agent_session` is a supported
  condition, not a fatal compatibility failure.
- Exact resume remains enabled only for verified harnesses. Recording a Herdr
  session identity does not itself enable resume.

## Verification and rollout

For every implementation PR:

1. Run `./tests/run.sh` locally with no Herdr server dependency.
2. Run `bash -n` over every shell script and Python syntax compilation through
   the runner.
3. Confirm `git diff --check` and review changed help/README/skill text against
   actual CLI behavior.
4. Run both Linux and macOS CI jobs.
5. Inspect the changed JSON with `jq` fixtures and assert schema versions and
   `null` handling, not only string fragments.

Before the final #11 closeout, perform one optional manual smoke pass in a
disposable `ROZORO_HOME` with Herdr 0.8.2:

- Start one Claude task and one unsupported-resume harness task.
- Verify Claude Herdr metadata linking when the integration reports a session;
  otherwise verify the configured fallback and diagnostic.
- Observe `working -> done` once with and once without a new handoff block.
- Call status repeatedly and confirm no files change.
- Teardown from a dirty disposable checkout and confirm the checkout and durable
  task folder remain.

The manual smoke pass validates integration shape; it must not replace automated
fixtures or be required for contributors.

Rollout is additive except for status JSON v2. Announce that break in the #9 PR,
retain the listed aliases/fallbacks, and remove compatibility surfaces only in a
later, separately documented change after downstream consumers have migrated.

## Risks and mitigations

| Risk | Mitigation |
| --- | --- |
| Herdr 0.8.x response nesting varies | Parse the documented `AgentInfo` shape first, retain defensive fixture-backed fallbacks, validate agent/harness before use |
| Agent status settles just before a handoff write becomes visible | The protocol requires append-before-turn-end; document that invariant and keep the classification tied to the edge. If real fixtures demonstrate ordering lag, add a bounded single reconciliation delay in the watcher, never reader polling |
| Overlapping watchers race on projection files | Write complete deterministic JSON through process-unique temp files and atomic rename; never use a shared increment cursor |
| Canonical heading enforcement rejects historical prose | Treat zero canonical turns with legacy verdict-bearing H2 blocks as a surfaced `protocol-error` containing remediation; never silently discard data |
| JSON v2 breaks a consumer | Version the payload, retain `verdict` temporarily, document exact replacements, and test both new and compatibility fields |
| Session descriptor becomes a command-injection surface | Store argv arrays, reject controls/newlines in identity, validate harness/kind/value, and dispatch only an allowlisted capability without `eval` |
| Fake Herdr drifts from upstream | Keep raw 0.8.2 response fixtures beside tests and perform the optional release smoke pass; test both primary and defensive nesting |
| Test processes or sockets leak | Central trap registry kills children, waits for them, and removes only the per-test temporary directory on all exits |
| Parallel PRs conflict in shared glue/docs | Land the foundation first, assign issue-owned files, serialize #9/#10 merges, and require a full post-rebase run |

## Final acceptance criteria

The four-issue program is complete only when all of the following are true:

- Teardown succeeds for non-Git, no-upstream, dirty, and ahead-of-upstream
  disposable checkouts without a force flag, while unknown tasks fail closed,
  `--keep-tab` is unchanged, and durable task data survives.
- No production teardown/control code invokes Git or claims to establish landed,
  merged, accepted, or discarded state.
- Repeated status reads are file-system pure and produce stable facts.
- Missing handoff is recorded only for an observed working-to-settled turn with
  no appended canonical block.
- Independent readers and overlapping watchers do not suppress one another or
  corrupt runtime, turn, or acknowledgement files.
- Earlier open items survive later done blocks and repeated reads until explicit
  acknowledgement.
- Human and JSON output separately name runtime status, task status, handoff
  verdict, and turn report status; acceptance is absent from those projections.
- Handoff parsing has one implementation and deterministic errors for malformed
  protocol data and Markdown headings.
- Herdr-reported session identity is preferred and fixture-covered; Claude's
  fallback honors `CLAUDE_CONFIG_DIR`; non-Claude starts never scan Claude data.
- Schema-v1 Claude links remain resumable, schema-v2 descriptors use validated
  argv, and unsupported resume fails explicitly without cold-spawning.
- `./tests/run.sh` passes from a clean clone on Linux and macOS without contacting
  a real Herdr server, harness session store, user rozoro home, or developer
  checkout.
- CI runs the same command, shell/Python syntax checks are included, cleanup is
  proven on failure paths, and README manual checks are clearly labeled as such.
- Repository README, watchtower template, and rozoro skill agree with the shipped
  lifecycle, status, and conversation-capability boundaries.
