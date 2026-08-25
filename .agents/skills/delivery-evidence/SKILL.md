---
name: delivery-evidence
description: >-
  Audit whether review, test, CI, publication, and delivery claims apply to the
  exact current software head. This is a Watchtower-owned skill used to judge
  crew reports, decide whether work can continue or close, and record bounded
  unattended decisions.
metadata:
  execution-owner: watchtower
  watchtower-action: invoke-directly
  derived-from:
    - docs/runbooks/human-gates-and-evidence.md
    - templates/watchtower.md
---

# Delivery evidence

Use exact-head evidence to support unattended Watchtower decisions. Do not turn
ordinary delivery into a human-approval queue.

This skill is executed by the **Watchtower**. Crew members produce review, test,
CI, no-mistakes, and implementation evidence; the Watchtower reconciles those
reports here and decides what should run next. Do not pass this skill to a coder
as a substitute for independent verification.

Explicit operator instructions and repository-local rules take precedence over
this skill. Existing branch protection, provider authorization, and destructive
operation limits still apply.

## Build the decision record

For each meaningful delivery decision, record three things:

1. **Prerequisites** — earlier merges, environments, permissions, policy choices,
   or other conditions that must already hold.
2. **Machine evidence** — exact commit/tree, tests, CI run and conclusion,
   independent review/test attestations, and reproducible artifacts.
3. **Decision** — what the Watchtower decided, why the evidence supports it, and
   any residual risk or follow-up issue.

Green CI or an agent verdict is evidence, not proof by itself. The Watchtower
should combine the available evidence and make the bounded decision it is
already authorized to make.

## Exact-head audit

Before a publish, merge, release, or other delivery action, compare every
identity required by repository policy. Common identities include:

- independently reviewed head;
- independently tested head;
- final pipeline or publication head;
- pull-request or branch head;
- required CI head.

If a relevant head changes, mark stale attestations as stale and repeat the
assurance required for the new head. After merge, bind post-merge checks to the
actual merge commit when policy requires them.

## Unattended decision policy

Default to continuing when the decision is reversible, within declared scope,
and supported by current evidence and repository policy. Record the decision in
the durable task handoff or other designated decision log.

Do not stop merely because no human is present. When the Watchtower encounters a
choice outside its authority or evidence is insufficient for a safe mutation:

- preserve the current safe state;
- file a GitHub issue describing the decision or missing authority;
- include exact heads, evidence, options considered, recommendation, and the
  smallest action needed later;
- link that issue from the task handoff/decision record; and
- continue with other independent work where possible.

Do not silently broaden scope, bypass branch protection, expose secrets, or make
destructive/irreversible changes that repository policy does not already permit.

## Sensitive or sequential work

For secret-bearing, live-provider, deployment, or irreversible work, require the
explicit prerequisites and authorization already defined by repository/operator
policy. If those prerequisites are absent, create an actionable issue instead of
inventing a new approval mechanism.

For dependent changes, preserve declared order and revalidate each current head.
Documentation is never permission to bypass branch protection.

## Exception record

When normal policy cannot resolve a case, record an exception as a bounded
engineering decision rather than a generic human gate. Capture:

- one target and one proposed action;
- exact immutable preconditions;
- read-only checks available before mutation;
- why normal supported paths are insufficient;
- the safest recommended next action;
- stop conditions if identities change; and
- assurance that must be rerun afterward.

If the action is not currently authorized, file this record as a GitHub issue and
leave the state safe.

## Report

Return:

- decision/status;
- exact identities compared;
- prerequisites satisfied or missing;
- machine evidence and where it came from;
- stale or mismatched evidence;
- decision taken and rationale;
- follow-up issue, if one was filed;
- blockers that prevent safe autonomous progress.
