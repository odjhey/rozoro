---
name: v2_contract_event_protocol
description: "Protocol v1: the closed NDJSON wire format between producers, the rozorod daemon, and watchtower clients — events, requests, notifications, the frozen report tuple matrix, and durability guarantees."
type: contract
tags: [architecture, contracts, protocol, event-bus]
status: v2-draft
generated: "Claude Fable 5, 2026-08-28"
created_at: 2026-08-28T00:00:00+08:00
---

> **v2 working copy** — forked from [`docs/architecture/contracts/event-protocol.md`](../../docs/architecture/contracts/event-protocol.md) at `b044dbe`. Iterate here; the v2 effort never edits the live architecture docs.

# Event protocol (v1)

Part of the [contracts index](./README.md). Protocol v1 is the wire contract over `$ROZORO_HOME/monitor.sock` (AF_UNIX, NDJSON, one JSON object per newline-terminated frame). It is deliberately **closed, strictly typed, correlation-checked, prose-free, and non-contradictory** — the architectural separations (event ≠ delivery ≠ ACK, crew ≠ watchtower, batch ≠ work item) are enforced by the validator, not by convention.

## Envelope rules

- `"v": 1` mandatory and exact (booleans rejected). Unknown `type` → `unsupported-type`.
- **Unknown fields are rejected** (`invalid-field`) — a misspelling cannot silently weaken semantics.
- Canonical encoding: `sort_keys`, compact separators, no NaN/Infinity. `MAX_FRAME_BYTES = 1 MiB`, newline-inclusive, checked before parsing in both directions.
- Duplicate JSON members at any depth, lone surrogates → `invalid-json`.
- Integers bounded by the cross-runtime-safe `MAX_INTEGER` (JS safe integer).
- IDs match `^[A-Za-z0-9][A-Za-z0-9._:@+-]{0,127}$` (event ids become spool filenames; traversal rejected here).

## Lifecycle events (producer → daemon)

Shared required fields: `event_id`, `producer_seq` (positive, 1-based), `session_id`, `harness ∈ {claude, pi, codex, copilot}`, `role ∈ {crew, watchtower}`, plus **exactly one** of `task_id` (crew) or `driver_id` (watchtower).

| Type | Extra fields | Semantics |
|---|---|---|
| `session.register` | — | Session exists. |
| `turn.start` | `turn_id` | Foreground turn began. |
| `turn.stop` | `background_active: true\|false\|null`, opt `turn_id` | Foreground settled. **Tri-state background**: `null` = unknown and is *not* a negation of prior positive facts; only `false` certifies clear. |
| `background.start` | `job_id`, `job_kind` | Background job began. |
| `background.stop` | `job_id`, `result ∈ {success, failed, cancelled, unknown}` | Supported by the reducer; currently no emitter. |
| `background.snapshot` | `active_count ≥ 0` | Authoritative point-in-time background count. Only an explicit snapshot can certify `clear`. |
| `session.end` | — | Session ended. |

**Ordering**: `producer_seq` must be strictly contiguous per session. Stale sequences are dropped; gaps buffer the event, set `sequence_gap`, and immediately de-certify availability to `unknown` while retaining pre-gap facts for deterministic replay. Herdr's `state_change_seq` is a **different ordering domain** and never seeds `producer_seq`.

**Durability**: `ack {event_id, durable_seq}` is returned only after SQLite COMMIT. Producers spool durably before sending and delete only on a matching ACK (at-least-once delivery; duplicates collapse on `event_id`; a replayed `event_id` with different content is a spool collision error).

## Requests and responses (client ↔ daemon)

All requests carry `request_id`; events must not (strict correlation).

| Request | Response | Notes |
|---|---|---|
| `health` | `health.result` | running, schema_version, cursors, spool backlog, herdr connectivity, per-driver rows. |
| `task.status {task_id}` | `task.status.result` | availability, foreground, background, report_state, verdict, actionable_reason. |
| `watchtower.register {session_id, harness, driver_id}` | `ok` | Binds the connection epoch. |
| `watchtower.availability {driver_id}` | `…result {availability}` | Drives the live gate. |
| `notification.pending {driver_id}` | `ok` + optionally an unsolicited `notification` frame | Pull path. |
| `notification.delivered {driver_id, generation}` | `ok` | Delivery confirmation. Distinct from ACK: carries `generation`, never `through`. |
| `reconcile.pending {driver_id, scope? ∈ {delta, full}}` | `reconcile.pending.result {through, reports[], since?, unchanged_count?}` | `scope` optional/additive (ADR-0010): an old daemon sees no field and serves a full snapshot. |
| `reconcile.ack {driver_id, through}` | `ok` | Generation ACK: carries `through`, never `generation` — the delivery/ACK distinction is structurally unrepresentable to confuse. |
| `driver.authority` / `driver.disable` | `…result {authority ∈ {active, disabled, unknown}}` / `ok` | Authority inspection and tombstone. |
| `monitor.stop` | `ok`, then exit | In-band shutdown. |

Implemented but currently caller-less (see [rewrite seams](../rewrite-seams.md)): `driver.snapshot`, bare `reconcile`, `ack-generation`.

## The notification frame

```json
{"v": 1, "type": "notification", "generation": N, "priority": "normal|urgent", "task_count": N}
```

**Deliberately prose-free.** Adding `message`, `summary`, `prompt`, `reports`, or `task_ids` is `invalid-field`. The wake carries no content and no task attribution — the watchtower must reconcile to learn anything. This is simultaneously a prompt-injection boundary, a privacy boundary, and the "delivery batches are not work items" principle enforced on the wire.

## Reconcile reports and the frozen tuple matrix

Each report is exactly `{task_id, generation, availability, report_state, verdict, actionable_reason}` (+ optional free-form `projection`). Field domains:

```text
availability        busy | waiting-background | quiescent | blocked | gone | unknown
report_state        missing | malformed | valid
verdict             done | waiting | needs-action | failed | blocked | null
actionable_reason   none | quiescent | missing-report | malformed-report | waiting-background |
                    native-turn-ended-report | blocked | failed | needs-action | gone | unknown
```

A **frozen 14-entry whitelist** of legal `(report_state, verdict, actionable_reason)` combinations is enforced at the protocol boundary; any other combination is rejected as contradictory. The daemon cannot emit a semantically self-contradictory task row. Additional cross-field checks: every `report.generation ≤ through`; no duplicate `task_id` in a snapshot.

## Error frames

- `frame.error {code}` — the no-safe-correlation path; may carry **no** id (an id here is itself `invalid-field`). Direction is chosen only from a recognized `type`, never from attacker-selected id presence.
- `event.error {event_id, code}`, `request.error {request_id, code}` — correlated failures with closed code subsets.
- Codes: `invalid-json`, `frame-too-large`, `invalid-message`, `invalid-version`, `invalid-event`, `invalid-field`, `unsupported-type`, `read-timeout`, `server-busy`, `internal-error`.

## Availability derivation (reducer)

Foreground (`running|stopped|unknown`) and background (`active|clear|unknown`) are independent axes, each separately invalidated by adapter disconnect. Availability is derived conservatively, in precedence order:

```text
gone > unknown (disconnected) > blocked > busy (fg running)
     > waiting-background (fg stopped + bg active)
     > quiescent (fg stopped + bg clear) > unknown
```

Tested exhaustively, including all arrival permutations (no false quiescence), "report done never changes runtime or implies acceptance", and "a shell pane can never be quiescent".
