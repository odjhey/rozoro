# Watchtower runbooks

These runbooks capture reusable operating practices for Watchtower and crew. They
are current guidance; repository-specific instructions and explicit operator
constraints still apply to the target work.

## Runbooks

- [Dispatch and lifecycle](dispatch-and-lifecycle.md) — route work, follow durable
  handoffs, and retain useful crew context.
- [Role-separated delivery](role-separated-delivery.md) — plan, implement, assure,
  integrate, run no-mistakes, and land worksets with clear role ownership.
- [No-mistakes custody](no-mistakes-custody.md) — configure a profile, submit or
  reattach through the No-Mistakes Runner, and retain exact run/custody evidence.
- [Watchtower machine profile](machine-profile.md) — describe machine-local
  harness/model/account and no-mistakes profile availability without making it
  repository policy.
- [Human gates and exact-head evidence](human-gates-and-evidence.md) — preserve
  decisions that genuinely require human authority and bind evidence to immutable
  heads.
- [Proportional assurance](proportional-assurance.md) — dispatch only the
  evidence deficits a changed-head reconciliation identifies, with worked
  pipeline-fix and integration examples.

## How to use them

Load the runbook that applies to the current action. A Watchtower does not need to
read every runbook before starting useful work.

Project context should accumulate from the repository, plans, task handoffs,
assurance results, workset integration, delivery outcomes, and operator steering.
Keep facts scoped to the project/workset that produced them and reuse durable
results when they constrain later work.

The optional machine profile answers a different question from repository docs:
**what can this machine run?** Repository/operator policy answers **what should
this project do?** The Watchtower combines both when selecting and routing crew.
