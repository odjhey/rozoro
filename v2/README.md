---
name: v2_index
description: "Landing point for the v2 rewrite: the charter and the independently-iterated mirror of the architecture suite."
type: index
tags: [v2, architecture]
status: v2-draft
generated: "Claude Fable 5, 2026-08-28"
created_at: 2026-08-28T00:00:00+08:00
---

# Rozoro v2

This directory is the v2 rewrite's workspace. It contains two things:

1. **The charter** — [charter.md](./charter.md): goals, ground rules, phase plan, and the decision log, with its supporting docs ([goal and scope](./goal-and-scope.md), [core and commands](./core-and-commands.md), [ports and adapters](./ports-and-adapters.md), [test strategy](./test-strategy.md)).
2. **The mirror** — a full copy of [`docs/architecture/`](../docs/architecture/README.md) in the same structure ([product architecture](./product-architecture.md), [ubiquitous language](./ubiquitous-language.md), [bounded contexts](./bounded-contexts/README.md), [contracts](./contracts/README.md), [rewrite seams](./rewrite-seams.md)), forked at `b044dbe`.

## The iteration rule

**v2 iterates only here.** The live `docs/architecture/` suite keeps describing `master` (which is in production use) and is never edited from the v2 effort. Target-state changes — a contract tightened, a port added, a context re-drawn, a seam resolved — are made to the mirror copies in this directory. Every mirrored file carries a fork banner naming its live counterpart; the divergence between mirror and live *is* the rewrite's design delta, reviewable at any time with:

```sh
diff -ru docs/architecture v2 --exclude=charter.md --exclude=goal-and-scope.md \
  --exclude=core-and-commands.md --exclude=ports-and-adapters.md --exclude=test-strategy.md
```

## Reading order

1. [Charter](./charter.md) — why v2 exists, ground rules, phases, decisions.
2. [Goal and scope](./goal-and-scope.md) — what phase 1 must deliver.
3. [Core and commands](./core-and-commands.md), [Ports and adapters](./ports-and-adapters.md), [Test strategy](./test-strategy.md) — the structural commitments.
4. The mirror, starting at [product architecture](./product-architecture.md) — the semantics v2 implements, iterated toward target state.

## Status convention

Mirrored files start as `status: v2-draft` and byte-identical to their live counterpart (plus the fork banner). As iteration lands real divergence, keep the banner and note the change in the file; when a mirrored doc reaches its intended target state for a phase, flip it to `status: v2-accepted` in the PR that implements it.
