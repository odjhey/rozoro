# Skill ownership and routing

Project skills under `.agents/skills/` are **Watchtower tools**. Rozoro does not
currently transmit a skill object or skill reference into a crew session.

Do not use skills as a prompt-template layer. Watchtower remains responsible for
understanding the current task, choosing the next task kind, and writing the
smallest useful brief for that crew.

## Watchtower action skills

| Skill | When Watchtower uses it |
| --- | --- |
| `crew-model-selection` | Before every fresh Rozoro crew dispatch: choose task kind and current canonical model/effort. |
| `quick-crew-routing` | Decide whether a bounded task qualifies for Quick Scout/Quick Coder. |
| `no-mistakes-gate` | Submit/reattach and drive the external no-mistakes run, reconcile exact-head/custody evidence, and route findings. |
| `no-mistakes-observatory` | Maintain the dedicated untracked Herdr visualization surface for active no-mistakes run graphs. |
| `delivery-evidence` | Reconcile exact-head review/test/CI/delivery evidence and make bounded Watchtower decisions. |
| `attempt-budget` | Enforce the coder-attempt budget and defer exhausted implementation lineages. |

These skills guide Watchtower's own routing/coordination actions. They are not
blocks of text to paste into a crew prompt.

## Crew briefs are authored by Watchtower

The old `brief-*` skill layer was removed because it made Watchtower behave like a
prompt forwarder. Standing role/model policy lives in
`templates/watchtower-crew-dispatch-guidelines.md`; the actual brief is composed
for the task at hand.

Default style:

> **intent + pointer + only the context, constraints, and evidence this crew needs**

A brief may be only a few lines. Do not paste the role policy, repeat the target
repository's own rules, or force every task into the same report/checklist shape.
The crew should have enough context to exercise judgment.

Examples of task-specific information worth adding:

- Planner: raw operator request/issue plus exclusions or decisions already made.
- Coder: bounded task or repair finding plus acceptance criteria that are not
  obvious from the source pointer.
- Reviewer/Tester: exact candidate head and the task/acceptance source.
- Merge Finisher: PR, expected exact head, landing evidence, allowed merge path,
  and post-merge work that actually applies.
- Quick Crew: the exact narrow question/change and its stop/escalation boundary.

## Planner is the normal bounding step

For new implementation work, raw operator intent normally goes through the Task
Decomposer before Coder. Skip that planning turn only when the implementation task
is already genuinely bounded, this is a normal repair turn for the same coder, or
Quick Coder clearly qualifies.

Watchtower should not inspect the repository deeply enough to replace the Planner.
Dispatch the specialist instead.

## No-mistakes is not crew

No-mistakes is a Watchtower-managed external gate. It owns its pipeline worktree,
internal agents/model selection, branch custody, PR/CI work, and supported recovery
surface. Watchtower uses `no-mistakes-gate` to submit/reattach, drive supported
gates, and reconcile the result.

There is no No-Mistakes Runner crew and no no-mistakes briefing skill.

## No-mistakes Observatory

No agent pane owns the no-mistakes graph.

Use one persistent, untracked **no-mistakes Observatory** Herdr tab per Watchtower
workspace. Put one `no-mistakes attach` pane in that tab for each active gate/run,
using enough task/run identity to distinguish concurrent pipelines.

The Observatory is deliberately separate from Planner/Coder/Reviewer/Tester/Merge
Finisher panes and from the Watchtower pane. It does not consume crew capacity and
must not become a second no-mistakes controller.

Keep terminal graph/scrollback visible through the associated landing/post-merge
episode when practical so the operator can compare stage behavior and identify
optimization opportunities. For durable analysis, retain run IDs and prefer
structured timing/retry/fix/model evidence from no-mistakes rather than scraping
the TUI.

## Merge/post-merge is crew

Once Watchtower judges that the candidate is eligible to land, it dispatches a
**Merge Finisher** (`gpt-5.6-luna`, low). The finisher performs repository/provider
merge and required post-merge activities and returns exact landed evidence.
Watchtower does not perform the repository mutation itself.

Merge Finisher activity does not consume coder attempts unless a later failure is
routed to a Coder for a new implementation turn.

## Boundary

**Watchtower chooses, briefs, dispatches, drives external gates, reconciles
evidence, and decides what runs next. Crew performs repository planning,
implementation, review, testing, merge, and post-merge work. No-mistakes performs
its own pipeline work under its own custody. The Observatory is presentation only.**
