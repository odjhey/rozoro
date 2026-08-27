# Shared facts across all watchtowers

These invariants hold for every watchtower regardless of which preset launched
it or which mission it runs. A change to any fact here is an architecture
change and needs an ADR, not a mission edit.

## Composition

- Every Pi watchtower boots the same **mechanics core**
  (`templates/watchtower.md`) plus **exactly one mission** (ADR-0013). There is
  no mission-less watchtower: an unpreset launch or a preset without a
  `mission` field runs the shipped `delivery` mission.
- The **preset** selects the mission by its `mission` field, never by preset
  name. Preset names are metadata (ADR-0011); several presets may share one
  mission.
- A **mission** describes what the fleet is for: its task kinds, specialist
  roles (the fleet members), assurance flow, authority boundaries, and which
  skills it uses. The core owns mechanics; the mission owns purpose. Where a
  mission assigns a decision owner, that assignment governs.
- Mission resolution is fail-closed: exactly one of
  `templates/missions/<name>.md` (shipped) or
  `$ROZORO_HOME/watchtower-missions/<name>.md` (operator-drafted) may exist.

## Shared mechanics (the core, identical for every mission)

- Rozoro is the hands: `./bin/rozoro` start/send/status/reconcile/ack from this
  checkout, one `--cwd` per crew, repository implementation belongs to crew.
- The event-driven loop: `rozorod` delivers crew notifications; reconcile,
  record attention items via `watchtower-attention-ledger`, route, ACK, idle.
  A fresh/compacted/resumed session primes the ledger from disk first.
- Crew lifetime rules, brief style (intent + pointer + only needed context),
  follow-up via `send` versus fresh crew on task-kind change, and
  evidence-based reporting.

## Shared state and substrate (one namespace, not partitioned per mission)

- The effective home is nonempty public `$ROZORO_HOME`, else nonempty legacy
  `$RZR_HOME`, else `$HOME/.rozoro`; `ROZORO_HOME` wins when both are set. This
  one namespace is shared by all watchtowers on the machine: task folders
  (`tasks/`), state, the event bus (`rozorod`, monitor.db), artifacts,
  registrations (`watchtowers/<driver-id>/`), presets
  (`watchtower-presets/`), operator missions (`watchtower-missions/`), durable
  operator policy (`watchtower-policies/`), and the machine profile
  (`config/machine.md`).
- Tasks, crews, and attention state are **not mission-namespaced today**. Any
  watchtower can see any task. Coexisting towers rely on operator discipline,
  not enforced partitioning.
- Project skills under `.agents/skills/` are **shared across all missions**
  and are never preset- or mission-scoped (ADR-0013). A mission scopes skill
  *usage* textually by naming the skills it uses; unused trigger-gated skills
  are accepted context overhead. Skill bytes are not yet part of policy
  attribution — a recorded, deferred gap.

## Shared policy layers and precedence

The resolution order is the same for every watchtower: explicit operator
instructions > repository-local constraints (per crew `--cwd`) > durable
operator policy (`$ROZORO_HOME/watchtower-policies/`, e.g. role/model
assignments per ADR-0012) > machine availability (`config/machine.md`) >
mission policy > mechanics core > skills and repository templates (role
contracts only; they intentionally name no models).

## Shared attribution

- Driver identity is transport-derived (ADR-0011); the watchtower **name** is
  operator metadata and never identity.
- Every Pi launch records the complete five-field policy tuple. Every preset
  launch records preset name, operator-managed version, and exact preset-byte
  SHA-256. A named-unpreset launch records only its name plus
  harness-applicable attribution. Pi unnamed/unpreset and named/unpreset have
  the policy tuple but no preset/model attribution; Pi presets have all three.
  Claude unnamed/unpreset has none, Claude named/unpreset has only a name, and
  Claude presets have name/preset/model attribution but never the Pi tuple.
  `target.json` is current attribution; `registrations.jsonl` is history.
- `watchtower-policy-snapshot` captures the core plus shipped missions with
  per-mission composed hashes; operator missions are noted as not-captured.

## Operating model

- **One primary watchtower by default** (ADR-0001). Named presets and missions
  make additional towers attributable, but multiple concurrent towers remain a
  scaling option, not the default response to attention pressure. Business
  priority and final acceptance stay with the operator in every mission;
  technical severity is factual metadata, never an automatic work order.

## What varies per mission (everything else)

Task kinds, fleet roles and their boundaries, assurance flow and what
"verified" means, unattended-versus-ask authority, and the skill subset in
use. `templates/missions/delivery.md` is the reference implementation.
