# ADR-0005: Keep workflow policy above Rozoro core

review: approved
date: 2026-08-24

## Context

A watchtower may coordinate rich engineering patterns such as planning, implementation, independent review, and testing. Those patterns differ by repository and team. Encoding them directly into Rozoro would couple the core to repository-specific concepts such as pull requests, test gates, branch policy, and merge authority.

## Options

1. Encode common engineering workflows directly in Rozoro core.
2. Keep Rozoro focused on durable task/session/lifecycle/attention primitives and let prompts, skills, and higher layers compose those primitives.
3. Use only harness-native child agents and never create independent crew tasks.

## Choice

Keep repository workflow policy **above Rozoro core**.

Rozoro owns durable task identity, session launch and follow-up, exact resume linkage, lifecycle/event/projection truth, and attention/delivery state. The watchtower, prompts, skills, and any future separate work-graph layer decide how those primitives are composed into planner/coder/reviewer/tester-style workflows.

Harness-native child agents remain inside their parent crew unless an independent Rozoro task is deliberately useful for separate context, lifecycle, or accountability.

## Consequences

- Rozoro remains portable across repositories with different delivery rules.
- Coordination policy can evolve without forcing core schema changes.
- Crew-role names may influence launch profiles without becoming core workflow states.
- Independent reviewer/tester contexts can be preserved when desired without hard-coding that sequence into the runtime.
- A future work-graph layer should consume Rozoro as a substrate and own graph-specific state separately.
- Core interfaces should expose machine-stable lifecycle and attention outputs so higher layers do not need to parse human-oriented prose.
