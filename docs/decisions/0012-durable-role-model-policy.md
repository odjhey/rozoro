# ADR-0012: Role model assignments live in durable operator policy

review: pending
date: 2026-08-27
supersedes: ADR-0006 (residual model-routing authority)

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
- Resolution order for a fresh dispatch: explicit operator instructions,
  repository-local constraints, durable operator policy, machine availability
  from `$ROZORO_HOME/config/machine.md`, then current crew presets. On a machine
  with no durable policy set, selection is machine-profile/preset/operator
  driven.
- The Watchtower's own harness/model/effort is launch selection, not crew
  dispatch: the canonical operator path is a versioned preset under
  `$ROZORO_HOME/watchtower-presets/` (ADR-0011). Unpreset launches remain
  supported but register without attribution.
- Policy *content* (`templates/watchtower.md`) stays VCS-managed and hashed into
  each registration; presets have no policy override (ADR-0011 v1).

## Consequences

- Model routing has a single current authority again; repository diffs of the
  dispatch guide are semantics-only.
- Model/effort changes no longer require a repository PR and therefore lose VCS
  review. Attribution comes from `watchtower-policy-snapshot` artifacts, preset
  version/byte hashes, and registration records instead.
- Fresh machines without a durable policy set get no model defaults from the
  repository; the machine profile, presets, or the operator must supply them.
- ADR-0006's first authority bullet ("standard role/model/effort selection in
  `templates/watchtower-crew-dispatch-guidelines.md`") is retired; the rest of
  the ADR-0006/ADR-0009 resolution is unchanged.
- Future cross-machine policy snapshots reconcile against the durable policy
  set, not against repository templates.
