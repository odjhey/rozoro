# ADR-0013: Mission-composed watchtower policy

review: pending
date: 2026-08-27
supersedes: ADR-0011 (the "v1 has no policy override" boundary only)

## Context

ADR-0011 shipped versioned watchtower presets with an explicit v1 boundary: a
preset selects harness/model/effort but never policy content; every Pi launch
appends the one shipped `templates/watchtower.md`.

The Watchtower proved useful beyond delivering repository changes. Wanting a
project-manager watchtower (docs, boards, tickets — no coding fleet) surfaced
that `templates/watchtower.md` conflated two kinds of text: **mechanics** (rozoro
CLI usage, event loop, attention ledger, crew lifetime, briefs, registration)
that every watchtower kind needs and that must move in lockstep with the code,
and a **delivery mission** (worksets, Coder/Reviewer/Tester routing, No-Mistakes
Runner, merge authority, `/afk`) that is only one possible purpose.

An overlay model fails here: a non-delivery mission is not a delta on the
delivery policy — it would spend its text countermanding worksets and gates, and
negation overlays are fragile for an unattended agent. Full preset-resolved
replacement fails in the other direction: if the whole policy lived in
`$ROZORO_HOME` files, upgrading the checkout would silently desynchronize every
watchtower's instructions from the CLI behavior they describe.

## Options

1. Overlay — shipped policy always applies, preset appends a delta. Works for
   parameter tweaks; cannot express a genuinely different mission without
   negation text.
2. Full replacement keyed on preset identity — one file per preset resolved from
   `$ROZORO_HOME`. Single authority per preset, but mechanics leave VCS and
   drift from the code; preset *names* (metadata per ADR-0011) would acquire
   behavioral meaning.
3. Compose core + mission — VCS-owned mechanics core always appended, plus
   exactly one mission policy selected by an explicit preset field.

## Choice

Choose option 3.

- `templates/watchtower.md` becomes the **mechanics core**: watchtower identity,
  context accumulation, machine profile, dispatch/brief mechanics, event loop,
  crew lifetime, reporting. It is always appended and stays VCS-owned.
- A **mission policy** is always appended after the core. The former delivery
  content of `templates/watchtower.md` moves verbatim (minus mechanics) to
  `templates/missions/delivery.md`, the shipped default mission.
- The preset gains an optional `mission` string field (filename-safe, ≤120
  chars). Absent, and for unpreset launches, the mission is `delivery`, so
  existing launches keep their exact current policy content.
- Mission resolution is explicit and fail-closed: exactly one of
  `<checkout>/templates/missions/<name>.md` (shipped) or
  `$ROZORO_HOME/watchtower-missions/<name>.md` (operator-authored) may exist.
  Both existing is an ambiguity error; neither is an error. Operator missions
  let a new mission iterate outside VCS and graduate into `templates/missions/`
  once stable; the hash trail keeps both phases attributable.
- The mission is selected by the preset **field**, never inferred from the
  preset name. Names remain pure metadata (ADR-0011); renaming a preset must
  not change its policy, and several presets may share one mission.
- `ROZORO_WT_POLICY_SHA256` becomes the SHA-256 of the exact concatenated
  core+mission bytes delivered at launch. The registration schema is unchanged;
  which mission a tenure ran is recoverable through the recorded preset
  name/version/sha256, whose bytes include the `mission` field.
- The launcher rechecks both file identities immediately before exec and dies
  on a mid-launch change, extending the existing single-file guard.
- Composition is Pi-only for now: the Claude watchtower launcher appends no
  policy file today, and this decision does not change that.

## Consequences

- New watchtower kinds (project manager, triage, release shepherd) are new
  mission files plus a preset field — no launcher fork, no policy fork.
- Mechanics stay reviewable in VCS and cannot drift from the CLI they describe;
  mission content is the only per-kind variation point.
- The composed policy hash changes for every existing launch (two files now),
  so policy attribution is discontinuous at this migration; snapshots and
  registrations before/after are joined through this ADR, not through equal
  hashes.
- `watchtower-policy-snapshot` must capture the core plus shipped missions and
  per-mission composed hashes; operator missions under `$ROZORO_HOME` are
  enumerated as a coverage note but not captured from the checkout.
- A malicious or mistaken operator mission file changes watchtower behavior
  without VCS review. The filesystem contract from ADR-0011 (owner-private,
  no-follow, owned regular files, same-UID sabotage out of scope) applies to
  mission resolution unchanged; this ADR does not broaden that threat model.
- ADR-0011's registration, locking, and attribution decisions are otherwise
  unchanged.
