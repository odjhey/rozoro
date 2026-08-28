---
name: v2_test_strategy
description: "v2 test taxonomy: behavioural, capability, and technical suites — what belongs where, the sensitive-case list, and the mapping from v1's pinned guarantees."
type: architecture
tags: [v2, tests]
status: current
generated: "Claude Fable 5, 2026-08-28"
created_at: 2026-08-28T00:00:00+08:00
---

# Test strategy

Three dedicated kinds, three directories, no mixing. The rule of thumb: **behavioural** tests would survive a total rewrite of the internals; **capability** tests would survive a rewrite of the core; **technical** tests exist because a specific mechanism is dangerous to get wrong.

## Behavioural (`<code-root>/tests/behavioural/`)

Black-box over **commands**, with every port faked. They state what the product promises, in ubiquitous-language terms, and never mention providers.

- One file per bounded-context concern (task lifecycle, handoff/ack, availability derivation, generation/delivery algebra, reconcile, registration/authority, attention).
- Every v1 guarantee that concerns core semantics is carried over; the port starts from v1's suites (`lifecycle.bats`, `handoff.bats`, `ledger.bats`, `cli-event-bus.bats`, `test_reducer.py`, `test_delivery_ledger.py`, `test_notify.py`, `test_protocol.py`'s semantic cases). A tracking table in the phase-1 PR maps each v1 test name → v2 test or a retirement rationale. Nothing is dropped silently.
- Style rules: given/when/then over fakes; assertions on returned types and durable state via ports; no sleeps (fake clock); no filesystem outside the fake stores.

Representative promises (from v1, non-exhaustive): teardown preserves the durable record byte-for-byte; resume refuses a tracked task; a `done` report never changes availability or implies acceptance; twenty actionable events remain twenty facts through coalescing; an edge landing mid-reconcile re-nudges; generation ACK never resolves task open items; ambiguous identity is always fatal.

## Capability (`<code-root>/tests/capability/`)

Per-adapter certification: what a real backend can and cannot certify, and that the adapter tells the truth about it.

- Runs the shared **conformance suite** (per port, same tests against fake and real adapter) plus backend-specific cases.
- Each suite includes at least one **negative capability** case: version drift, missing flag, refused hook, absent background snapshot — asserting the adapter degrades to `unknown`/fail-closed rather than inferring.
- Live-gated cases follow v1's evidence discipline: env-gated (`exit 77` skip), producing dated, redacted fixtures (the `claude-hooks-2.1.240.json` pattern), with a test binding assertions to the fixture.
- Capability descriptors are themselves tested: the descriptor an adapter exports must match what its suite proves.

## Technical (`<code-root>/tests/technical/`)

For sensitive mechanics where a plausible-looking implementation can be subtly catastrophic. Reserved for cases on this list (extend it in the PR that needs it):

1. **Durability orderings** — spool-before-cursor, commit-before-ack, generation-before-delivery, target-before-history; crash injection at each boundary proves recoverability (v1: `test_client.py`, `test_store.py`).
2. **Concurrency** — concurrent reservation, registration, ledger mutation, delivery bumps; lock release on failure preserving exit status (v1: `lock.bats`, ledger 24-writer cases, registration APFS probe).
3. **Ordering domains** — producer-seq gap buffering and de-certification; replay permutations produce no false quiescence (v1: `test_reducer.py`).
4. **Security discipline** — symlink/hardlink/traversal/FIFO/control-char/rename-swap rejection; owner-private modes; socket identity proofs; parser-differential JSON (duplicates, surrogates, NaN); frame-size-before-parse (v1: `watchtower-security.bats`, `test_server.py`, `test_protocol.py`).
5. **Import boundary** — the AST walk enforcing the [dependency rules](./core-and-commands.md#dependency-rules-enforced-not-aspirational), plus a consumer audit in the spirit of v1's home-resolution source audit (registry + mutation-tested decoys).
6. **Wire codec exactness** — closed-set round-trip corpus (the v1 `protocol-v1/messages.ndjson` pattern: set-equality so an unfixtured message type fails).

## Harness and CI

- Same execution posture as v1: everything runs in a pinned, network-less, read-only container; sandbox sentinel guards; parallel by default with per-test tmpdirs. Reuse `tests/run.sh` machinery with a v2 phase.
- The v1 suite keeps running unchanged on this branch until cutover — v2 tests are additive.
- Docs-as-code checks extend to `v2/`: if a v2 doc pins a number or a name the code must honor, pin it with a test the way `test_policy_contracts.py` does.
