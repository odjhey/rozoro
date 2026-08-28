---
name: v2_ports_and_adapters
description: "v2 port catalogue and adapter guidelines: what each port owes the core, what adapters may and may not do, and the conformance requirements for real integrations."
type: architecture
tags: [v2, ports, adapters]
status: current
generated: "Claude Fable 5, 2026-08-28"
created_at: 2026-08-28T00:00:00+08:00
---

# Ports and adapters

The core is assembled from ports at a composition root. A port is a `typing.Protocol` in `core/ports/` with a docstring contract, a reference fake, and a conformance suite. An adapter is the only place a provider's types, shapes, and quirks may exist.

## Port catalogue

Derived from the v1 [contracts](./contracts/README.md); each port names the v1 contract it must honor.

| Port | Owes the core | v1 contract |
|---|---|---|
| `Clock` | Instants; monotonic ordering hints. No direct `time.*` in core. | conventions |
| `Identity` | ULIDs, UUIDs, nonces, hashes. No direct `random`/`uuid` in core. | conventions |
| `TaskRecordStore` | Durable task folder semantics: reserve-by-collision, atomic writes, append-only handoff, cursor files. | [task-folder](./contracts/task-folder.md), [handoff](./contracts/handoff.md) |
| `HomeStore` | The home namespace: resolution (once, frozen), owner-private creation, safety discipline (no-follow, dev/ino, nlink, modes). **The single implementation** of what v1 has five of. | [home-layout](./contracts/home-layout.md), conventions |
| `EventStore` | Exactly-once durable acceptance, contiguous per-session ordering surface, projections, generation freezing, delivery cursors with the CHECK-equivalent invariant, the reset boundary. | [event-protocol](./contracts/event-protocol.md) |
| `EventIngress` | The producer path: durable reserve (spool) before send, at-least-once, idempotent by event id. | event-protocol |
| `TerminalHost` | Tabs/panes/workspaces, agent oracle (status, readiness, session identity), actuation (prompt, keys, wait), edge subscription. Host truth only — never semantic truth. | [herdr-port](./contracts/herdr-port.md) |
| `Harness` (one per harness) | Launch argv mapping, capability gate, lifecycle production wiring, session discovery, exact resume. Certifies only what the harness can certify. | [harness-adapters](./contracts/harness-adapters.md) |
| `WakeActuator` | Deliver the fixed nudge to a driver target; report delivered/deferred/failed distinctly; confirm only after backend success. | [registration](./contracts/registration.md), wake-delivery context |
| `RegistrationStore` | Commit-point target + append-only history + gap repair + authority marker transactions. | registration |
| `AttentionStore` | Ledger items: strict format, supersession, locked mutations, malformed-surfacing. | [attention-ledger](./contracts/attention-ledger.md) |
| `WorkGraphStore` | Worksets, typed edges, patch-only mutation with lineage, readiness derivation inputs. | [work-graph](./contracts/work-graph.md) |
| `AttemptStore` | Append-only attempts/loops, cumulative-lineage budget queries. | [attempts](./contracts/attempts.md) |
| `EvidenceStore` | Version-bound artifact refs, evidence, gate verdicts, monotonic staleness. | [artifacts-evidence](./contracts/artifacts-evidence.md) |
| `PolicySource` | Resolve preset + exactly-one-mission, validated bytes, composed digest. | [policy-composition](./contracts/policy-composition.md) |

## Adapter guidelines

**What an adapter is for.** Translating one provider's reality into a port's contract — nothing else. If logic would be correct for every conceivable provider, it belongs in the core; if it exists because of this provider's shape, it belongs in the adapter.

1. **Provider types stop here.** No provider JSON shape, SDK object, exit-code convention, or path layout crosses the port boundary. Port signatures use domain types only.
2. **Never certify beyond the backend.** If the provider cannot prove a fact, return the port's `unknown`, not a guess. The Claude/Codex/Pi background-axis differences are the model: same port, honestly different certifications, declared via a capability descriptor the adapter exports.
3. **Capability descriptors are data** (schema now normative: [executor descriptors](./contracts/harness-adapters.md#executor-descriptors-v2-addition--proposal-0001-p5)). Each adapter declares what it can certify (background axis, session preallocation, readiness signal, version window) as a structured value the core can branch on — replacing v1's scattered per-harness special cases.
4. **Validate before mutate.** Capability gates, version windows, and input validation run before the first side effect on the backend.
5. **Fail closed, distinctly.** Distinguish transport failure / cannot-certify / backend-refused in the port's error types (v1's eventwait exit codes 2/3/4 and wake delivered/deferred/failed are the pattern). Retry only what the port contract declares retryable; never retry an operation that could double-claim a live resource (v1: `agent_not_ready` is polled, never re-started).
6. **Idempotency at the edge.** Where a backend gives at-least-once behavior, the adapter dedups by the contract's identity (event id, edge id) before the core sees it — or passes the identity through so the store can.
7. **Tolerate shapes, pin grammar.** Defensive parsing of unversioned upstream output is fine *inside* the adapter (v1's jq `//`-chains), but anything the adapter asserts about the backend's grammar goes in its capability suite so drift is caught, not absorbed.
8. **No prose synthesis.** Adapters never compose text for a resident conversation; the only injectable string is the core's fixed wake constant.
9. **Security discipline is inherited, not re-implemented.** Filesystem adapters use the one safety toolkit; no adapter hand-rolls no-follow walking.
10. **One adapter, one backend, one directory.** Adapters never import each other's internals; shared needs graduate into the core or a shared adapter-support module by explicit decision.

## Conformance and acceptance

A real integration (phase 2+) may land only with:

1. **The shared conformance suite green** — every port has one; it encodes the port's contract (orderings, idempotency, error taxonomy) and runs identically against the fake and the real adapter.
2. **A capability suite** — what this backend certifies, including at least one negative case (drift, refusal, absence), following v1's fixture-evidence pattern (`claude-hooks-*.json`, capability probes) with dated, redacted evidence for live-gated claims.
3. **A capability descriptor** consumed by the core, not comments.
4. **Technical tests** for any sensitive mechanics the adapter owns (locking, fsync ordering, socket identity, permission modes).

The fake for each port is written **first** and is the reference semantics; when a real adapter and the fake disagree, the port contract decides which is wrong, and the losing side changes in the same PR.
