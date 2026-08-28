---
name: v2_registration_authority_context
description: "Registration & Authority bounded context — driver identity, validated wake targets, watchtower launchers, epochs/incarnations, and event-bus authority."
type: bounded-context
tags: [ddd, watchtower, registration]
status: v2-draft
generated: "Claude Fable 5, 2026-08-28"
created_at: 2026-08-28T00:00:00+08:00
---

> **v2 working copy** — forked from [`docs/architecture/bounded-contexts/registration-and-authority.md`](../../docs/architecture/bounded-contexts/registration-and-authority.md) at `b044dbe`. Iterate here; the v2 effort never edits the live architecture docs.

# Registration & Authority

**Core question:** which resident session may be woken, under which recorded policy?

## Responsibility

Bind a resident watchtower conversation to a transport-derived **driver identity**, validate that binding against live evidence before recording it, attribute the launch (preset bytes, composed policy digest), and manage which delivery mechanism holds **authority** for that driver.

## Owned state

- `watchtowers/<driver>/target.json` (commit point) + `registrations.jsonl` (append-only history, self-healing gaps) — the [registration contract](../contracts/registration.md).
- The `.event-bus-authority` marker and its transactional activate/rollback protocol.
- Launch-time identity: native session, per-launch **incarnation**, readiness handshakes (`poller-ready.<incarnation>`), registration **epochs** in the daemon (offers are per-epoch; reconnect creates a fresh epoch).

## Key behaviors

- **Never guess a backend from a bare environment variable** — the founding rule. Declared harness is verified against the live pane; ambiguous driver resolution is fatal; `auto` requires proof, not env presence.
- **Launchers** compose the resident session deterministically: Pi (policy-composed, extension-registered), Claude (preset-only, capability-gated, poller-registered). Both unset inherited attribution first and re-verify at the last moment (TOCTOU guards).
- **Attribution, not authorization**: watchtower names, presets, and policy digests are recorded metadata for after-the-fact accountability; delivery identity stays transport-derived (ADR-0011), and machine facts/presets/launcher defaults never grant authority (ADR-0012).
- Registration is a hardened security surface (traversal/symlink/hardlink/FIFO/control-char/rename-swap rejection, fail-closed, no-write on invalid ingress), with an explicitly fenced threat model: no forward-progress guarantee under same-UID sabotage.

## Invariants

- One driver directory per identity; concurrent registrations serialize per driver; duplicate canonical identities are ambiguous, not merged.
- Exact resume reuses the driver id but mints a new incarnation — stale terminal events from a previous life cannot poison the new registration.
- Authority transitions are transactional and conservative: activation requires an active daemon and a clean legacy ledger; rollback requires fully reconciled cursors and tombstones before removing the marker.
- Once authority is active, every legacy writer for that driver hard-refuses.

## Boundary rule

Registration & Authority owns *who may be woken and how that is recorded*. It does not own the wake decision (Wake Delivery), the policy content (Policy & Steering), or the session's runtime truth (Lifecycle Evidence).
