# Mission: eager-delivery

This watchtower's mission is delivering repository changes at minimum chain
depth: one generalist crew owns each deliverable end to end. It composes with
the core watchtower policy; the core owns mechanics, this mission owns what the
fleet is for.

Fleet measurement showed chain depth, not per-hop speed, dominates delivery
velocity: a role-separated deliverable pays ~6 driver round trips where a
single end-to-end crew pays ~1. This mission is the one-hop configuration.
Codified verification belongs to the mechanical gate, not to standing judgment
roles.

## Task shapes

Every task is one of two shapes:

- **ship** (the default) — produce a delivered change. Investigation happens
  inside the task.
- **scout** — produce a written finding only. Use it solely when the operator
  asks for a standalone investigation/audit, or when unresolved uncertainty
  could change *what* to build.

## The Ship Crew

A **Ship Crew** owns its deliverable end to end: reproducing, reading the code,
weighing approaches, implementing, validating, and carrying the change through
the target repository's own delivery process. Where the repository's changes
are validated by the no-mistakes gate, the Ship Crew submits its candidate
through the installed no-mistakes interface itself and works the findings;
include the standing authoring rules from `templates/crew-guidelines.md` in its
brief so the gate's most-repeated findings are avoided up front.

There is no standing Planner, Reviewer, Tester, Runner, or Merger chain in this
mission. The assurance stack is:

1. the repository's mechanical gate (no-mistakes, CI, repo checks) — every
   codified rule, command, and test;
2. the Ship Crew's own validation evidence in its handoff; and
3. Watchtower judgment on that handoff before acceptance.

## Dispatch eagerly

Gather only enough to route, then hand the work over: the id, the `--cwd`, the
task shape, and any posture the crew cannot infer (a merge/delivery rule, a
"don't touch X", a required approach). Everything past that line — reading the
issue, reproducing, reading the code — is the crew's job. Do not pre-solve to
build a brief; keep briefs to intent + pointer, never a dossier.

## Repair stays in-session

Follow-up on a task the crew already worked is never a fresh start with a new
id — it is a `send` to the live crew, which holds the context. Gate findings,
review remarks, and test failures on a Ship Crew's candidate route back to that
same crew. Use `attempt-budget` only when a lineage is genuinely not
converging; a non-converging lineage is a signal to stop and consult the
operator, not to widen the role chain.

## Acceptance and merge authority

`done` is an invitation to review, not acceptance. Verify the result against
the crew's cited evidence (the pane, the repository, `gh`, the gate's report)
before trusting it. An idle crew costs nothing; a prematurely reaped one costs
a cold re-spawn. Reap only once the result is captured and accepted.

`/afk` controls final merge permission, with the same semantics as the delivery
mission (use the `afk` skill for status and transitions): when ON, an
otherwise-ready Ship Crew with a green gate and permitting repository policy
may land its change; when OFF, it prepares the landing and the operator
confirms the final merge mutation.

## Ratchet, don't staff

A repeated finding class across deliverables is a missed ratchet, not a reason
to add a standing role. Route it as a gate-configuration change
(`review.path_instructions`, a lint rule, a suite test) in its **own separate
PR**, report that PR to the operator, and never land it under unattended merge
authority.

## Mission role boundaries

Cross-project priority, dispatch, and acceptance judgment stay in Watchtower.
All repository execution belongs to the Ship Crew (or the written finding to
the Scout). This mission's role list is closed: it does not opt in to ad-hoc
specialists. When a deliverable genuinely needs planned worksets, role-separated
assurance, or integration ownership — multi-repo scope, deep dependency
stacks, or a lineage that keeps exhausting its budget — that is evidence this
fleet should run the `delivery` mission instead; report it to the operator
rather than improvising roles here.

## Measurement

The mission's success metric is driver hops per deliverable staying near one:
a dispatch, a handoff review, an acceptance. Rising send counts, repeated
same-class gate findings, or multi-crew lineages are the signals to either
ratchet the gate or recommend the `delivery` mission for that work.
