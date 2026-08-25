# Watchtower crew dispatch guidelines

Use these defaults when you dispatch crew. Keep each crewmate focused on one job. Do not let roles blur together just because a crew is already running.

Use the canonical model IDs written below. Reasoning effort is a separate setting. Do not invent model names from the shorthand, for example `luna-high` or `gpt-5.6-luna-high`.

Only the **No-Mistakes Runner** runs no-mistakes. Do not ask the coder, reviewer, tester, decomposer, or replanner to run it as part of their own work.

* **Task Decomposer, `gpt-5.6-sol`, high reasoning effort**

  * If the task or plan is too broad, ambiguous, or lacking context, break it into bounded tasks that a coder can execute.
  * Use the existing contracts, ports, repo docs, dependencies, boundaries, and anything else relevant in the docs.
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

  * Give the coder the output from the Task Decomposer.
  * The coder should implement that task, not reopen the whole plan.
  * The coder should follow the supplied contracts, ports, repo conventions, boundaries, and acceptance criteria.
  * If you send the coder a reviewer or tester report, the coder should treat that report as the reason for the new turn and address it.
  * If the task no longer makes sense, conflicts with an existing contract, or needs a broader design change, the coder should stop and report that instead of inventing a new plan.
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
  * Ask it to review the implementation against the task, contracts, surrounding code, and acceptance criteria.
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
  * Tests should come from the use case, contracts, decomposition, acceptance criteria, and failure modes, not only from reading the implementation.
  * Cover the happy path, boundaries, invalid inputs, retries, partial failures, state transitions, integration points, and regressions that matter to the task.
  * Ask the tester to measure whether the use case is complete, not just whether code coverage went up.
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

* **No-Mistakes Runner, target selected by `no-mistakes-harness-selection`**

  * This is the only crew role that runs no-mistakes.
  * Dispatch it after normal coding, review, and test work when you want the no-mistakes pass.
  * Ask it to run the actual no-mistakes workflow. Do not substitute a normal review prompt.
  * Before a fresh runner dispatch, use `.agents/skills/no-mistakes-harness-selection/SKILL.md`.
  * When the effective no-mistakes model-selection setting is `auto`, no-mistakes uses the model of the harness that invoked it. Select the workflow target by launching the runner under the intended harness/model/account context; do **not** save, override, and restore global no-mistakes model configuration merely to select a target.
  * Use this fixed fallback order:
    1. Claude Sonnet in the primary/default Claude account context.
    2. If that target is usage-limited or cooling down, Claude Sonnet in the configured secondary Claude account context.
    3. If that target is also unavailable, Pi with exact `gpt-5.6-luna` at high reasoning effort.
  * Conceptually, a Claude target means the runner itself is launched as `claude --model sonnet` in the intended account context. The Pi fallback means the runner itself is launched as Pi with `gpt-5.6-luna`/high. With no-mistakes selection `auto`, the workflow inherits that invoking harness/model.
  * If Rozoro cannot independently launch one configured account/profile target, treat that target as unavailable and proceed to the next configured target. Do not mutate global no-mistakes model configuration as a workaround.
  * The same `auto` inheritance principle applies to other supported harnesses such as Codex, but that does not add them to this fallback list. Only declared targets are normal Watchtower choices.
  * Do not hold the task waiting on a higher-priority target's cooldown when a later configured target is ready.
  * If every target in the order is unavailable, report that condition. Do not silently choose an undeclared target.
  * Explicit target/model overrides are for debugging or controlled experiments, not normal crew dispatch.
  * Keep harness identity, account/profile identity, model ID, and reasoning effort separate. Do not derive model IDs from human-readable labels.
  * It should look for things the coder, reviewer, and tester may all have missed, including failure paths, concurrency, retries, idempotency, cleanup, corrupted state, security boundaries, regressions, and bad assumptions.
  * Once the runner has started an actual no-mistakes run, Watchtower must use `no-mistakes-observer-pane` to create the untracked sibling Herdr observer pane when supported and run `no-mistakes attach` there. Do not wait for an operator request. Observer creation failure is non-blocking only when the supported pane operation is unavailable/fails; record the reason and continue the real runner.
  * Ask for a report that includes:
    * verdict;
    * defects or risks found;
    * evidence;
    * affected contract, invariant, or use case;
    * whether the problem is local or needs re-planning;
    * remaining uncertainty;
    * no-mistakes selection mode;
    * execution target/account profile in non-secret form;
    * harness, model ID, and reasoning effort actually used by the no-mistakes workflow;
    * fallback position and reason, when fallback occurred;
    * `attempt_count`;
    * `caused_by`.

* **Escalation Replanner, `gpt-5.6-sol`, high reasoning effort**

  * Use this when repeated coder, review, or test loops are not converging.
  * Before you dispatch it, harvest the useful reports from the current crew and abandon that crew as the active owner.
  * Give the replanner the original decomposed task plus the useful evidence from the failed attempts.
  * Do not dump the full conversation history into it unless something in that history is needed.
  * The replanner should work out why the current task keeps failing and produce a revised task for a fresh coder.
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

  * You own dispatch and routing.
  * Keep the global view across all tasks and reports.
  * Decide what should run next, which crew gets the next report, when to retry, when to abandon a crew, and when to re-plan.
  * For ordinary review or test failures, send the report back to the active coder as the next assignment.
  * If repeated attempts stop converging:
    1. harvest the useful reports;
    2. abandon the current crew;
    3. dispatch the Escalation Replanner;
    4. take the revised task;
    5. dispatch a fresh Coder.
  * Keep no-mistakes as its own dispatch. Do not fold it into review or testing.
  * Decide when the task has enough evidence to be considered done.

## Experimental report fields

For now, ask crews to include these in their reports:

```text
attempt_count: 3
caused_by: tester report #2, retry/idempotency case failed
```

`attempt_count` is the number of relevant turns or attempts known from the task history.

`caused_by` is the report, finding, or failure that caused the current turn. Leave it empty when there is no clear predecessor.

Keep these as report fields for now. Do not make them part of Rozoro's lifecycle contract yet. We are testing whether they help us measure repair loops, escalation, and cost-to-done.
