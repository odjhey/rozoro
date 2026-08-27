# ADR-0012: Role model assignments live in durable operator policy

review: approved
date: 2026-08-27
supersedes: ADR-0006's concrete repository-owned role/model/effort table and Quick Crew model choice only

## Context

ADR-0006 declared the standard role/model/effort selection in
`templates/watchtower-crew-dispatch-guidelines.md` authoritative. Since then,
ADR-0009 added the machine-local routing profile, ADR-0011 added versioned
watchtower presets for launch selection, and the operator now maintains a
durable policy set under `$ROZORO_HOME/watchtower-policies/` (for example
`roles-and-models.md`) whose own precedence rule says later operator updates
supersede older policy.

That left two competing authorities for the same role/model table. The VCS copy
hard-coded machine- and account-specific model IDs, and drift was already real:
the repository template preferred `gpt-5.3-codex-spark` for Quick Crew while
current durable operator policy forbids that model and the machine profile notes
the harness is unavailable on this machine. Because durable policy is not in
VCS, the drift was invisible to repository review.

## Options

1. Keep the VCS table authoritative and mirror it into durable policy —
   preserves reviewability, but keeps duplicate authorities and puts
   machine-specific model IDs in every checkout.
2. Move the whole dispatch guide (contracts included) out of VCS — one
   authority, but role semantics lose repository review and crews get briefed
   from unreviewed text.
3. Split by kind: VCS keeps role contracts and dispatch semantics; concrete
   harness/model/effort assignments live in durable operator policy; the machine
   profile stays availability input; watchtower presets own the Watchtower's own
   launch selection.

## Choice

Choose option 3.

- `templates/watchtower-crew-dispatch-guidelines.md` and crew-facing skills
  describe role contracts, dispatch semantics, and briefing shape only. They
  intentionally name no models.
- Concrete per-role harness/model/effort assignments are durable operator policy
  under `$ROZORO_HOME/watchtower-policies/`.
- Resolve a fresh dispatch in phases: (1) apply explicit operator requirements
  and repository constraints; incompatible mandatory constraints block, (2)
  apply the role contract and all durable operator policy, including global
  denials, (3) filter authorized candidates through freshly verified machine
  availability, and (4) realize the authorized selection with a crew preset or
  use an ordered fallback only when operator or durable policy explicitly names
  it. Machine facts, presets, and launcher defaults never grant authorization.
- Durable global prohibitions and operational limits apply to every shipped,
  aliased, mission, and ad-hoc role. Resolve an exact durable role entry first,
  then a documented canonical alias, then one nearest analogous named role. An
  analog is valid only when exactly one role boundary contains the work and the
  mission narrows it, considering authority, mutation rights, work type, and
  assurance posture. Never splice one role's authority with another's target.
- Missing policy, a missing role assignment, unavailable or ambiguously available
  targets, and non-unique analogs fail closed. Split the mission or obtain an
  explicit authorized assignment. Do not fall through to machine guidance,
  presets, or built-in defaults. Re-verify stale availability claims; dated
  operator prohibitions remain binding until explicitly superseded.
- Quick Crew uses an authorized fast assignment or routes to an independently
  resolvable standard role; it never invents a fast target. Existing live crews
  are not restarted solely for a later policy change.
- The Watchtower's own harness/model/effort is launch selection, not crew
  dispatch: watchtower presets under `$ROZORO_HOME/watchtower-presets/` select
  only the resident Watchtower target (ADR-0011). Crew presets are execution
  configurations for an already-authorized crew target. Neither is role policy.
- Policy *content* (`templates/watchtower.md`) stays VCS-managed and hashed into
  each registration; presets have no policy override (ADR-0011 v1). No-mistakes
  pipeline target/fallback selection remains governed separately by trusted
  repository/global no-mistakes configuration.

## Consequences

- Model routing has a single current authority again; repository diffs of the
  dispatch guide are semantics-only.
- Model/effort changes no longer require a repository PR and therefore lose VCS
  review. Attribution comes from `watchtower-policy-snapshot` artifacts, preset
  version/byte hashes, and registration records instead.
- Fresh machines without durable role policy block unless an explicit
  operator/repository-authorized target is supplied.
- ADR-0012 supersedes only ADR-0006's concrete repository-owned role/model/effort
  table and concrete Quick Crew model choice. ADR-0009 already supersedes
  ADR-0006 for its stated scope and remains authoritative for machine-profile
  purpose and runtime verification; ADR-0012 does not supersede ADR-0009.
  ADR-0011 remains orthogonal launch-attribution authority.
- Future cross-machine policy snapshots reconcile against the durable policy
  set, not against repository templates.
