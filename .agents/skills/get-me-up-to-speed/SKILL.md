---
name: get-me-up-to-speed
description: Summarize current Watchtower work as done, in progress, and next. Use when the operator says “get me up to speed”, “gmuts”, “what is the current status?”, “where are we?”, or asks what is happening and what comes next.
---

# Get me up to speed

Build a concise status update from current durable evidence, not conversational memory.

1. Reconcile notifications and inspect the relevant task status and latest handoffs. Re-prime the Watchtower attention ledger on a fresh or resumed session.
2. Group the answer into **Done**, **In progress**, and **Next**. Include project/workset identity and exact branch or head when it matters.
3. Treat a `done` handoff as reported done, not accepted or landed. Treat `waiting` as reported activity whose runtime is unverified unless current runtime evidence confirms it.
4. Under **Next**, name the immediate pipeline route: follow-up, review/test, no-mistakes, integration, PR/CI, merge decision, operator input, or no queued action.
5. Mention blockers, stale evidence, and exact operator decisions needed. Do not infer progress, priority, acceptance, or runtime liveness from silence or terminal state.

For a fleet-wide durable summary, reuse `watchtower-progress-report`. For a focused request, prefer the smallest relevant task/workset evidence and keep the response brief.
