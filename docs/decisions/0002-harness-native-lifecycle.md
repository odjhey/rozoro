# ADR-0002: Harness-native lifecycle is semantic truth

review: approved
date: 2026-08-22

## Context

Herdr can tell Rozoro where an agent is hosted and whether a pane/process appears live or idle. That host-level information is useful, but it cannot reliably answer semantic questions such as whether a harness turn is complete or whether native background/subagent work is still active.

Treating terminal idleness as semantic completion created exactly the kind of false-settled behavior the event-bus work was designed to remove.

## Options

1. **Use Herdr state as completion truth.** Simple and generic, but unable to represent harness-native background activity reliably.
2. **Normalize structured harness lifecycle evidence.** Prefer an upstream protocol such as ACP when it carries enough evidence; otherwise use the thinnest adapter needed to certify foreground/background facts and derive conservative availability.
3. **Infer completion from output/report files only.** Useful as task evidence, but too late or incomplete for runtime availability.

## Choice

Use **structured harness lifecycle evidence as the semantic authority** for runtime state whenever the harness or an upstream protocol exposes sufficient evidence.

Herdr remains the host abstraction for tabs, panes, liveness, addressing, and supported actuation. It is not sufficient proof that a harness turn is semantically complete.

Rozoro-specific adapters are an implementation choice, not the product requirement. Prefer ACP/acpx or another proven upstream lifecycle contract when it can provide the same conservative facts. If no source can certify a fact, prefer `unknown` to guessing from terminal idle state.

## Consequences

- Availability and task/report verdict remain separate axes.
- Different lifecycle sources may normalize into the same conservative product semantics.
- Pi and Claude currently provide stronger Rozoro-specific semantic integration than harnesses whose structured lifecycle contracts are not yet proven.
- Codex/Copilot parity is evidence-driven; test ACP/acpx or upstream contracts before adding more Rozoro-specific adapter surface.
- Defensive Herdr reconciliation remains useful for membership/liveness without becoming semantic completion authority.
