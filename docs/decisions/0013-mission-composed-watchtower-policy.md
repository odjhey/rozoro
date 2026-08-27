# ADR-0013: Mission-composed watchtower policy

review: approved
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
- Every launch records an all-or-none five-field policy tuple: the SHA-256 of
  exact core+mission bytes, core SHA-256, logical mission name, symbolic
  `shipped`/`operator` source, and mission SHA-256. This applies even without a
  name or preset and is preserved in current and historical registration.
- Resolution is descriptor-relative and no-follow. Checkout directories and
  shipped files must be effective-UID-owned and not group/world-writable;
  shipped files are singly-linked regular files. The effective home and its
  mission directory are owner-private real directories, and operator missions
  are owner-private singly-linked regular files. Unsafe candidates fail the
  launch even when the alternate candidate is safe.
- Core and mission bytes must be nonempty strict UTF-8 containing at least one
  non-whitespace scalar. TAB, LF, and CR are the only permitted C0/C1 controls.
  Bytes are not normalized and their exact form determines all hashes.
- The launcher rechecks both lexical paths and selected identities immediately
  before exec and dies on an ordinary mid-launch change.
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
- `ROZORO_HOME` when nonempty, then legacy `RZR_HOME` when nonempty, then
  `$HOME/.rozoro` is the single effective home precedence for presets, missions,
  registration, and other home-relative state.
- Pi passthrough cannot supply policy prompt options; the launcher alone owns
  exactly two `--append-system-prompt` pairs, core first and one mission second.
- A malicious or mistaken operator mission file changes watchtower behavior
  without VCS review. The filesystem contract from ADR-0011 (owner-private,
  no-follow, owned regular files, same-UID sabotage out of scope) applies to
  mission resolution unchanged; this ADR does not broaden that threat model.
- Project skills under `.agents/skills/` remain shared across all missions and
  are **not** scoped per preset or per mission. Presets must never carry their
  own skill set: two presets may share one mission, and preset identity is
  metadata (ADR-0011), so behavior must not vary by preset. A mission scopes
  skill *usage* textually by naming the skills it uses and staying silent on
  the rest; trigger-gated skills a mission never invokes are accepted context
  overhead. If shared skills prove harmful in practice (for example a
  delivery-only skill like `afk` misfiring on a non-delivery watchtower), the
  designated fix is mission tagging in skill frontmatter plus launcher/harness
  filtering, decided by a new ADR — not per-preset or per-mission skill
  directories.
- Known attribution gap, explicitly deferred: skill bodies steer watchtower
  behavior but are not part of `policy_sha256` or the policy snapshot. Any
  future decision that formalizes per-mission skills must also fold the
  effective skill set (paths and hashes) into policy attribution, or the
  mission hash stays precise while part of the effective policy floats free.
- The final pathname recheck does not prevent a same-UID process replacing a
  path after that check but before Pi opens it. That residual attribution race
  is explicitly accepted under ADR-0011's threat model; immutable handoff or
  stronger same-UID isolation requires a future architecture decision.
- ADR-0011's transport-derived driver identity, preset-name metadata semantics,
  registration/current-history behavior, locking, dispatch attribution, and
  filesystem threat model remain unchanged. ADR-0012's durable policy
  precedence is unchanged. This ADR supersedes ADR-0011 only on v1 policy
  selection.
