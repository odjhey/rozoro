---
name: brief-task-planner
description: >-
  Brief a Task Decomposer or Escalation Replanner crew. Use when Watchtower is
  spawning a planning crew for broad, ambiguous, or non-converging repository
  work and needs to put the decomposition/replanning contract into that crew's
  brief. Watchtower routes the work; the dispatched crew performs the planning.
---

# Task planner briefing guideline

Use this when **Watchtower is preparing the brief for a Task Decomposer or
Escalation Replanner crew**. Take the applicable instructions below, combine them
with the task-specific source pointers and constraints, and include them in the
crew brief before dispatch.

Do not perform the repository investigation or decomposition in Watchtower merely
because this skill is loaded. Repository investigation and planning remain work
for the dispatched crew.

Explicit operator instructions and repository-local rules take precedence over this guideline.

## Initial decomposition contract to brief

1. Identify the requested outcome and the source of truth for scope.
2. Read the relevant repository contracts, ports, docs, interfaces, dependencies, and boundaries needed to split the work correctly.
3. Separate product or operator decisions from implementation choices the coder may make locally.
4. Split only where a boundary is real: independent behavior, dependency order, ownership boundary, or acceptance surface. Do not create tiny tasks merely to make a longer plan.
5. For each task, state:
   - scope and intended outcome;
   - relevant contracts, interfaces, and repository rules;
   - dependencies and ordering constraints;
   - explicit acceptance criteria;
   - important exclusions;
   - assumptions;
   - unresolved ambiguity that requires a decision.
6. Do not implement, edit production code, or certify a solution.

## Replanning contract to brief

Use replanning when implementation, review, or testing is looping without convergence, or when a finding exposes a contract or scope conflict.

Start from the original bounded task plus the useful evidence from failed attempts. Do not dump unrelated conversation history into the new plan.

Require the crew to report:

- likely reason earlier attempts failed;
- approaches that should not be repeated;
- newly discovered constraints or dependencies;
- revised scope and boundaries;
- revised acceptance criteria;
- recommended implementation direction;
- evidence the next coder should inspect;
- unresolved decisions that must be surfaced to the Watchtower.

A replanned task replaces only the parts it explicitly changes. Preserve unaffected operator and repository constraints.
