---
name: get-me-up-to-speed
description: Give a lightweight conversational Watchtower summary as Done, Current, and Next. Use when the operator says “get me up to speed”, “gmuts”, “where are we?”, “what is the current status?”, or “what comes next?”. Do not use for requests to generate, save, or persist a durable fleet progress artifact.
---

# Get me up to speed

Build a concise status update from current durable evidence, not conversational memory.

1. Reconcile notifications and inspect the relevant task status and latest handoffs. Re-prime the Watchtower attention ledger on a fresh or resumed session.
2. Group the answer into **Done**, **Current**, and **Next**. Include project/workset identity and exact branch or head when it matters.
3. Under **Current**, report only conservatively evidenced present state. A `waiting` handoff is reported waiting with runtime liveness unverified; never turn it, silence, or terminal state into a claim that work is running.
4. Treat a `done` handoff as reported done, not accepted or landed. Under **Next**, name the immediate pipeline route: follow-up, review/test, no-mistakes, integration, PR/CI, merge decision, operator input, or no queued action.
5. Mention blockers, stale evidence, and exact operator decisions needed. Do not infer progress, priority, acceptance, or runtime liveness.

This skill is for a brief conversational update. Route an explicit request to generate, create, save, or persist a durable fleet-wide progress artifact to `watchtower-progress-report`. For a focused update, prefer the smallest relevant task/workset evidence.
