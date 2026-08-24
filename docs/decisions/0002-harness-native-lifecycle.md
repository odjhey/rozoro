# ADR-0002: Harness-native lifecycle is semantic truth

review: approved
date: 2026-08-22

## Context

Herdr can tell Rozoro where an agent is hosted and whether a pane/process appears live or idle. That host-level information is useful, but it cannot reliably answer semantic questions such as whether a harness turn is complete or whether native background/subagent work is still active.

Treating terminal idleness as semantic completion created exactly the kind of false-settled behavior the event-bus work was designed to remove.

## Options

1. **Use Herdr state as completion truth.** Simple and generic, but unable to represent harness-native background activity reliably.
2. **Normalize harness-native lifecycle evidence.** Let adapters certify foreground/background facts and derive conservative availability, using Herdr for hosting/liveness/actuation.
3. **Infer completion from output/report files only.** Useful as task evidence, but too late or incomplete for runtime availability.

## Choice

Use **harness-native lifecycle evidence as the semantic authority** for runtime state whenever the harness exposes sufficient evidence.

Herdr remains the host abstraction for tabs, panes, liveness, addressing, and supported actuation. It is not sufficient proof that a harness turn is semantically complete.

If an adapter cannot certify a fact, prefer `unknown` to guessing from terminal idle state.

## Consequences

- Availability and task/report verdict remain separate axes.
- Adapters may differ internally but must normalize into the same conservative product semantics.
- Pi and Claude can provide stronger semantic integration than harnesses whose native lifecycle contracts are not yet proven.
- Codex/Copilot parity should be evidence-driven rather than implemented by optimistic inference.
- Defensive Herdr reconciliation remains useful for membership/liveness without becoming semantic completion authority.
