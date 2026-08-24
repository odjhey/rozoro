# ADR-0001: One primary watchtower; operator owns priority

review: approved
date: 2026-08-22

## Context

Rozoro is intended to coordinate a fleet large enough that several crews may report at nearly the same time. The operational temptation is to solve attention pressure by spawning multiple coordinating watchtowers or by letting the system infer a priority queue from technical states.

The target operating model instead needs one place where the operator can see the whole fleet, ask what needs attention, and decide what matters first.

## Options

1. **One primary watchtower with explicit operator priority.** Improve durable attention bookkeeping and presentation so one coordinator remains viable around 10–12+ concurrent tasks.
2. **Multiple watchtowers by default.** Partition the fleet early and accept routing/ownership complexity between coordinators.
3. **System-assigned priority.** Convert states such as `failed`, `blocked`, or `completed` into an automatic work order.

## Choice

Use **one primary watchtower by default**. Preserve technical severity as factual metadata, but keep business priority and final acceptance with the **operator**.

The watchtower may group and summarize facts, propose an order, and execute an operator-selected order. It must not silently convert technical severity into business priority.

Multiple watchtowers remain a future scaling option, not the first response to attention bookkeeping pressure.

## Consequences

- Rozoro must make per-task attribution and partial handling cheap enough for one coordinator to stay useful under bursty concurrency.
- Watchtower state cannot rely only on conversational memory.
- `failed`/`blocked` may be surfaced prominently without becoming an unconditional priority rule.
- Future multi-watchtower routing should preserve task/attention identity rather than inventing a different model.
- The operator remains the final authority on what to inspect first and whether a task result is accepted.
