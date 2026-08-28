---
name: get-me-up-to-speed
description: Give a comprehensive, operator-first conversational Watchtower status report from durable evidence. Use when the operator says “get me up to speed”, “gmuts”, “where are we?”, “what is the current status?”, or “what comes next?”. Do not use for requests to generate, save, or persist a durable fleet progress artifact.
---

# Get me up to speed

Explain the useful human picture, not the implementation log. Build the report from current durable evidence rather than conversational memory.

## Reconcile before reporting

1. Reconcile notifications and inspect the relevant task status, latest handoffs, delivery evidence, and open attention items. Re-prime the Watchtower attention ledger on a fresh or resumed session.
2. Prefer the smallest evidence set that answers the question, but include every project, material operator decision, blocker, and route relevant to the requested scope. Do not omit a required human action merely to keep the update brief.
3. Separate these evidence levels:
   - Call a capability **landed** only when current integration, publication, or target-branch evidence establishes that outcome.
   - A `done` handoff means a crew **reported its work complete**. It is not acceptance, verification, integration, or landing evidence by itself.
   - A `waiting` handoff means **reported waiting; live execution is unverified**. Never turn it, terminal state, silence, or elapsed time into a claim that work is running.
   - Missing, stale, conflicting, or malformed evidence stays unknown and is described as such. Do not infer progress, priority, acceptance, or runtime liveness.
4. Translate evidence into plain-English product or operational behavior. Say what a capability lets the operator or user do and why it matters. Avoid code-oriented summaries, hashes, branch names, task/session IDs, filenames, and internal role labels unless an exact identity is materially needed to act, distinguish conflicting evidence, or verify a delivery claim.

## Required report shape

Use these top-level headings in this exact order: `## Operator action`, `## What landed`, `## What is happening now`, and `## What happens next`. The report may be concise for a small scope or comprehensive for a fleet-wide question; it is not restricted to three terse bullets.

### Operator action

When any human decision or action is pending, this is the first section and contains one clearly labeled action item per decision. Never bury an input request under project status.

For each action item include:

- **Readiness —** say **Ready now** or **Not ready yet**. If it is not ready, do not ask the operator to act; name the missing prerequisite, its owner or next route when known, and the evidence that will make the decision ready.
- **Decision and why it matters —** state the decision in nontechnical terms and the user, delivery, cost, risk, or priority consequence.
- **Exact steps —** give a short numbered procedure, including where to look or what to provide. Do not write only “please review” or “input needed.”
- **Choices —** list the evidenced options and practical tradeoffs. Identify a recommendation only when evidence supports one; otherwise say that no recommendation is established.
- **Acceptance evidence —** state exactly what result, demonstration, check, or visible behavior the operator should use to accept the choice. Distinguish evidence already available from evidence still to be produced.
- **What remains blocked —** name the work or outcome that cannot proceed without the decision. If nothing is blocked yet because the item is not ready, say so and identify what would eventually wait on it.

If no operator action is needed anywhere in scope, begin with `## Operator action` and say **None — the next routes are automatic** (or conservatively explain why no route is queued). Do not manufacture a decision to fill the section.

### What landed

Group verified landed outcomes by human-recognizable project or product area. Describe capabilities and their value before delivery mechanics. Include exact delivery identity only when needed to locate or disambiguate the outcome.

Do not put merely reported-complete work here. If no landing is verified, say so plainly and place the reported state under **What is happening now**.

### What is happening now

Describe each material active, reported-complete-but-not-landed, blocked, failed, or uncertain thread in plain English. State the conservative evidence qualifier inline, especially when runtime is unverified or evidence is stale. Explain the practical outcome each thread is trying to reach and any impact on the operator.

### What happens next

Give one ordered, numbered route across the relevant work, not an unordered task inventory. Name the next meaningful stages—for example follow-up, independent review/test, no-mistakes validation, integration, PR/CI, merge decision, or external unblock—and the outcome each stage enables.

For every step say **Operator: not needed**, **Operator: needed now**, or **Operator: needed later**, and cross-reference any action item above. Clearly distinguish an automatic next route from a step that has no owner or is not yet queued. End with the expected operator intervention point, or explicitly say that no intervention is currently expected.

## Conversational-only boundary

Return the report directly in the conversation. Do not create or update a progress-report artifact, report file, or other persisted summary. An explicit request to generate, create, save, or persist a durable fleet-wide report belongs to `watchtower-progress-report` instead. Reading task evidence and maintaining the attention ledger under its own skill contract are not progress-report generation.
