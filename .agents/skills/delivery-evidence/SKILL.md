---
name: delivery-evidence
description: >-
  Audit whether review, test, CI, publication, and human-gate claims apply to the
  exact current software head. Use when deciding whether a PR, branch, release,
  or deployment has sufficient evidence for an authorized human decision. This
  skill gathers and validates evidence; it does not grant merge or deployment authority.
metadata:
  derived-from: docs/runbooks/human-gates-and-evidence.md
---

# Delivery evidence

Keep machine evidence separate from human authority.

Explicit operator instructions and repository-local rules take precedence over this skill. Never infer approval from silence, green CI, or an agent verdict.

## Build the gate record

For each gate, keep three sections distinct:

1. **Prerequisites** — earlier merges, environments, permissions, policy decisions, or other conditions that must already hold.
2. **Machine evidence** — exact commit/tree, tests, CI run and conclusion, independent review/test attestations, and reproducible artifacts.
3. **Human decision** — the decision required, who is authorized to make it, what evidence is acceptable, and where the approval is recorded.

Agent approval and green CI are evidence, not substitutes for a required human decision. Keep separate gates separate even when they share evidence.

## Exact-head audit

Before a publish, merge, release, or deployment decision, compare every identity required by repository policy. Common identities include:

- independently reviewed head;
- independently tested head;
- final pipeline or publication head;
- pull-request or branch head;
- required CI head.

If a relevant head changes, mark stale attestations as stale and repeat the assurance required for the new head. After merge, bind post-merge checks to the actual merge commit when policy requires them.

## Sensitive or sequential work

Do not start secret-bearing, live-provider, deployment, or irreversible work until its explicit prerequisites and human gate are satisfied. Record the minimum safe evidence that the gate occurred; do not copy credentials, secret values, private snapshots, or operator-local audit material into reports.

For dependent changes, preserve declared order and revalidate each current head. Documentation is never permission to bypass branch protection.

## Exception requests

A request for exceptional authority should be bounded to one target and one action. It should identify immutable preconditions, distinguish read-only checks from mutations, name the authorized actor, and state hard stop conditions. Drafting or documenting an exception does not authorize execution.

## Report

Return:

- gate name and status;
- exact identities compared;
- prerequisites satisfied or missing;
- machine evidence and where it came from;
- stale or mismatched evidence;
- human decision still required, if any;
- hard blockers and stop conditions.

Use conservative language: `evidence complete for human decision` is different from `approved`, `merged`, `released`, or `deployed`.
