# Human gates and exact-head evidence

Use this runbook where delivery includes decisions that automation cannot own.

## Separate evidence from decisions

For each gate, record three distinct sections:

1. **Prerequisites:** earlier merges, environments, permissions, or policy decisions that must already hold.
2. **Machine evidence:** exact commit/tree, tests, CI run and conclusion, review/test attestations, and reproducible artifacts.
3. **Human decision:** the named choice, authorized decision maker, acceptable evidence, and recorded approval.

Agent approval and green CI do not satisfy a human gate. Absence of an objection is not approval. Keep separate gates separate even when their evidence overlaps.

## Exact-head chain

Before a publish or merge decision, require equality among every relevant identity:

- independently reviewed/tested head;
- pipeline final and pushed head;
- pull-request head; and
- required CI head.

If the pipeline or branch changes, invalidate stale attestations and repeat the checks required by repository policy. After merge, bind post-merge CI to the actual merge commit.

## Sensitive and sequential work

Do not start secret-bearing, live-provider, deployment, or irreversible work until its explicit prerequisites and human gate are satisfied. Do not put credentials, secret values, private snapshots, or operator-local audit material in a runbook or PR. Record only the minimum safe evidence that a gate occurred.

For dependent changes, preserve declared order, revalidate each current head, and require protected CI. Never use documentation as permission to bypass branch protection.

## Exception requests

An exception request must be bounded to one target and one action, identify immutable preconditions, distinguish read-only checks from mutations, name the authorized actor, and list hard stop conditions. Drafting such a request does not authorize execution. If any precondition changes, stop and obtain a new decision.
