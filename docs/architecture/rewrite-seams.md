---
name: rewrite_seams
description: "Code-verified inventory of seams for the rewrite and contract/ports improvements: orphaned surfaces, duplicated implementations, prose-only concepts, asymmetries, and soft spots."
type: architecture
tags: [architecture, rewrite, debt]
status: current
generated: "Claude Fable 5, 2026-08-28"
created_at: 2026-08-28T00:00:00+08:00
---

# Rewrite seams

Everything below was verified against the current code and tests. These are the places where the rewrite and the contract/ports improvements have the most leverage — either because a contract exists but is unenforced, because one concept has several divergent implementations, or because a surface is dead weight.

## Orphaned and caller-less surfaces

| Seam | Detail |
|---|---|
| Codex rollout adapter | `bin/rzr-codex-event-adapter.py` is launched by nothing; superseded by the native Codex hook. It also bypasses the durable spool (in-memory retry only) and reads `/proc` (non-functional on macOS). Teardown's `event_adapter_pid` kill path is dead code — no writer for that meta key. |
| Unreachable protocol surface | `driver.snapshot`, bare `reconcile`, `ack-generation`, and `background.stop` are fully implemented (protocol, server, store, reducer) with zero production callers/emitters. Decide: promote to contract or delete. |
| Stubbed push actuator | The daemon registers the coalescer's push actuator as a permanent-DEFER lambda; only the pull path (`notification.pending`) is live. The elaborate in-flight/claim push logic is exercised by tests only. |
| Parsed-and-discarded flags | `status --peek` is accepted and ignored; teardown `--force` is a warn-only no-op. |

## Duplicated implementations of one contract

| Contract | Implementations | Risk |
|---|---|---|
| Home resolution | 5 (shell lib, producer client, monitor CLI, poller, Pi extension TS) | Matrix-tested today, but every new consumer must join the audit registry; a rewrite should centralize. |
| Filesystem-safety toolkit | `lib/rozoro_artifacts/safe_fs.py` plus hand-rolled inline-Python equivalents in `rzr-lib.sh` and `rzr-register.sh` | Same discipline, three codebases. |
| Attention-item reader | Canonical `ledger.py` parser vs `rzr-lineage.py`'s own loose regexes | Second reader will diverge silently. |
| Claude version window | Duplicated in the hook, the shell gate, and twice inline in settings-writer heredocs | Four edit sites per version bump. |
| Herdr socket discovery | Daemon prefers `sessions[?default==true]`; shell takes `.sessions[0]` | Divergent behavior with multiple sessions. |
| Pi extension path | Spelled `$RZR_BIN/../.pi/...` in the lib, `$ROOT/.pi/...` in the launcher | Same target, two derivations. |
| Attempt-budget prose | Identical counter model defined in 3 files (skill, mission, guidelines), held together only by regex tests | See "prose-only concepts". |

## Prose-only concepts with no code representation

Candidates for real contracts in the ports/contracts work:

- **Workset** — mission vocabulary ("the group of tasks producing one integrated outcome") with no file, schema, field, or verb.
- **Attempt/replan/repair counters and lineage ids** (`attempt_count`, `replan_count`, `repair_lineage_id`, `implementation_lineage_id`, caps) — derived from durable history by the watchtower's judgment; nothing validates the arithmetic.
- **`heads:` line** in handoff blocks (`reviewed=/pushed=/ci=/merged=`) — demanded by the protocol template, invisible to the canonical parser. Either parse it or stop asking for it.
- **Role rosters and status routing** — enforced only as documentation-referential-integrity tests over Markdown.
- **Assurance map / changed-head reconciliation records** — named-owner records required by policy with no schema or storage convention.

## Deliberate asymmetries worth revisiting

- **Claude watchtowers are policy-blind**: preset-only, no mission, no composed policy, recorded as `unverified-no-consumed-policy-args-array`. Pi is the only mission-composed harness.
- **Producer trust varies by harness**: Claude has a capability proof + strict version window; Codex hooks have no proof and no version gate; Copilot has no producer at all.
- **Reconcile delta is CLI-only** (ADR-0010): the Pi adapter path remains full-snapshot.
- **Skill bytes are not part of policy attribution** — a recorded, deferred gap: a driver's behavior depends on skills whose hashes are not in the registration.
- **Tasks/crews/attention are not mission-namespaced**: coexisting watchtowers share one home on operator discipline alone.

## Soft spots in durable formats

- `state/<key>.meta` — KEY=VALUE with `grep -v` rewrite, no schema version, explicitly "not a stable public API"; `crew=resumed` abuses a preset field as a lifecycle marker and needs a special case in `restart`.
- The legacy stack (`pending.json`/`ack`, `.acked-blocks`, `state/*.status`, `*.runtime.json`, `watch --wake`) is fenced but still shipped; the cutover is complete, so this is deletable weight once diagnostics needs are settled.
- Herdr JSON parsing is 5-way `//`-fallback shape tolerance — coping with an unversioned upstream, not a contract.
- `fast` mode hard-pins one vendor model in executable code (the only model name in `bin/`).

## Known documentation defects (in the pre-existing docs)

Found while verifying; the new suite supersedes the first, the others are one-line fixes in place:

1. `docs/architecture.md` predates ADR-0012/0013/0014 — no missions, presets, driver identity, attention ledger, or lineage. Superseded by this suite.
2. `docs/event-bus-cutover.md` header still says "G4/G5 release gate" while body and siblings say the cutover completed; also says `rzr-watch` where the verb is `watch`.
3. `docs/decisions/0014-….md` carries `date: 2025-10-24` — ~10 months off its 2026-08-27 commit (likely meant 2026-08-24); no test checks ADR dates.
4. Five `docs/plans/2026-08-22-000356-*/plan.md` files still say "proposed" for work that demonstrably shipped and is regression-tested.

## Constraints any rewrite must preserve

- The test-pinned prose: status taxonomy set-equality, replan-accounting negative regex, repair caps, ordered precedence chain, README attribution table, shared-facts paragraph, ADR index ordering. Run `./tests/run.sh` after any docs/templates edit.
- The wire-level separations (event ≠ delivery ≠ ACK; prose-free notification; frozen report tuples) — these are the product's identity, not incidental strictness.
- The durability orderings (spool→send, commit→ack, generation→deliver, target→history) and the reset boundary.
- Runtime floors (bash 3.2, Python ≥3.11) unless explicitly re-decided.
