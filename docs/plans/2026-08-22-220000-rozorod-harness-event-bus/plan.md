# Add a harness-native Rozoro event bus and resident monitor

Status: accepted implementation plan

Created: 2026-08-22 22:00:00 Asia/Manila

Scope: documentation-only implementation plan for a resident Rozoro monitor, harness adapters, durable lifecycle state, and coalesced watchtower notifications

## Outcome

Rozoro gains one resident local service (`rozorod`, name provisional) that owns
crew/watchtower lifecycle normalization, durable event sequencing, projection,
notification coalescing, and wake delivery. Pi and Claude become first-class
harness adapters speaking one Rozoro protocol over a local Unix-domain socket.
Codex and Copilot remain supported by the architecture but are implementation
follow-ups after the Pi + Claude path is proven.

The target architecture is:

```text
 Claude hooks                  Pi extension
      │                             │
      │ harness-native lifecycle    │ harness-native lifecycle
      └──────────────┬──────────────┘
                     ▼
          ~/.rozoro/monitor.sock
                     │
              ┌──────▼───────┐
              │   rozorod    │
              │              │
              │ ingest       │
              │ normalize    │
              │ reduce       │
              │ persist      │
              │ coalesce     │
              │ route/wake   │
              └──────┬───────┘
                     │
          Herdr host/liveness/actuator
```

Rozoro must no longer infer semantic completion from Herdr `idle`/`done` alone.
Herdr remains the process/session host, a liveness source, and a last-mile prompt
actuator where needed. Harness-native adapters own the richer facts that Rozoro
needs to distinguish a truly settled turn from a main agent that is temporarily
idle while harness-owned background/subagent work remains active.

The service accepts every normalized lifecycle event durably, reduces those
facts into current task/session projections, and coalesces only the resulting
watchtower notifications. Event ingestion itself is never debounced or dropped.

## Why this change

The current implementation has two architectural splits that make reliable
watchtower updates difficult:

1. Pi uses a repository extension that directly owns an `rzr-watch --json`
   subprocess and injects a model follow-up when a projection says
   `action.required=true`.
2. Claude/Codex use a separate registered wake path backed by the durable
   generation/delivered/ack ledger.

Those paths do not share one delivery contract. The Pi path is less durable, and
its extension currently restarts the fleet watcher when `state/*.meta` changes,
which creates unnecessary subscription churn and edge-loss/replay hazards.

There is also a deeper semantic problem: Herdr foreground state cannot certify
that a harness has no owned background work. A Claude main turn may reach an
idle/stopped foreground state while Claude-native subagents or other background
jobs are still active. Current Rozoro Stage 1 explicitly records this limitation:
Herdr 0.8.2 does not expose normalized background-job activity, so a `waiting`
report cannot be certified from Herdr alone.

The fix is not another Herdr-state heuristic. The semantic boundary must move up
to harness-native adapters, which normalize richer lifecycle information into a
single Rozoro protocol.

## Design principles

### 1. Normalize harness semantics, not Herdr status names

The core state model must use concepts Rozoro actually needs:

```text
foreground:
  running | stopped | unknown

background:
  active | clear | unknown

availability:
  busy | waiting-background | quiescent | blocked | gone | unknown
```

Recommended derivation:

```text
foreground=running
  -> busy

foreground=stopped + background=active
  -> waiting-background

foreground=stopped + background=clear
  -> quiescent

foreground/background uncertified
  -> unknown
```

Task/report semantics remain independent axes. `verdict: done`,
`needs-action`, `failed`, etc. must not be collapsed into runtime availability.
A quiescent crew can still have an invalid/missing report; a reported `done`
turn is still not user acceptance.

### 2. Accept every event; coalesce only wakeups

Event correctness and notification interruption are separate concerns.

```text
raw lifecycle events
        ↓ persist all
session/task reducer
        ↓ current projection
notification scheduler
        ↓ cluster/coalesce
one watchtower wake
```

A burst such as:

```text
crew A -> quiescent
crew B -> quiescent
crew C -> blocked
crew D -> quiescent
```

must produce four durable facts but may produce one watchtower notification:

```text
3 crews completed; 1 needs attention
```

The daemon should keep wake payloads deterministic and content-free. The
watchtower gets authoritative detail by reconciling structured state; the daemon
is the state/reliability layer, not a second judgment agent.

### 3. At-least-once delivery with explicit generations

Preserve and generalize the current durable wake semantics:

```text
generation  = highest actionable projection generation persisted
delivered   = highest generation for which a wake was attempted/succeeded
ack         = highest generation the watchtower reconciled
```

The critical distinction is:

- **observed**: event/projection is durably committed;
- **delivered**: the watchtower was nudged;
- **reconciled**: the watchtower consumed authoritative state and acked through a
  snapshotted generation.

If generation 52 is delivered but the watchtower crashes before reconciliation,
52 remains unacked and must be redeliverable after recovery. Duplicate fixed
nudges are acceptable; silently lost actionable generations are not.

### 4. One semantic owner

Exactly one local Rozoro monitor owns:

- normalized lifecycle ingestion;
- durable ordering/deduplication;
- task/session projection;
- notification coalescing;
- watchtower pending generations;
- retry/reconnect state;
- Herdr membership/liveness reconciliation.

Pi extensions, Claude hooks, CLI commands, and later Codex/Copilot adapters must
not each implement independent reducers or ledgers.

### 5. Herdr becomes infrastructure, not semantic truth

Herdr remains useful for:

- launching and hosting harness sessions;
- identifying panes/workspaces;
- proving that a process/session still exists;
- last-mile prompt injection for a quiescent harness when no native push channel
  exists;
- optional defensive reconciliation when an adapter disappears.

A Herdr `idle` transition alone must never certify `quiescent`.

## Technology decision

Implement the resident monitor in **Python**, not Bash, using the standard
library initially:

- `asyncio` for the long-lived event loop and local socket clients;
- `socket`/`asyncio.start_unix_server()` for AF_UNIX stream transport;
- newline-delimited JSON (NDJSON) for framing;
- `sqlite3` for the durable event/projection/wake ledger;
- atomic filesystem spool files as the adapter-side fallback when the daemon is
  unavailable before an event receives a durable ACK.

Keep Bash as the public CLI/glue layer. Existing commands can delegate monitor
operations to a small Python client without exposing the implementation language
to users.

Do **not** add Redis, NATS, Kafka, or another external broker in this stage. The
local deployment is one user, one machine, normally 3-5 concurrent crews, and a
single resident daemon. An external broker would add installation, service
lifecycle, security, versioning, and debugging burden before Rozoro needs its
multi-host capabilities.

The domain protocol should remain transport-independent so a later distributed
version can map the same events to NATS/JetStream without redesigning reducers.

## Files and ownership

Proposed shape (exact names may change during implementation):

```text
bin/
  rozoro                       existing public dispatcher
  rzr-monitor.sh               thin CLI bridge, if useful

lib/ or bin/
  rozorod.py                   daemon entry point
  rzr-monitor-client.py        CLI/socket client
  rzr-protocol.py              schema validation/helpers
  rzr-store.py                 SQLite ownership/migrations
  rzr-reducer.py               pure session/task reducers
  rzr-notify.py                generation/coalescing scheduler

.pi/extensions/
  rozoro-watchtower.ts         thin Pi adapter only

hooks/ or generated config/
  claude-rozoro-event.py       Claude hook -> socket/spool adapter

$ROZORO_HOME/
  monitor.sock
  monitor.lock
  monitor.db
  spool/
```

Prefer modules whose reducers/protocol validation are independently testable and
free of socket/process side effects.

## Protocol v1

Use NDJSON: exactly one JSON object per line. Every producer event must include a
stable `event_id` so delivery/replay is idempotent.

Illustrative producer events:

```json
{"v":1,"type":"session.register","event_id":"...","session_id":"...","role":"crew","harness":"claude","task_id":"..."}
{"v":1,"type":"turn.start","event_id":"...","session_id":"...","turn_id":"..."}
{"v":1,"type":"background.start","event_id":"...","session_id":"...","job_id":"opaque","job_kind":"subagent"}
{"v":1,"type":"background.stop","event_id":"...","session_id":"...","job_id":"opaque","result":"success"}
{"v":1,"type":"background.snapshot","event_id":"...","session_id":"...","active_count":0}
{"v":1,"type":"turn.stop","event_id":"...","session_id":"...","background_active":false}
{"v":1,"type":"session.end","event_id":"...","session_id":"..."}
```

Illustrative daemon responses:

```json
{"v":1,"type":"ack","event_id":"...","durable_seq":193}
{"v":1,"type":"error","event_id":"...","code":"invalid-event"}
```

Illustrative watchtower-side messages:

```json
{"v":1,"type":"watchtower.register","session_id":"...","harness":"pi","driver_id":"..."}
{"v":1,"type":"notification","generation":54,"priority":"normal","task_count":4}
{"v":1,"type":"reconcile","through":54}
{"v":1,"type":"reconcile.result","through":54,"reports":[...]}
{"v":1,"type":"ack-generation","through":54}
```

Exact schemas should be committed as tested validation code before adapters are
migrated.

## Persistence model

SQLite is the daemon-owned durable source. Other components should not write it
directly.

Minimum logical data:

### events

- monotonic durable sequence;
- `event_id` unique constraint;
- session/task identity;
- event type;
- normalized payload;
- receive timestamp.

### sessions

- session id;
- task id or driver id;
- harness;
- role (`crew` or `watchtower`);
- foreground state;
- background state/count;
- derived availability;
- latest durable sequence;
- last-seen/liveness metadata.

### task projections

- task id;
- current availability;
- current handoff/report projection or reference;
- actionable reason;
- projection generation/version;
- last event sequence.

### watchtower delivery

- driver id;
- latest generation;
- delivered generation;
- acked generation;
- pending task ids / projection references;
- delivery state and last error.

Use one SQLite transaction for an accepted event's event-log insert, reducer
updates, and any resulting actionable-generation bump. Only ACK the socket event
after commit succeeds.

## Adapter crash fallback

A harness event must not vanish solely because `rozorod` is restarting.

Adapter send algorithm:

```text
connect monitor.sock
  ↓
send normalized event
  ↓
wait for durable ACK

success -> done
failure before ACK -> atomically write
                      $ROZORO_HOME/spool/<event-id>.json
```

On daemon startup and periodically thereafter:

```text
scan spool/
  ↓
import idempotently (UNIQUE event_id)
  ↓
commit
  ↓
delete spool file
```

A duplicated event due to uncertain client ACK is harmless. A producer must not
invent a second logical event id during retry.

## Claude adapter

Claude is a first-class semantic producer, not just a Herdr pane.

Use Claude lifecycle hooks/capabilities available on the installed supported
version to emit normalized events. The implementation crew must verify exact
hook names/payloads on the target Claude release before coding against them.
The intended mapping is:

```text
SessionStart      -> session.register
UserPromptSubmit  -> turn.start
SubagentStart     -> background.start
SubagentStop      -> background.stop
Stop              -> turn.stop + authoritative background snapshot when exposed
SessionEnd        -> session.end
```

The important semantic rule is that `Stop` with owned background work still
active maps to `waiting-background`, not `quiescent`.

Where Claude exposes an authoritative list/snapshot of background tasks at Stop,
use that snapshot to reconcile incremental SubagentStart/SubagentStop bookkeeping
and correct missed hook edges.

### Claude watchtower wake

If the watchtower is currently running or waiting on its own background work,
retain pending generations; do not inject a Herdr prompt based on raw `idle`.

If Claude itself reports quiescent and a pending generation arrives later, the
daemon may use Herdr as the actuator to submit the fixed content-free wake:

```text
Rozoro notification pending; run ./bin/rozoro reconcile.
```

Where a Claude Stop hook can safely continue the same Claude turn/session in
response to a pending generation, prefer that native path; otherwise the durable
pending generation remains available for the next safe actuator opportunity.

## Pi adapter

Refactor `.pi/extensions/rozoro-watchtower.ts` into a thin adapter.

Remove from the Pi extension:

- `state/*.meta` filesystem watching;
- `rzr-watch.sh` process ownership;
- fleet watcher restart logic;
- runtime projection parsing;
- `action.required` policy;
- task membership bookkeeping.

The Pi extension should instead:

1. connect/register with `monitor.sock` as a watchtower client;
2. expose Pi-native lifecycle information to Rozoro where available;
3. receive a coalesced `notification` generation;
4. call `pi.sendMessage()` with the fixed reconciliation nudge using
   `triggerTurn:true` / `deliverAs:"followUp"`;
5. reconnect after daemon/socket interruption and re-register without losing
   already persisted pending generations.

Pi's visual `setStatus()` may show daemon/watchtower health, but UI status is not
part of correctness.

## Crew adapters use the same model

The socket protocol is not watchtower-only. A Rozoro-managed Claude or Pi crew
should also publish harness-native lifecycle events so the same reducer can
distinguish:

```text
main agent stopped + background active
  -> waiting-background

main agent stopped + background clear
  -> quiescent / turn settled
```

This removes the current dependence on adjacent Herdr pairs such as
`working -> done`. Herdr foreground changes remain useful defensive observations
but cannot override a certified harness-native background-active state.

## Notification coalescing

Coalesce notification delivery, never source events.

Initial policy should stay deliberately small:

- persist/reduce an actionable event immediately;
- open a short collection window (target 250-500 ms; choose one value in code and
  make it testable/configurable only if evidence warrants it);
- events arriving during the window persist normally and may add affected tasks
  to the same pending generation range;
- at expiry, if no wake is outstanding, send one notification;
- if a wake is already delivered-but-unacked, do not send another solely because
  more normal-priority events arrived; they remain in a higher generation;
- after the watchtower acks only the generation it reconciled, any newer pending
  generation becomes eligible for the next wake.

Priority can remain minimal in v1:

```text
blocked/failed/needs external action -> flush collection window early
normal completion                   -> batch normally
progress-only/non-actionable        -> no watchtower wake
```

Do not put LLM-generated summaries inside the daemon. A deterministic UI string
such as `3 completed · 1 blocked` is acceptable; authoritative details come from
reconcile.

## Dynamic task membership

This plan subsumes the intent of open issue #25's long-lived monitor: one resident
process owns Herdr subscriptions, dynamic membership, periodic fallback scans,
and health/status.

Filesystem notifications are an optimization, never the correctness boundary.

When `state/*.meta` changes:

1. debounce a membership scan;
2. compute the actual task-id set;
3. if membership did not change, do nothing;
4. if membership changed, add/remove only the affected subscriptions or rebuild
   the Herdr subscription using a synchronized snapshot that cannot lose a
   settlement edge;
5. periodically rescan task membership even without filesystem notification,
   because filesystem events may be coalesced or dropped.

Critically, changing fields inside an already-known task `.meta` must not restart
monitoring of unrelated crews.

## Herdr defensive reconciliation

Harness-native events are semantic authority when available, but the daemon
still needs failure detection:

- periodically verify that registered task/driver panes still exist;
- project a session `gone` when the host process/pane truly disappears;
- mark adapter state `unknown`/disconnected if the harness stops reporting while
  the process remains alive;
- do not silently downgrade `background=active` to `clear` merely because Herdr
  reports `idle`;
- on daemon restart, reconstruct projections from SQLite and then reconcile live
  Herdr liveness before sending pending wakes.

The old `rzr-watch` path can remain temporarily as a compatibility/fallback
observer during migration, but there must be one clearly documented semantic
authority at each rollout phase.

## Health and observability

`./bin/rozoro monitor status [--json]` should expose at least:

- daemon running/not running;
- socket path;
- DB schema/version;
- Herdr subscription connected/disconnected;
- last Herdr error;
- connected harness clients/adapters;
- task count;
- watchtower driver(s);
- latest generation / delivered / ack;
- pending task count;
- spool backlog count;
- last accepted event sequence/time.

The daemon should have structured stderr/log output suitable for debugging but no
mandatory external log service.

## Security/locality

Stage 1 is local single-user only.

- `$ROZORO_HOME` must be user-only (`0700` expectation).
- `monitor.sock`, DB, spool, and driver state must not be world-readable/writable.
- Bind an AF_UNIX socket only; do not open a TCP listener.
- On startup, hold a daemon lock. If the socket exists and is connectable, fail
  because another daemon owns it. If the socket is stale and the lock proves no
  live owner, remove/rebind it safely.
- Never send crew-authored prose as executable instructions through wake payloads.
  Wake messages remain fixed/content-free.

Remote/multi-host Rozoro is explicitly out of scope. If that becomes a real
requirement, evaluate NATS/JetStream rather than extending the local Unix-socket
transport into an ad-hoc network broker.

## Implementation sequence

Implement this as a series of independently reviewable PRs. Do not attempt a
single flag-day rewrite.

### Phase 0 — lock protocol/state contracts in tests and docs

Goal: define the normalized model before any current behavior changes.

Deliver:

- protocol v1 event/response schema and validation helpers;
- pure reducer tests for foreground/background/availability combinations;
- explicit semantic tests proving `idle/stopped + background active` is **not**
  quiescent;
- generation/delivered/ack invariants written as tests;
- compatibility mapping from current v2 task/report state into the new
  projection model.

Acceptance:

- no daemon yet;
- no production wake-path behavior changes;
- reducer is deterministic and side-effect free.

### Phase 1 — resident daemon skeleton + SQLite + socket

Goal: establish durable local ownership.

Deliver:

- daemon lifecycle (`start|status|stop`) or an equivalent supervised foreground
  entry point used by wrappers;
- daemon lock and stale-socket handling;
- AF_UNIX NDJSON server;
- SQLite schema/migrations;
- event `event_id` dedup;
- durable ACK after transaction commit;
- spool import path;
- health/status endpoint;
- clean restart recovery.

Acceptance:

- synthetic client can send events, disconnect/retry, and never create duplicate
  logical events;
- killing daemon between receive/ACK and restarting yields at-least-once import;
- no Pi/Claude production migration yet.

### Phase 2 — task/session reducer + notification ledger/coalescer

Goal: move correctness into `rozorod` before attaching harnesses.

Deliver:

- persistent session/task projections;
- actionable generation bumps inside the same SQLite transaction as event
  acceptance;
- delivered/ack semantics;
- short notification collection window;
- deterministic clustered pending-task summary;
- reconcile API that snapshots/returns through a generation and acks only the
  caller-specified/snapshotted generation;
- restart recovery for delivered-but-unacked generations.

Acceptance tests must include:

- 20 events arriving in a burst are all persisted but cause one normal wake;
- events arriving after a wake is delivered remain pending through a higher
  generation;
- reconcile/ack of generation N never consumes N+1;
- blocked/failed can flush the normal batching window;
- daemon restart cannot lose pending work.

### Phase 3 — Claude semantic adapter (crew + watchtower)

Goal: solve the background/subagent ambiguity first.

Deliver:

- verified Claude hook integration on the supported installed version;
- session/turn/subagent/background events sent through socket with spool fallback;
- authoritative Stop/background snapshot reconciliation when available;
- Claude crew settlement derived from normalized state rather than Herdr
  `working -> idle/done` adjacency;
- Claude watchtower registration and safe wake gating from normalized availability;
- Herdr used only as the wake actuator once Claude is certified quiescent (or a
  verified native Stop-continuation path when available).

Mandatory live tests:

1. Claude starts a native subagent, main foreground becomes idle/stopped, subagent
   continues: watchtower/crew must remain `waiting-background` and must not be
   considered settled.
2. Final subagent completes and Claude reaches a no-background Stop: projection
   becomes quiescent and exactly one actionable completion is produced.
3. Pending crew events arrive while Claude watchtower is waiting-background:
   they accumulate without injecting into the active orchestration flow, then
   wake once safe.
4. Kill/restart `rozorod` during the above and verify spool/replay recovery.

### Phase 4 — Pi adapter migration

Goal: remove Pi-specific watcher correctness logic.

Deliver:

- Pi socket registration/client;
- coalesced notification -> `pi.sendMessage` fixed wake;
- reconnect/re-register behavior;
- Pi-native lifecycle publication where useful/available;
- delete extension-owned `rzr-watch` subprocess and `.meta` restart machinery;
- keep existing Pi UX status only as health display.

Mandatory regression tests:

1. crews A/B are working; metadata for B is rewritten repeatedly; A settles:
   exactly one A notification is eventually reconciled;
2. restart Pi extension/session while a generation is delivered-but-unacked:
   pending generation survives and is redelivered/reconciled;
3. multiple crews finish within the collection window: one Pi wake, all tasks in
   reconcile result;
4. restarting monitor five times with no new semantic event does not manufacture
   five completion notifications.

### Phase 5 — replace/deprecate old watcher ownership

Goal: make one path authoritative.

Deliver:

- update watchtower template, README, and skill to use `rozorod`/socket semantics;
- remove or clearly demote Pi direct `rzr-watch` integration;
- retain `rzr-watch` only for explicit diagnostics/compatibility if still useful;
- merge/supersede issue #25's resident-monitor scope into the delivered daemon;
- migrate existing durable wake JSON ledger only if needed for compatibility, or
  document a clean one-time boundary if no pending driver state can safely be
  carried across.

Acceptance:

- normal Pi and Claude operation has exactly one semantic owner;
- no global watcher restart occurs when an unrelated task metadata field changes;
- docs do not teach two competing production wake paths.

### Phase 6 — Codex and Copilot adapters (deprioritized)

Goal: prove the adapter boundary, not expand core semantics.

Only after Pi + Claude are stable:

- map available Codex lifecycle signals into protocol v1;
- map Copilot lifecycle signals into protocol v1;
- reuse the same reducer/ledger/coalescer;
- where a harness lacks certified background state, report `background=unknown`
  and fail conservatively rather than inventing quiescence;
- use their existing wake actuators (`codex queue`, Herdr/Copilot-compatible path)
  behind the same delivery interface.

No core database/protocol redesign should be required merely to add these
adapters. If it is, revisit the adapter abstraction before shipping them.

## Test strategy

### Pure/unit tests

- protocol validation and version rejection;
- `event_id` idempotency;
- reducer transitions and illegal regressions;
- background snapshot correcting missed incremental events;
- projection/action generation rules;
- coalescing scheduler with virtual/controlled time;
- generation/delivered/ack invariants;
- SQLite migration/restart behavior.

### Process integration tests

Use temporary `ROZORO_HOME` directories and a real Unix socket:

- two clients publishing concurrently;
- client disconnect before durable ACK;
- spool recovery;
- daemon SIGTERM/SIGKILL/restart;
- stale socket recovery;
- multiple watchtower reconnects to the same durable driver identity;
- membership rescans while events are arriving.

### Herdr integration tests

- pane disappearance -> `gone` without corrupting harness-native state;
- task addition/removal does not interrupt unrelated task observation;
- no dependence on a raw `idle` transition to declare a Claude session
  quiescent.

### Live harness tests

Run opt-in, cost-incurring smokes for Pi and Claude covering native background
work/subagents, watchtower busy/quiescent transitions, notification clustering,
and daemon restart recovery.

Live tests are required before deleting the current production path; fake-Herdr
coverage alone is insufficient for the lifecycle semantics this plan exists to
fix.

## Migration and compatibility

- Existing `tasks/<id>/brief.md`, `handoff.md`, `session.json`, and task identities
  remain durable and valid.
- The append-only handoff protocol remains the task-report contract.
- `./bin/rozoro status` should continue exposing task/report semantics during
  migration; implementation may source runtime availability from SQLite once the
  daemon becomes authoritative.
- `./bin/rozoro reconcile` remains the watchtower command conceptually, even if
  its backend moves from JSON ledger files to the daemon/SQLite API.
- Do not require users to install Python packages beyond the runtime already
  needed by Rozoro unless later evidence justifies one.

## Failure policy

Fail closed on uncertain semantic state.

- `background=unknown` must not silently become `clear`.
- disconnected harness adapter + live Herdr pane -> availability `unknown`, not
  quiescent.
- DB commit failure -> no durable ACK.
- invalid protocol event -> reject loudly and preserve adapter spool copy if the
  producer cannot prove acceptance.
- wake actuator failure -> retain pending generation and expose retry/error in
  monitor status.
- malformed handoff -> actionable report state; it does not invalidate lifecycle
  history.

## Non-goals

This plan does not:

- create a distributed/multi-host broker;
- replace Herdr as the terminal/session backend;
- make Rozoro a general pub/sub product;
- add Redis/NATS/Kafka as a dependency;
- use an LLM inside the daemon to summarize events;
- infer acceptance/merge success from runtime quiescence;
- prioritize Codex/Copilot parity before Pi + Claude correctness;
- redesign the task brief/handoff/report protocol except where needed to consume
  the new runtime projection.

## Acceptance criteria

The architecture is ready to call complete when all of the following hold:

1. Pi and Claude both speak one versioned Rozoro lifecycle protocol.
2. A Claude foreground idle/Stop while native subagents remain active is never
   classified as a settled/quiescent turn.
3. Every accepted lifecycle event is durably owned before the producer receives
   ACK; retries are idempotent by `event_id`.
4. The daemon survives crash/restart without losing pending actionable
   generations.
5. A burst of crew completions persists every event but produces a coalesced
   watchtower wake.
6. A watchtower reconciliation acknowledges exactly the generation it observed;
   newer events remain pending and re-notify.
7. Adding/updating one crew cannot globally interrupt monitoring of unrelated
   crews.
8. Pi no longer owns the Herdr fleet watcher/reducer lifecycle in its extension.
9. Claude wake safety is based on normalized Claude/Rozoro availability, not raw
   Herdr `idle`.
10. Herdr disappearance still surfaces `gone` and other infrastructure failures.
11. `rozoro monitor status --json` exposes enough state to diagnose disconnected,
    pending, delivered-unacked, retrying, and spool-backlog conditions.
12. Existing user-facing task folders, handoff reporting, and exact-session
    resume remain compatible.
13. Codex/Copilot can be added as adapters without changing core persistence or
    notification semantics.

## Coordination notes

- Open issue #25 already requests a long-lived monitor with dynamic membership,
  periodic reconciliation, and health/status. This plan should be treated as the
  expanded target architecture for that work rather than implementing a second
  resident monitor beside it.
- The existing durable cross-harness wake ledger is valuable prior art. Preserve
  its at-least-once/generation invariants while moving ownership into the daemon
  store; do not preserve its exact file layout merely for compatibility aesthetics.
- The current Pi watchtower extension is a migration target, not the new core.
- Keep implementation PRs small enough that current watchtower operation remains
  usable until the replacement path has passed live Pi + Claude tests.
