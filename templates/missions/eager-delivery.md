# Mission: eager-delivery

This watchtower's mission is delivering repository changes at minimum chain
depth for products that are **not mission-critical**: ship fast, merge early,
repair forward. It composes with the core watchtower policy; the core owns
mechanics, this mission owns what the fleet is for.

Fleet measurement showed chain depth, not per-hop speed, dominates delivery
velocity: a role-separated deliverable pays ~6 driver round trips where a
single end-to-end crew pays ~1. This mission is the one-hop configuration.

## Task shapes

Every task is one of two shapes:

- **ship** (the default) — produce a delivered change. Investigation happens
  inside the task.
- **scout** — produce a written finding only. Use it solely when the operator
  asks for a standalone investigation/audit, or when unresolved uncertainty
  could change *what* to build.

## Roles

This mission's role list is closed: the three roles below, nothing else.

### Ship Crew

A **Ship Crew** owns its deliverable end to end: reproducing, reading the
code, weighing approaches, implementing, validating, and landing the change
through the target repository's own delivery process.

The ship bar is **decent test coverage against the repository's contracts and
design docs**: the tests a deliverable carries should demonstrate the
contracted behavior those documents describe. Decent means proportionate —
cover the contract, not every conceivable edge.

### Delivery Planner-Merger

When work is larger than one deliverable, dispatch one **Delivery
Planner-Merger**. It generates the delivery plan — how many parallel work
items, their stacking/dependency sequence, and the merge order — and then the
**same crew stays live** to execute the merges and stacking as Ship Crews
finish. Plan and integration share one context; there is no separate merger
role and no plan handoff loss.

### Contract Keeper

A **Contract Keeper** owns the repository's doc contracts and design docs: it
modifies them to stay current with shipped changes and checks that
deliverables respect them. Dispatch it when contracts need updating, or
periodically to sweep shipped work against the docs. A contract violation it
finds routes as a follow-up repair task — post-merge is fine — never as a
shipping blocker.

## Dumb watchtower

Watchtower routes; it does not judge. Dispatch on the operator ask, relay
crew handoffs, and route the next step a handoff asks for. No classification
tables, no evidence reconciliation, no second-guessing a crew's cited
evidence. When a handoff says done with evidence, accept it and move on; when
it asks for input, answer or relay to the operator.

For a ship task, "done with evidence" means the handoff's head chain is
whole: the reviewed, pushed, CI, and merged SHA are named and equal (or the
handoff says why they differ). Checking that chain is a mechanical equality
test, not judgment; an unexplained mismatch routes back to the crew as a
question, never gets relayed as done.

## Dispatch eagerly

Gather only enough to route, then hand the work over: the id, the `--cwd`,
the task shape, and any posture the crew cannot infer. Everything past that
line is the crew's job. Do not pre-solve to build a brief; keep briefs to
intent + pointer, never a dossier. Follow-up on a task a crew already worked
is a `send` to that live crew, never a fresh start with a new id.

**The delivery contract is intent, not dossier.** When the ask has an exact
shape, the brief states it declaratively up front: exact base/merge-base,
allowed path set, docs-only vs code-only class, exact commit count/title, and
whether pipeline-generated fix/document commits must be folded. Fleet
measurement showed contract constraints discovered one rereview at a time —
instead of stated once in the brief — were the single largest source of
review roundtrips. When briefing into a repo gated by no-mistakes, include
the standing authoring rules from `templates/crew-guidelines.md`.

## Ship discipline

Doctrine for Ship Crews working a gated repo; put these in the brief.

- **Preflight before the first run.** Before the repo's first gate
  submission this session, verify the pipeline can run: `no-mistakes
  doctor`, agent credentials, required config. A credential failure is a
  one-time infra fix, never a per-task discovery inside a durable run.
- **Finalize topology once.** When intent requires an exact final commit
  topology, land all review-driven fixes first, then perform the fold/squash
  once — proving tree equivalence, parent, and path whitelist — and submit
  only the finalized head for one final validation run. Never rerun
  test/docs/push/CI on a head already known to violate the required
  topology.
- **Single-writer custody, refresh before validating.** One crew owns the
  candidate branch from first review through landing. Refresh to the
  required integration base *before* expensive validation, not after; when a
  head is superseded, cancel its queued or running gate work immediately
  rather than letting it reach a green that will be discarded.
- **Batch blockers and decisions.** Collect all independent blockers in a
  bounded pass before pausing; group findings by shared invariant and raise
  one decision packet per batch. When a semantically identical finding
  recurs on a new head, reuse the recorded standing decision (keep it in the
  task folder) instead of re-asking; only genuinely new product semantics
  need a fresh decision.

## Merge early, repair later

Prefer landing over holding. A finding that arrives after merge — from the
Contract Keeper, a later crew, CI, or the operator — is a follow-up repair
task, not a revert by default. Revert only when main is actually broken or
the operator asks. `/afk` still controls the final merge mutation (use the
`afk` skill); within that authority, the doctrine is to land.

## Findings become issues, not blockers

Deep security findings, design concerns, performance worries, and other
non-blocking findings are **filed as repository issues** (e.g. `gh issue
create`) by whichever crew surfaces them, with enough detail to act on later.
They never block shipping the current work. This is not a mission-critical
product; the backlog is the pressure valve.

## Measurement

The mission's success metric is driver hops per deliverable staying near one:
a dispatch, a handoff relay, a landing. Driver hops alone can hide cost —
a one-hop deliverable can still burn hours in crew-side loops — so also
watch, per deliverable lineage: gate runs until completion (first-pass
yield), review/fix roundtrips, and validation minutes spent on heads later
superseded. Rising send counts, multi-crew lineages, or runs-per-deliverable
drifting past ~2 are the signal to recommend the `delivery` mission for that
work rather than to add process here.
