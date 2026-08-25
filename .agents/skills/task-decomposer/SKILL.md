---
name: task-decomposer
description: >-
  Turn a broad, ambiguous, or repeatedly failing software task into one or more
  bounded implementation tasks with explicit contracts, dependencies, acceptance
  criteria, and unresolved decisions. Use for planning or escalation replanning;
  do not implement the change while using this skill.
metadata:
  derived-from: docs/runbooks/role-separated-delivery.md,templates/watchtower-crew-dispatch-guidelines.md
---

# Task decomposer

Produce work a coder can execute without reopening the whole plan.

Explicit operator instructions and repository-local rules take precedence over this skill.

## Initial decomposition

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

## Replanning mode

Use replanning when implementation, review, or testing is looping without convergence, or when a finding exposes a contract or scope conflict.

Start from the original bounded task plus the useful evidence from failed attempts. Do not dump unrelated conversation history into the new plan.

Report:

- likely reason earlier attempts failed;
- approaches that should not be repeated;
- newly discovered constraints or dependencies;
- revised scope and boundaries;
- revised acceptance criteria;
- recommended implementation direction;
- evidence the next coder should inspect;
- human decisions still unresolved.

A replanned task replaces only the parts it explicitly changes. Preserve unaffected operator and repository constraints.
