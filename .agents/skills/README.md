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
need for the role, dispatches the appropriate crew, and makes the relevant skill
instructions available in that crew's context.

| Skill | Crew role | Watchtower action |
| --- | --- | --- |
| `task-decomposer` | Task Decomposer / Replanner | Dispatch a planning crew; pass or expose the skill. Do not plan the repository task in Watchtower. |
| `independent-review` | Reviewer | Dispatch a fresh reviewer; pass or expose the skill and bounded task/evidence. |
| `adversarial-testing` | Tester | Dispatch a tester; pass or expose the skill and bounded task/evidence. |
| `no-mistakes-branch-recovery` | No-Mistakes Runner | Dispatch/resume the dedicated runner; pass or expose the recovery skill. Watchtower judges the returned custody report. |
| `rozoro-authoring` | Coder working on Rozoro | Make the repository-specific authoring rules available to the coder. |

## Passing crew-facing skills

A crew-facing skill is not considered applied merely because the Watchtower read
it. The dispatched crew must actually receive or be able to discover the
instructions.

Use the least-duplicative supported mechanism available:

1. repo-local skill discovery when the target checkout already contains the skill;
2. crew preset/system rules when the role is a standing crew configuration; or
3. an explicit prompt/reference that makes the relevant skill instructions
   available to the crew.

A skill name alone is not sufficient when the target crew cannot resolve that
skill from its own context. In that case the Watchtower must pass the instructions
or a resolvable source reference, not assume the crew inherited the Watchtower's
skill context.

Do not copy model-selection policy into crew-facing skills. Model and reasoning
effort are Watchtower routing choices; the crew skill describes how that role
performs its job after dispatch.

## Boundary rule

**Watchtower decides who should work and what evidence is sufficient. Crew does
repository planning, implementation, review, testing, and pipeline/recovery work.**

When a crew report exposes a new routing decision, the Watchtower consumes the
report, records the decision, and dispatches the next role. Do not silently change
the current crew's role just to avoid another dispatch.
