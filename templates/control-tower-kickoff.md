# Control-tower kickoff

Operator template for handing a plan to an unattended control-tower (driver)
session. Fill every `{{…}}` and paste as the opening prompt. This is the
operator-side counterpart of [`watchtower.md`](watchtower.md): that file is the
wake-consumer's standing rules; this one is the mission brief that starts a run.

The skeleton reproduces the kickoff that drove the event-bus build-out
(plan → 16 stacked PRs, unattended); the review/lifecycle sections encode what
that run's retrospective showed was missing.

---

## 1. Mission and source of truth

Work `{{plan-doc-path}}` to completion. That document is the only scope
authority; reviewer findings beyond it need my sign-off or an explicit
narrow/waive note in the handoff.

## 2. Crew policy

Role model/effort assignments come from the durable operator policy under
`$ROZORO_HOME/watchtower-policies/` (ADR-0012); do not restate them here. Use
this section only for run-specific deviations:

- explicit operator-authorized assignments for this run: `{{none, or role: target}}`
- Such assignments may override durable preferences only where repository policy
  permits; they cannot silently waive repository constraints or global denials.
- coding effort assignment: `{{durable policy, or explicit authorized target}}`
  for concurrency, persistence, and protocol slices — one expensive coder turn
  beats six review rounds.

## 3. Autonomy

I am AFK. Go with your recommendations and record each decision in the task
handoff instead of waiting. Ask me only for: scope changes to the plan,
destructive or irreversible actions, and spend beyond `{{limit, or "none"}}`.

## 4. Review and validation contract

- Reviewers enumerate all findings in one pass; coders fix in batch.
- Middle re-review rounds are deltas (changed files plus a prior-findings
  checklist); full audits only on the first and final rounds.
- Crews own full-suite runs; reviewers trust green CI at the exact head and
  spend their own runs only on live/behavioral probes CI cannot perform.
- Gate evidence ships as a machine-checkable manifest (claims mapped to
  executable test sources), committed with the PR.

## 5. Lifecycle and hygiene

- Keep crews resident; resume, never respawn. Teardown is VCS-agnostic and
  never refuses based on repository state. Conservatively avoid reaping within
  minutes of recent operator focus on the pane. This release adds no
  recent-focus or pending-input enforcement; generic runtime safeguards remain
  a separate #67 concern.
- Handoff `did:` stays around five lines; long evidence goes in task-folder
  files, not the handoff block.
- Maintain a running story/index doc at `{{story-doc-path}}` mapping
  PRs ↔ landed SHAs ↔ coding/review task IDs as slices land.

## 6. Continuation and stop conditions

Continue (stacking PRs if needed) until `{{done-condition, e.g. "the plan's
acceptance criteria hold and the final PR is in human merge review"}}`.
Stop and wait for me when: `{{stop-conditions}}`.

## 7. Fallbacks and quotas

`{{fallback accounts/harness commands, known quota limits, and what to do when
each is hit — declare these now, not mid-incident.}}`
