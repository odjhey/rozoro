# Cross-harness watcher wake/notification plan

Date: 2026-08-22

Repository baseline: `/home/odz/packages/rozoro` at `4dd14e1`

Scope: written implementation and validation plan only; no product code was changed.

## Recommendation

Build one harness-neutral, long-lived notification pipeline with a durable pending ledger, then use a small last-mile adapter per watchtower harness:

- Codex: `codex queue --thread "$CODEX_THREAD_ID" --message <fixed-nudge>`.
- Claude: `herdr agent prompt "$HERDR_PANE_ID" <fixed-nudge>`, deferred until the driver pane is `idle` or `done`.
- Pi: a Pi extension calling `pi.sendMessage(..., { triggerTurn: true, deliverAs: "followUp" })`.

Do not define success as watcher stdout being produced. Success is: an actionable crew transition is durably recorded, a wake is accepted by the correct driver, the driver begins a reconciliation turn, and the notification is explicitly acknowledged after reconciliation. Delivery should be at least once; duplicate fixed nudges are acceptable, lost actionable notifications are not.

The common command may be exposed as `rozoro watch --wake`, but backend selection must use an explicit, validated driver registration. It must not choose Codex merely because `CODEX_THREAD_ID` happens to exist: a Claude or Pi process launched from a Codex environment can inherit that stale variable and wake the wrong conversation.

## What exists today

### Common Herdr sensor

Herdr 0.8.2, protocol 20 is installed. Its `pane.agent_status_changed` subscription is harness-neutral and reports `idle`, `working`, `blocked`, `done`, or `unknown` for Claude, Codex, Pi, and other detected agents. `herdr agent get/list` additionally exposes `interactive_ready` and `state_change_seq`.

`bin/herdr-eventwait.py` subscribes directly to that push stream and `bin/rzr-watch.sh`:

1. resolves task ids to panes;
2. takes an initial status snapshot;
3. subscribes to subsequent status events;
4. deduplicates per watcher process; and
5. mirrors the last status to `$ROZORO_HOME/state/<id>.status`.

This is a good common sensor, but it is not yet a reliable notification service. It watches a static task set, has a documented snapshot-before-subscribe race, stops on socket loss, and `--once` creates an unmonitored gap between delivery and the driver's next re-arm.

### Codex

Installed Codex CLI: 0.149.0. The local CLI provides `codex queue --thread <uuid-or-name> --message <text>`, and the resident session exports `CODEX_THREAD_ID`. Current master implements `rzr-watch.sh --wake-codex`, sending a fixed content-free nudge on `idle`, `done`, or `blocked` and ignoring initial/`working` observations.

This is the strongest external wake API of the three harnesses. Current automated coverage uses a fake `codex` executable; there is no live end-to-end assertion that an idle or busy Codex watchtower actually starts the expected reconciliation turn. Official OpenAI documentation search did not surface a public page defining `codex queue` semantics, so runtime capability detection and a pinned live smoke test are required rather than assuming the command exists on every installed Codex version.

### Claude

Installed Claude Code: 2.1.6. Its CLI exposes interactive resume and headless `--print --input-format stream-json`, but no external `queue` or `remote-control` command. Headless stream-json is not a drop-in wake channel for the existing interactive Herdr-hosted watchtower and would require replacing its launch/runtime model.

Herdr supplies the practical live-session adapter: `herdr agent prompt <pane> <text>` submits a prompt atomically to a live Claude pane. It accepts prompts while an agent is working and rejects a blocked agent. For watcher notifications, prompting a working Claude session is the wrong default because it may queue or steer terminal input according to TUI behavior. The notifier should retain the pending notification and submit only after Herdr reports the Claude driver `idle` or `done`; if blocked, it should keep the pending record and optionally raise `herdr notification show` for human visibility.

### Pi

Installed Pi: 0.84.2 (`@earendil-works/pi-coding-agent`). Pi has two relevant APIs:

- RPC mode accepts JSONL `prompt`, `steer`, and `follow_up` commands on stdin, but the existing interactive TUI is not running in RPC mode.
- Its extension API provides the exact desired interactive semantics: `pi.sendMessage` with `deliverAs: "followUp"` waits for current work to finish, while `triggerTurn: true` starts a turn when idle. Extensions can own background resources from `session_start` through an idempotent `session_shutdown` cleanup.

Therefore Pi should use an in-process extension, not terminal typing and not a foreground bash tool. A project-local prototype exists on the unmerged `pi-harness-parity` branch, along with broader Pi spawn/link/resume support. Master still documents Pi launch mapping as unverified and lacks Pi exact session lifecycle support, so Pi parity is a prerequisite, not an assumption.

### Test baseline

Master contains 14 watcher/event-stream Bats cases and 43 Bats cases overall. They cover the raw subscription, deduplication, overlapping one-shot watchers, and fake Codex wake success/failure. They do not cover Claude delivery, Pi extension behavior, durable/coalesced notifications, reconnects, dynamic task membership, driver-busy behavior, or a real harness round trip.

The full suite could not run on this machine because Bats 1.14.x is absent. Shell syntax and Python compilation checks passed. This must be fixed before implementation starts so the baseline is known rather than inferred.

## Reliability gaps and constraints

1. **Buffered stdout is not a wake.** Once a model turn ends, output from a background tool is not a portable way to initiate another turn.
2. **`--once` has a re-arm hole.** An edge after the watcher exits but before the next watcher subscribes can be missed. Initial observations intentionally do not wake, so level reconciliation does not close that hole.
3. **Snapshot-before-subscribe has a race.** Current `rzr-watch.sh` reads status before opening the event subscription. A transition inside that interval may be absent from both the baseline and future stream.
4. **Herdr events are not replayed and omit sequence numbers.** The subscription event schema has status but no `state_change_seq`; the latest agent snapshot has the sequence. Exact event replay cannot be built from the current stream alone.
5. **Task membership is static per subscription.** Tasks created or reaped after watcher startup require a safe resubscribe plus reconciliation.
6. **Wake delivery and reconciliation are conflated.** A successful CLI invocation only means the nudge was accepted. It does not prove the driver ran, read all handoffs, or acknowledged them.
7. **Duplicates are currently unconstrained.** Overlapping watchers deliberately see the same edge. Without a per-driver ledger they can each create a driver turn.
8. **Driver identity can be ambiguous.** Nested harnesses can inherit `CODEX_THREAD_ID` and `HERDR_PANE_ID`. Environment-variable priority alone can address the wrong driver.
9. **Busy and blocked semantics differ.** Codex has a queue; Pi explicitly supports follow-ups; Claude has no documented external queue and Herdr rejects blocked prompts.
10. **Process ownership is underspecified.** A watcher launched from a foreground tool call can occupy the turn; a casually backgrounded child may lose stdio or die with its parent. The monitor needs an owned lifecycle and health check.
11. **Pi discovery is location/trust dependent.** A project extension is not guaranteed to load if Pi starts outside the repo or without project approval. The watchtower launcher should pass the extension explicitly.
12. **Runtime settlement is not task completion.** `idle`/`done` means a harness turn settled. The authoritative workflow result remains the append-only handoff plus `rzr-status` open-item logic.

## Target architecture

### 1. Sensor and reconciliation layer

Keep Herdr as the common runtime sensor. Evolve the watcher into a long-lived monitor rather than repeatedly launching `--once`.

- Subscribe to all currently tracked crew panes.
- Reconcile current `agent get/list` state immediately after subscription and on every reconnect.
- Track each pane's latest `state_change_seq` from snapshots. If the sequence advances while the observed status is unchanged, conservatively schedule reconciliation because one or more transitions may have occurred during an outage or subscribe race.
- Rescan `state/*.meta` when task files change, with a periodic fallback scan because filesystem notifications can be coalesced or dropped. Debounce changes, resubscribe, then level-reconcile all panes.
- Reconnect on socket close with bounded exponential backoff and jitter. The monitor remains degraded-but-live and exposes the last error.
- Treat `working -> idle|done|blocked` as actionable. Treat a persistently `unknown` pane as degraded after a threshold. Treat unexpected disappearance as actionable, but suppress a close explicitly initiated by accepted teardown.
- Also reconcile handoff block counts/open items on startup and reconnect. The append-only handoff is the durable backstop when a runtime edge was not observable.

If Herdr later adds `state_change_seq` to subscription events or a replay cursor, consume it and tighten the guarantee; do not block the initial implementation on that upstream enhancement.

### 2. Durable per-driver notification ledger

Add a per-watchtower registration and ledger under `$ROZORO_HOME/watchtowers/<driver-id>/`:

- `target.json`: schema version, driver harness, chosen backend, immutable thread/pane identity, owner/session identity, and creation time.
- `pending.json`: monotonically increasing generation, affected task ids, last observed statuses/sequences, delivery state, retry count, and timestamps.
- `ack`: last generation reconciled by the driver.
- `health.json`: monitor pid/lease, subscription state, last event, last delivery, and last error.

Write complete files atomically and with user-only permissions. Persist a new generation before attempting delivery. If delivery succeeds but the process dies before recording success, a duplicate wake after restart is acceptable. Never put task prompts, handoff text, terminal output, or arbitrary event strings into the wake message.

Coalesce any number of edges while `generation > ack` into one outstanding fixed nudge. New edges remain represented in `pending.json`. After the driver reconciles and acknowledges generation N, immediately deliver another nudge if the ledger advanced to N+1 during reconciliation.

Add a `rozoro reconcile` operation that snapshots the pending generation, runs the existing `rzr-status --json` logic for every affected/live task, reports vanished tasks and monitor health, and acknowledges only the generation it actually processed. Existing handoff OPEN-item acknowledgement remains separate; reading a notification must not silently resolve a crew's `needs-action` or `blocked` verdict.

### 3. Explicit driver registration and backend adapters

Register the driver at watchtower startup. Validate that the target is live and matches the declared harness. `--wake auto` may use the registration, but must fail on ambiguity rather than inspect raw environment variables in priority order.

#### Codex adapter

- Preconditions: declared harness is Codex; thread id is non-empty; `codex queue --help` succeeds.
- Delivery: queue the fixed text `Rozoro notification pending; run rozoro reconcile.` to the registered thread.
- Busy behavior: queue immediately; Codex owns serialization.
- Failure behavior: retain pending generation, retry with backoff, and surface a health error. If the driver is Herdr-hosted and native queue is unavailable, an explicit configuration may permit the Herdr adapter; never silently change targets.

#### Claude adapter

- Preconditions: declared harness is Claude; registered Herdr pane exists, reports Claude, and is `interactive_ready`.
- Delivery: if driver is `idle` or `done`, call `herdr agent prompt` with the fixed nudge. If `working`, retain and wait for the driver's settled edge. If `blocked`, retain, show a human notification, and retry after unblocking.
- Session changes: pane identity is not durable across teardown/resume, so startup/resume must replace the registration. Never find a target by focus, newest pane, or cwd alone.

#### Pi adapter

- Load the extension explicitly from a blessed watchtower launcher; do not rely solely on project discovery.
- Start the monitor resource during `session_start` and stop child processes, watchers, and timers during `session_shutdown`.
- On a pending generation, call `pi.sendMessage` with a fixed custom message, `triggerTurn: true`, and `deliverAs: "followUp"`.
- Busy behavior: Pi queues the follow-up after the current run. Idle behavior: Pi starts a turn immediately.
- Expose `/rozoro-monitor status|on|off` and a visible health/status indicator. A normal Pi coding session must not auto-start the monitor; require the watchtower marker or an explicit flag.
- Use periodic task reconciliation in addition to filesystem watching, and test extension reload/session switching so there is never more than one owned child.

### 4. CLI and compatibility shape

- Keep `rzr-watch.sh`'s existing event-stream output for scripts.
- Introduce a long-lived `rozoro monitor start|status|stop` and `rozoro reconcile` rather than asking agents to manage detached shell syntax themselves.
- Make watchtower launch commands register the exact backend/target and start or attach to the monitor.
- Retain `--wake-codex` as a compatibility alias for one release. Document it as one-shot/best-effort until it routes through the ledger, then deprecate it in favor of registered `--wake`/monitor behavior.
- Add machine-readable health and reconciliation output so watchtower prompts do not parse prose.
- Keep polling (`rzr-list`, `rzr-status`) as the documented degraded fallback.

## Implementation sequence

### Phase 0 — establish prerequisites

1. Install/pin Bats 1.14.0 and run the current master suite before changes.
2. Land or rebase the Pi harness-parity work first: model/thinking/trust mapping, explicit system prompt, native session id/link, exact resume, and real lifecycle fixtures.
3. Record the supported minimum versions after live probes: Herdr protocol/version, Codex with `queue`, Claude with `agent prompt` support through Herdr, and Pi with `sendMessage` follow-up semantics.

Exit gate: baseline green on Linux and macOS; Pi can be launched, linked, torn down, and resumed independently of notification work.

### Phase 1 — separate notification policy from event transport

1. Preserve `herdr-eventwait.py` as a transport projection.
2. Add normalized event records containing task id, pane id, old/new status, initial flag, observation time, and snapshot sequence where available.
3. Add the target/ledger schemas, atomic state helpers, capability diagnostics, and fixed-message enforcement.
4. Add long-lived reconnect, dynamic-task resubscription, periodic reconciliation, and monitor health.

Exit gate: fake-server tests prove no event storm, no static membership limitation, recovery after disconnect, and durable pending state before any real harness wake is enabled.

### Phase 2 — migrate Codex to the ledger

1. Route the existing Codex queue adapter through registered identity and the pending/ack state machine.
2. Keep old CLI syntax working.
3. Add live idle, busy, restart, and duplicate-delivery smoke tests on the pinned Codex version.

Exit gate: current Codex behavior remains compatible and every accepted edge is either acknowledged or visibly pending/degraded.

### Phase 3 — enable Claude

1. Add the Herdr-prompt adapter with driver-status gating.
2. Register/re-register pane identity in Claude watchtower bootstrap and resume flows.
3. Exercise working, idle, blocked, unblocked, pane-gone, and nested-environment cases using a real Claude TUI.

Exit gate: no prompt is injected into a working or blocked Claude driver, and a retained notification wakes it once it settles/unblocks.

### Phase 4 — enable Pi

1. Add the explicit watchtower extension/launcher after Pi lifecycle parity lands.
2. Have the extension consume the same pending generations and acknowledge delivery without conflating it with reconciliation acknowledgement.
3. Test ownership through `/new`, `/resume`, `/fork`, extension reload, shutdown, and monitor restart.

Exit gate: the Pi editor stays responsive, busy notifications become follow-ups, idle notifications trigger a turn, and only one monitor child exists per session.

### Phase 5 — make generic wake the documented default

1. Run the full 3-by-3 driver/crew live matrix.
2. Publish capability/health diagnostics and degraded fallback behavior.
3. Update README, watchtower template, skill text, and help output together.
4. Roll out generic `--wake` first as opt-in, then default it only after one release of telemetry-free operational feedback and no unresolved loss/duplication defects.

Rollback is per adapter: disable automatic delivery while leaving the durable ledger and polling reconciliation intact.

## Validation plan

### Deterministic unit and component tests

Extend the fake Herdr server and fake harness executables to cover:

- exact subscription framing and multi-pane attribution;
- initial reconciliation without a startup wake;
- transition during startup/resubscribe, including sequence advancement with unchanged final status;
- dynamic task addition/removal and debounced resubscription;
- socket close before/after acknowledgement, reconnect backoff, and recovery;
- duplicate/overlapping watcher events coalescing into one pending generation;
- persist-before-deliver ordering and restart after every state-machine write boundary;
- delivery success, rejection, timeout, and retry without dropping pending state;
- event burst while a prior generation is delivered but unacknowledged;
- acknowledgement of N while N+1 arrives concurrently;
- stale/ambiguous target refusal, including both Codex and Herdr variables present;
- fixed payload enforcement and rejection of arbitrary task/handoff content;
- Claude idle delivery, working deferral, blocked deferral, unblocked retry, and gone-pane failure;
- Codex native queue selection and optional explicit Herdr fallback;
- Pi extension idle trigger, busy follow-up, monitor child crash/restart, task watcher rescan, and idempotent shutdown/reload;
- Bash 3.2 compatibility, atomic non-torn files, and restrictive permissions.

Use dependency-injected clocks/randomness for retry tests; do not sleep in the suite.

### Real integration tests without model calls

On each supported OS:

1. Verify exact installed CLI capabilities using `--help` and record versions.
2. Verify Herdr detects each interactive harness and returns the expected pane, harness, status, `interactive_ready`, and changing `state_change_seq`.
3. Verify monitor registration always selects the current declared driver even when unrelated/stale harness environment variables are also present.
4. Verify process ownership: monitor survives the launching command, exposes health, and exits cleanly on explicit stop/session shutdown.

### Live end-to-end acceptance matrix

Run all nine combinations of driver harness and crew harness:

| Driver | Crew variants | Expected last mile |
|---|---|---|
| Codex | Codex, Claude, Pi | native Codex queue |
| Claude | Codex, Claude, Pi | settled Herdr pane prompt |
| Pi | Codex, Claude, Pi | Pi extension follow-up/trigger |

For each combination, use a disposable worktree under `./.worktrees/`, a unique task id, and a deterministic crew prompt that writes a valid handoff after a controlled delay. End the driver's turn before the crew settles. Assert:

1. the crew edge reaches the ledger;
2. the correct driver, and no other session, starts a new turn;
3. `rozoro reconcile` observes the new handoff/verdict;
4. the processed generation is acknowledged; and
5. no extra turn occurs after acknowledgement.

Then repeat representative combinations for:

- edge while driver is busy;
- edge while Claude is blocked, followed by unblock;
- 20 near-simultaneous settled edges across multiple tasks;
- monitor kill before delivery, after delivery, and before acknowledgement;
- Herdr socket restart and task creation during the outage;
- driver session resume/re-registration;
- crew disappearance without handoff;
- missed handoff followed by the next crew turn;
- two overlapping monitor processes attempting the same generation.

Record event, persistence, delivery, driver-working, reconcile, and ack timestamps. Targets for a local healthy system: event-to-ledger under 1 second, first delivery attempt under 2 seconds, and driver transition to working under 10 seconds. Timeouts are test ceilings, not correctness substitutes; retained pending state is required on every timeout.

### Cross-platform and upgrade validation

- Linux with Bash 5 and macOS with stock Bash 3.2.
- Pinned current versions plus minimum supported versions of all four CLIs.
- Upgrade probes that intentionally remove `codex queue`, Pi extension options, or Herdr fields and verify a clear preflight failure/degraded status rather than silent fallback.
- A 30-minute soak with repeated task churn, burst completions, monitor reconnects, and zero unacknowledged lost generations or runaway CPU/process growth.

## Acceptance criteria

The feature is complete only when all of the following are true:

1. A settled or blocked edge from any Codex, Claude, or Pi crew can initiate reconciliation in a resident Codex, Claude, or Pi watchtower.
2. Every actionable observation is durably pending until a driver explicitly reconciles it; process or socket restarts do not erase it.
3. Delivery is at least once and coalesced: bursts do not create unbounded turns, and duplicates cannot lose work.
4. The wake is addressed using validated immutable identity. Nested/stale environment variables cannot wake another session.
5. Codex queues while busy; Pi queues a follow-up while busy; Claude waits until settled. Blocked Claude notifications remain pending and visible.
6. Initial startup baselines do not cause a wake unless an unacknowledged handoff/open item already exists.
7. New tasks are watched without restarting the watchtower manually, and socket/task churn is reconciled.
8. Wake text is fixed and content-free. Untrusted task ids, prompts, handoffs, and terminal output never become driver instructions.
9. `monitor status` clearly distinguishes healthy, pending, delivered-unacknowledged, retrying, blocked-target, and disconnected states.
10. Existing `--wake-codex` users remain compatible during the migration window.
11. Unit/component tests, the nine live matrix cases, busy/blocked/restart/burst scenarios, and Linux/macOS CI pass on pinned versions.
12. README, watchtower prompt, skill, CLI help, and behavior describe the same lifecycle and degraded fallback.

## Explicit non-goals

- Wake delivery does not mean the crew task is correct, accepted, or ready to reap.
- OS/Herdr visual notifications are a fallback for humans, not proof that a model turn ran.
- This plan does not replace the append-only handoff or its OPEN-item acknowledgement model.
- This plan does not change Claude watchtowers to headless stream-json or Pi watchtowers to RPC mode.
- This plan does not promise exactly-once model turns; it promises durable at-least-once notification with safe coalescing and explicit acknowledgement.

## Evidence consulted

- Current repository: `bin/rzr-watch.sh`, `bin/herdr-eventwait.py`, `bin/rzr-send.sh`, `tests/watch.bats`, `tests/eventwait.bats`, `README.md`, and the repository's rozoro skill.
- Current and pending repository history: master `4dd14e1`, Codex wake commit `0adaa10`, and unmerged Pi parity/watchtower commits on `pi-harness-parity`.
- Installed CLI help and runtime schemas: Herdr 0.8.2/protocol 20, Codex CLI 0.149.0, Claude Code 2.1.6, and Pi 0.84.2.
- Installed Pi package primary documentation: `docs/rpc.md`, `docs/extensions.md`, and exported extension API types for `sendMessage`.
- Live read-only Herdr inspection confirmed `HERDR_PANE_ID`, `CODEX_THREAD_ID`, harness detection, `interactive_ready`, and `state_change_seq` are present in this environment.

No live model wake was sent during this scout, so the live end-to-end behavior remains an explicit rollout gate rather than an unverified claim.
