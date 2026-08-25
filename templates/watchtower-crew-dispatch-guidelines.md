# Watchtower crew dispatch guidelines

Use these defaults when you dispatch **Rozoro crew**. Keep each crewmate focused
on one job. Do not let roles blur together just because a crew is already running.

Use the canonical model IDs written below. Reasoning effort is a separate setting.
Do not invent model names from shorthand, for example `luna-high` or
`gpt-5.6-luna-high`.

No-mistakes is **not** a Rozoro crew role. Watchtower drives it directly through
the `no-mistakes-gate` skill after normal coding/review/testing assurance.

* **Task Decomposer, `gpt-5.6-sol`, high reasoning effort**

  * If the task or plan is too broad, ambiguous, lacking context, or not yet
    bounded enough for a coder, break it into executable tasks.
  * Use the existing contracts, ports, repo docs, dependencies, boundaries, and
    anything else relevant in the docs.
  * Make the acceptance criteria explicit.
  * Do not implement.
  * Do not run no-mistakes.
  * Ask for a report that includes:
    * task scope;
    * relevant contracts and ports;
    * dependencies;
    * acceptance criteria;
    * assumptions;
    * unresolved ambiguity.

* **Coder, `gpt-5.6-sol`, low reasoning effort**

  * Give the coder the bounded task from the Task Decomposer when planning was
    needed.
  * The coder should implement that task, not reopen the whole plan.
  * The coder should follow the supplied contracts, ports, repo conventions,
    boundaries, and acceptance criteria.
  * If you send the coder a reviewer, tester, no-mistakes, or post-merge finding,
    the coder should treat that report as the reason for the new turn and address
    it.
  * If the task no longer makes sense, conflicts with an existing contract, or
    needs a broader design change, the coder should stop and report that instead
    of inventing a new plan.
  * Do not ask the coder to review its own work.
  * Do not ask the coder to run no-mistakes.
  * Ask for a report that includes:
    * what changed;
    * checks and tests run;
    * findings addressed from the report that caused this turn;
    * remaining failures or blockers;
    * assumptions made;
    * whether the task now needs re-planning;
    * `attempt_count`;
    * `caused_by`.

* **Reviewer, `gpt-5.6-luna`, high reasoning effort**

  * Give the reviewer a fresh context.
  * Ask it to review the implementation against the task, contracts, surrounding
    code, and acceptance criteria.
  * It should look outside the diff when that is needed to judge correctness.
  * A green test suite is not enough.
  * Ask it to separate real defects from optional cleanup and style preferences.
  * Do not ask the reviewer to fix production code.
  * Do not ask the reviewer to run no-mistakes.
  * Ask for a report that includes:
    * verdict;
    * concrete findings and evidence;
    * affected contract or acceptance criterion;
    * impact;
    * what needs correction;
    * whether the problem looks local or the task needs re-planning;
    * `attempt_count`;
    * `caused_by`.

* **Tester, `gpt-5.6-luna`, high reasoning effort**

  * Ask the tester to try to break the implementation.
  * Tests should come from the use case, contracts, decomposition, acceptance
    criteria, and failure modes, not only from reading the implementation.
  * Cover the happy path, boundaries, invalid inputs, retries, partial failures,
    state transitions, integration points, and regressions that matter to the
    task.
  * Ask the tester to measure whether the use case is complete, not just whether
    code coverage went up.
  * Ask it to inspect the quality of the tests too:
    * Would the tests fail if the implementation were wrong?
    * Are assertions strong enough?
    * Are mocks or fixtures hiding failures?
    * Are important scenarios missing?
    * Could a broken implementation still get a green suite?
  * A green suite does not prove that the use case is complete.
  * Do not ask the tester to quietly fix production code.
  * Do not ask the tester to run no-mistakes.
  * Ask for a report that includes:
    * tests added or run;
    * failures found;
    * acceptance criteria with direct test evidence;
    * scenarios still uncovered;
    * weak or misleading existing tests;
    * cases where broken behavior could still pass;
    * whether the problem looks local or the task needs re-planning;
    * `attempt_count`;
    * `caused_by`.

## No-mistakes gate — Watchtower action, not a crew role

After the candidate has the normal coding/review/testing evidence and a clean,
committed exact head, Watchtower may send it through no-mistakes assurance.

Use `.agents/skills/no-mistakes-gate/SKILL.md`.

* Do **not** dispatch a No-Mistakes Runner through `./bin/rozoro start`.
* Submit or reattach the candidate through the repository's supported
  no-mistakes/AXI path, including the configured `no-mistakes` Git remote where
  that is the repository contract.
* Record the exact submitted branch/head/tree, run ID, base, and operator intent.
* no-mistakes owns its disposable worktree, branch custody, internal agents,
  internal model/fallback selection, fixes, PR work, and CI work performed by its
  pipeline.
* Watchtower owns run submission/reattachment, structured observation, bounded
  gate responses, exact-head/custody reconciliation, and routing the resulting
  findings back to crew.
* Once a real run exists, invoke `no-mistakes-observer-pane` and attach the
  untracked side pane beside Watchtower. The pane is display-only.
* While no-mistakes owns the branch/worktree, do not issue competing Git
  mutations. Follow structured AXI/no-mistakes recovery instructions exactly.
* On an actionable defect, send the finding back to the active coder when it is a
  local repair. Use the Escalation Replanner when the finding exposes a contract,
  scope, or task-boundary problem.
* If no-mistakes' desired internal agent/account/fallback behavior cannot be
  expressed by the installed no-mistakes version, treat that as an integration or
  no-mistakes configuration gap. Do not add a wrapper LLM crew to simulate it.

* **Merge Finisher, `gpt-5.6-luna`, low reasoning effort**

  * Use this after Watchtower has decided that the candidate has sufficient
    pre-merge evidence and is eligible to land.
  * Read `.agents/skills/brief-merge-finisher/SKILL.md` and include its landing
    contract, exact candidate/evidence identities, merge policy, and required
    post-merge checks in the crew brief.
  * Before merging, verify the current PR head still matches the expected
    candidate and that required review/test/no-mistakes/CI evidence still applies
    to that exact head.
  * Use only the repository/provider-supported merge path and allowed merge
    method. Do not bypass branch protection, disable checks, force refs, or widen
    permissions merely to land the change.
  * Capture the actual merge commit or equivalent landed identity returned by the
    provider. Do not infer it from the PR head.
  * Perform the required post-merge checks/actions from the task or repository
    policy against the actual landed identity.
  * Do not quietly fix production code, regenerate stale assurance, or improvise
    rollback. Report blockers or post-merge failures back to Watchtower.
  * Ask for a report that includes:
    * expected and actual pre-merge PR head;
    * evidence/checks verified before merge;
    * merge method/path and provider result;
    * actual merge/landed commit;
    * post-merge checks/actions and exact evidence;
    * cleanup performed, if any;
    * any race, blocker, stale evidence, or post-merge failure; and
    * whether the change is fully landed/healthy or needs another routed task.

* **Escalation Replanner, `gpt-5.6-sol`, high reasoning effort**

  * Use this when repeated coder, review, test, no-mistakes, or delivery-repair
    loops are not converging, or when evidence exposes a contract/scope problem.
  * Before you dispatch it, harvest the useful reports from the current crew and
    gate/delivery history.
  * Give the replanner the original decomposed task plus useful evidence from the
    failed attempts.
  * Do not dump the full conversation history unless something in that history is
    needed.
  * The replanner should work out why the current task keeps failing and produce
    a revised task for a fresh coder.
  * It should not make another implementation attempt.
  * It should not run no-mistakes.
  * Ask for a report that includes:
    * likely reason the previous attempts failed;
    * approaches that should not be repeated;
    * new constraints or dependencies discovered;
    * revised scope;
    * revised boundaries;
    * revised acceptance criteria;
    * recommended implementation direction;
    * evidence the next coder should inspect;
    * `attempt_count`;
    * `caused_by`.

* **Watchtower, `gpt-5.6-sol`, high reasoning effort**

  * You own dispatch and routing for Rozoro crew.
  * Keep the global view across all tasks, reports, external-gate state, and
    delivery state.
  * Decide what should run next, which crew gets the next report, when to retry,
    when to abandon a crew, when to re-plan, when a candidate is ready for
    no-mistakes, and when it is eligible to hand to Merge Finisher.
  * For ordinary review, test, local no-mistakes, or local post-merge failures,
    send the report back to the active coder as the next assignment when that is
    still the correct task boundary.
  * If repeated attempts stop converging:
    1. harvest the useful reports and gate/delivery evidence;
    2. abandon the current implementation crew as active owner;
    3. dispatch the Escalation Replanner;
    4. take the revised task;
    5. dispatch a fresh Coder.
  * Drive no-mistakes directly through `no-mistakes-gate`; do not create a runner
    crew for it.
  * Do not perform repository merge/post-merge mutations yourself. Once landing is
    authorized by current evidence/policy, dispatch Merge Finisher.
  * Reconcile the Merge Finisher's exact landed identity and post-merge evidence
    before deciding the task is complete.

## Experimental report fields

For now, ask crews to include these in their reports:

```text
attempt_count: 3
caused_by: tester report #2, retry/idempotency case failed
```

`attempt_count` is the number of relevant turns or attempts known from the task
history.

`caused_by` is the report, finding, or failure that caused the current turn. Leave
it empty when there is no clear predecessor.

Keep these as report fields for now. Do not make them part of Rozoro's lifecycle
contract yet. We are testing whether they help us measure repair loops,
escalation, and cost-to-done.