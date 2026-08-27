# ADR-0009: Separate Watchtower intelligence from the Rozoro control plane

review: pending
date: 2026-08-25

## Context

Rozoro began with a concrete operating setup: a smart control-tower agent, TUI harnesses, Herdr tabs/panes, durable task folders, and a resident event path. As zxro and Beads are extracted/adopted and future requirements include ACP/acpx, tmux, browser/desktop frontends, remote or headless hosts, the product identity can no longer be defined by those current implementations.

The existing architecture already distinguishes task identity from host binding, harness lifecycle truth from terminal idleness, Watchtower judgment from repository work, and UI observation from semantic authority. The next boundary is to make those distinctions explicit at the product interface.

## Options

1. **Keep Rozoro defined by the current Herdr + TUI harness stack.** Lowest migration cost, but every new host/frontend/runtime becomes another special case and current implementation details remain product semantics.
2. **Make each subsystem expose its own independent public API/daemon.** Flexible, but creates overlapping control planes and pushes composition complexity into every client.
3. **Define Rozoro as an active control plane around a harness-neutral Watchtower role, with semantic ports and adapters.** Keep zxro/Beads as durable sibling systems, use `rozorod` as the single resident composition/activation authority, and treat Herdr/ACP/tmux/browser implementations as replaceable adapters.

## Choice

Propose option 3.

A **Watchtower** is a smart coordinating agent role, not a specific model, harness, daemon, pane, or UI. Any supported smart-agent host may embody the role when it has the Watchtower policy, authority, durable-state access, runtime-control capability, and wake/reconciliation path.

**Rozoro** is the active local-first control plane through which the Watchtower operates independent agent runtimes. It owns runtime/host adapter composition, active event/wake integration, Watchtower activation, and the machine-facing control surface. It does not own the Watchtower's judgment.

The target semantic boundaries are:

- **Work/planning:** Beads (or another provider satisfying the work-graph contract) owns accepted dependency/readiness topology.
- **Durable execution/attention:** zxro owns stable work/turn/session-binding/artifact/mailbox semantics where adopted.
- **Agent runtime:** a harness-neutral Runtime Port exposes start/describe/send/control/resume/stop with explicit capabilities.
- **Runtime lifecycle sources:** adapters normalize structured lifecycle facts without treating host idle as semantic completion.
- **Host:** a Host Port represents replaceable live hosting such as Herdr, tmux, subprocess, SSH, or containers.
- **Frontend:** browser/TUI/desktop/Herdr views are non-authoritative clients of the same stable resources.
- **Resident active authority:** `rozorod` supervises adapters, coalesces/serves wake activation, and is the natural server for a future versioned Rozoro Control Protocol.

The CLI remains valuable UX but should evolve toward a client/facade over semantic operations rather than being the only machine contract.

No required zxro daemon is introduced. zxro remains invocation-scoped durable infrastructure unless a future demonstrated requirement justifies an optional service implementing the same contracts.

## Consequences

- Herdr becomes the first Host/Frontend adapter rather than part of Rozoro's identity.
- ACP/acpx/native harnesses become Runtime/Lifecycle adapters rather than separate orchestration modes.
- A browser or desktop frontend does not need to host the runtime it displays.
- The Watchtower may run headless and may be hosted by different smart-agent harnesses without changing its role semantics.
- Current high-level commands such as `start`, `send`, `resume`, and `status` may remain as convenience facades while their internals are decomposed into stable operations.
- Host-specific escape hatches such as raw key presses must not become portable runtime semantics.
- `restart` should not remain an ambiguous semantic primitive where exact resume, new-turn replacement, or host rebind is the real intent.
- Durable attention and work/execution truth should not be duplicated permanently in `rozorod` once zxro/Beads take ownership; `rozorod` should remain the active supervisor/facade rather than another copied source of truth.
- New adapters should be validated by capability/conformance contracts instead of model/harness-name conditionals.

The detailed target surface and current-vs-target inventory live in [`../control-plane-contracts.md`](../control-plane-contracts.md).
