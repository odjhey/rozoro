# Proportional assurance via evidence-deficit dispatch

Use this runbook when a candidate changes and the question is "which assurance
must rerun?" The generic model applies to every artifact type — implementation,
documentation, configuration, generated output, dependencies, pipeline fixes,
rebases, and integration changes — not to any one of them.

## The model

1. **Planner** records the workset assurance map: acceptance/judgment questions,
   the evidence owner per question, the evidence required, the change classes
   that invalidate it, and which assurance may run concurrently. Small bounded
   work uses a concise default map.
2. **Workset Merger** (or a named reconciliation owner it routes) records a
   changed-head reconciliation after every candidate-changing action: old/new
   commit/tree/base/merge-base, changed paths and cause, affected judgment
   questions, evidence that remains current, evidence that became stale, and the
   minimum next checks required.
3. **Watchtower** dispatches only the evidence deficits that reconciliation
   identifies. Missing or incomplete reconciliation fails closed before
   post-gate Reviewer/Tester dispatch and before final readiness.

Impact class comes from affected-question analysis, never from file type, file
count, or diff size. The exact routing table lives in the dispatch guidelines'
"Evidence-deficit dispatch" section.

## Representative routing decisions

| Change at the new head | Affected questions | Dispatch |
|---|---|---|
| Formatting-only gate autofix; provenance/comment touch-up | none (mechanical/provenance) | exact-head gate rerun; retain prior judgment with recorded rationale |
| Public function contract altered during repair | design/contract/correctness | gate, then focused Reviewer on the changed questions |
| Retry/idempotency behavior changed; new failure mode introduced | behavior/test-design | gate, then focused Tester on the changed questions |
| Repair changes both a contract and observable behavior | both | gate, then focused Reviewer and focused Tester in parallel on the same frozen head |
| Rebase onto a moved base; workset integration merge | integration/base | Workset Merger changed-head reconciliation first, then only the affected assurance |
| Dependency bump with verified-identical build output and no contract change | none affected | no redundant Reviewer/Tester rerun; scoped no-new-judgment rationale in the reconciliation |

Uncertain impact is its own deficit: route a focused judgment turn to settle the
impact analysis instead of guessing "small means safe."

## Worked example: candidate-changing pipeline fix

A Coder reports candidate `A` (commit/tree/base/merge-base recorded). The
no-mistakes gate runs, applies a lint autofix, and reports final head `B ≠ A`.

1. The gate's report keeps separate submitted (`A`) and final (`B`) identity
   records.
2. Before any post-gate Reviewer/Tester dispatch for `B`, the reconciliation
   owner records: `A → B` identities, changed paths (the autofixed files) and
   cause (gate lint autofix), affected questions (none — formatting only),
   evidence current (gate green for `B`), evidence stale (any judgment bound to
   `A` is context, not assurance for `B`), and minimum next checks (none beyond
   the already-green gate).
3. Watchtower dispatches Reviewer and Tester against `B` for the task's original
   judgment questions — those are first-time deficits, not reruns — and retains
   nothing that claims to be prior judgment of `B`, because none exists yet.
4. Had the "fix" instead changed a conditional (a correctness question), the
   reconciliation would mark that question affected and the dispatch would be
   gate-for-`B` plus focused Reviewer on that question — not a full re-review of
   the whole task, and not a shrug because the diff was one line.

Absent the reconciliation record, dispatch and readiness both fail closed.

## Worked example: integration/base change

Tasks T1 and T2 are stacked; T1 lands and T2 is rebased from base `X` onto the
new default-branch head `Y`, producing head `C → C'`.

1. The Workset Merger records the reconciliation: `C → C'` with old base `X`,
   new base/merge-base at `Y`, changed paths (rebase-touched files plus anything
   conflict resolution edited), and cause (integration/base change).
2. Affected-question analysis: a clean rebase with no textual or semantic
   overlap against T1's changes affects no judgment question; a conflict
   resolution that edited T2's logic affects the correctness and
   behavior/test-design questions for the edited paths.
3. Either way `C'` is a new exact candidate: the gate reruns for `C'` first.
4. Then Watchtower routes only the affected deficits — nothing more for the
   clean rebase beyond the recorded retention rationale; focused Reviewer and/or
   Tester on the conflict-touched questions otherwise.
5. Prior gate/Reviewer/Tester observations for `C` remain context bound to `C`;
   the reconciliation is the provenance that says what carried forward and why.

## Convergence

- When Reviewer and Tester deficits are independent, fan both out on one frozen
  head and collect both results before one combined repair batch.
- A candidate-changing repair re-enters the gate once, then reruns only the
  affected questions.
- Two repeated failures with the same root cause trigger an ownership/authority
  checkpoint (Replanner, ownership change, or operator decision), not a blind
  third attempt.
- Repeated finding classes become repository tests, lint rules, or explicit
  gate/policy configuration where feasible, so the gate owns future enforcement.
- Assurance-only reruns consume no Coder attempts when no candidate-writing
  Coder turn occurred; `attempt-budget` owns the accounting.
