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
| `prompts/watchtower-model-selection.md` | Watchtower | Read before selecting the crew role/model/effort. It is a retrieval prompt, not crew instructions. |

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

Do not copy model-selection policy into crew-facing skills. Model and reasoning
effort are Watchtower routing choices; the crew skill describes how that role
performs its job after dispatch.

## Boundary rule

**Watchtower decides who should work and what evidence is sufficient. Crew does
repository planning, implementation, review, testing, and pipeline/recovery work.**

When a crew report exposes a new routing decision, the Watchtower consumes the
report, records the decision, and dispatches the next role. Do not silently change
the current crew's role just to avoid another dispatch.
