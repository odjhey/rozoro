# Rozoro product documentation

`docs/` is the product alignment point for Rozoro: the place to describe the system we are intentionally converging toward, while keeping the distinction between **already shipped substrate**, **required capabilities**, and **still-open implementation ownership** explicit.

The README remains the operator-facing description of the current CLI. Implementation plans describe delivery sequences. These product docs describe the durable concepts and boundaries that should survive individual implementations.

## Start here

- [Current vs target](current-vs-target.md) — what has already shipped and what remains intentionally ahead of implementation.
- [Architecture](architecture.md) — product boundaries, ownership, and integration map.
- [Artifact lifecycle](artifact-lifecycle.md) — when the major durable/runtime artifacts are created and what survives teardown.
- [Dated Watchtower artifacts](dated-watchtower-artifacts.md) — immutable policy snapshots and conservative task-evidence progress reports.
- [Ubiquitous language](ubiquitous-language.md) — canonical terms for code, prompts, issues, reviews, and docs.
- [Decisions](decisions/README.md) — ADR-lite records for decisions that constrain future work.
- [Implementation plans](plans/) — historical and active implementation sequencing.
- [Watchtower runbooks](runbooks/README.md) — reusable operator procedures with provenance and exclusions.

## Product direction

Rozoro exists so one primary watchtower can coordinate a substantial fleet of independent agent sessions without becoming a tab-juggler or relying on conversational memory for fleet state.

The intended operating model is:

1. The **operator** supplies intent, business priority, and final acceptance.
2. The **watchtower** decomposes/dispatches/steers work and presents factual fleet state, but does not silently invent business priority.
3. **Crew sessions** do repository/domain work using the target repository's own rules and tools.
4. Structured harness lifecycle facts are normalized conservatively; terminal hosting/liveness is not semantic completion truth.
5. The current `rozorod` path durably records normalized events and reduces them into current projections before wake delivery is considered authoritative.
6. Wake **generations** are delivery batches, not task identities and not operator work items.
7. The target product requires stable task-scoped **attention-item identity** and partial handling. We call this the Watchtower Mailbox capability, but ACP/acpx and existing local-first tools should be evaluated before Rozoro owns another subsystem.
8. Task open-item resolution, notification delivery, watchtower reconciliation, attention-item handling, and operator acceptance remain distinct operations.

## Principles

- **One primary watchtower, many crews by default.** Improve attention bookkeeping before multiplying watchtowers.
- **Operator priority is not technical severity.** `failed`, `blocked`, `needs-action`, and `completed` are facts; the operator decides what matters first.
- **Persist facts before notifying.** Durable events and projections are the source for recovery and reconciliation.
- **Projection is current truth.** Events answer what happened; projections answer what is true now.
- **Delivery batches are not work items.** Coalescing may reduce wake spam, but it must not erase per-task attribution.
- **Task identity outlives hosting.** Brief, handoff history, and exact-resume linkage survive host teardown.
- **Prefer adoption over reinvention.** Product contracts can remain firm while their implementation is delegated to ACP/acpx or another dependency that satisfies them.
- **Keep Rozoro small.** Repository workflows, PR policy, testing policy, merge authority, and harness-native subagent orchestration remain outside the core.

## Reading rule

When a document describes something not yet implemented, it must say so. When a capability is required but implementation ownership is still open, say that too. Target-state language is useful only if readers can tell where current runtime behavior ends and the intended product begins.
