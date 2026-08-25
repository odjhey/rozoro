# Skill ownership and routing

Rozoro skills fall into two execution classes. Keep the boundary explicit so the
Watchtower does not accidentally perform repository work that belongs to crew,
and so crew-facing instructions are not lost at dispatch time.

## Watchtower-owned skills

The Watchtower executes these itself as part of orchestration, evidence
reconciliation, routing, and durable decision making.

| Skill or prompt | Owner | Watchtower action |
| --- | --- | --- |
| `delivery-evidence` | Watchtower | Invoke directly to reconcile exact-head evidence, decide what runs next, and record bounded decisions. |
| `attempt-budget` | Watchtower | Derive coder-attempt count from durable turns, enforce no attempt 11, and defer exhausted lineages while other runnable work exists. |
| `quick-crew-routing` | Watchtower | Decide whether a task qualifies for Quick Scout/Quick Coder; standard crew remains the default. |
| `no-mistakes-observer-pane` | Watchtower | Create/close an untracked observer pane around an active no-mistakes run without creating another crew or taking custody. |
| `prompts/watchtower-model-selection.md` | Watchtower | Read before selecting the standard crew role/model/effort. It is a retrieval prompt, not crew instructions. |

## Crew-facing skills

The Watchtower does **not** execute these as repository work. It recognizes the
need for the role, reads the relevant skill, includes the applicable instructions
in the crew brief, and dispatches the appropriate crew.

| Skill | Crew role | Watchtower action |
| --- | --- | --- |
| `task-decomposer` | Task Decomposer / Replanner | Dispatch a planning crew with the skill instructions included in its brief. Do not plan the repository task in Watchtower. |
| `independent-review` | Reviewer | Dispatch a fresh reviewer with the review instructions and bounded task/evidence in its brief. |
| `adversarial-testing` | Tester | Dispatch a tester with the testing instructions and bounded task/evidence in its brief. |
| `no-mistakes-branch-recovery` | No-Mistakes Runner | Dispatch/resume the dedicated runner with the recovery instructions in its brief. Watchtower judges the returned custody report. |
| `rozoro-authoring` | Coder working on Rozoro | Include the repository-specific authoring instructions in the coder brief. |
| `quick-scout` | Quick Scout | Include the narrow read-only contract and escalation marker in a Spark/low scout brief. |
| `quick-coder` | Quick Coder | Include the one-attempt mechanical implementation contract and escalation marker in a Spark/low coder brief. |

## Routing rule

Use `metadata.execution-owner` and `metadata.watchtower-action` as the quick
machine-readable distinction:

- `execution-owner: watchtower` + `watchtower-action: invoke-directly` means the
  Watchtower performs that skill itself.
- `execution-owner: crew` + `watchtower-action: dispatch-and-brief` means the
  Watchtower must dispatch the named crew role and include the relevant skill
  instructions in that crew's brief.

The `crew-role` metadata names the intended role for crew-facing skills.

## Briefing crew-facing skills

Rozoro does not currently pass a skill object or skill reference into a crew
session. Crew-facing skills are therefore **Watchtower briefing sources**.

A crew-facing skill is not considered applied merely because the Watchtower read
it. Before dispatch, the Watchtower must incorporate the applicable instructions
into the task brief that the crew actually receives.

Keep the brief focused: include the role contract, important constraints,
required report shape, and task-specific inputs. Do not paste unrelated policy or
turn the brief into a second copy of the whole skill library.

A future mechanism may support first-class skill delivery to crews. Until that
exists, do not claim repo-local skill discovery, presets, system rules, or a skill
name/reference alone as a supported way to transmit these instructions.

## Model routing

Current standard model selection remains authoritative in
`templates/watchtower-crew-dispatch-guidelines.md`. Current no-mistakes target
fallback also remains authoritative there/current no-mistakes policy.

`quick-crew-routing` is a bounded fast-path exception: eligible Quick Scout and
Quick Coder tasks use `gpt-5.3-codex-spark` at low effort. It does not redefine
any standard role assignment and must not be retried when the quick path fails.

Do not import machine-specific harness defaults into global role policy.

## Attempt budget

Implementation lineages have ten coder attempts derived from durable coder turns.
Attempt 10 may complete normal review/test/gate assurance. If that evidence asks
for another coder repair, do not start attempt 11.

An exhausted lineage is deferred while other runnable work exists. Reconsider
deferred work when the runnable queue is empty, or earlier only when materially
new evidence/tooling changes the premise or the operator explicitly reprioritizes
it.

## Boundary rule

**Watchtower decides who should work and what evidence is sufficient. Crew does
repository planning, implementation, review, testing, and pipeline/recovery work.**

When a crew report exposes a new routing decision, the Watchtower consumes the
report, records the decision, and dispatches the next role. Do not silently change
the current crew's role just to avoid another dispatch.
