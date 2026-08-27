# ADR-0014: Delivery failure routing and ad-hoc specialists

review: approved
date: 2025-10-24
supersedes: ADR-0009 fixed delivery-role roster and implementation-only repair-accounting boundary

## Context

Delivery needs exclusive per-edge failure routing, bounded infrastructure/gate repair, and narrowly attributable specialists without weakening ADR-0012 model-routing precedence or ADR-0013 mission ownership.

## Options

1. Treat every failure as implementation/replan — charges the wrong lineage.
2. Permit universal or unbounded ad-hoc roles — bypasses mission and role authority.
3. Mission opt-in with bounded repair lineages and authority fences — explicit and auditable.

## Choice

Choose option 3. Delivery classifies each actionable edge with exactly one of `DONE`, `NEEDS_IMPLEMENTATION`, `NEEDS_TESTS`, `NEEDS_REVIEW`, `NEEDS_DECISION`, `NEEDS_REPLAN`, `NEEDS_INFRA_REPAIR`, `NEEDS_GATE_REPAIR`, or `BLOCKED_EXTERNAL`; Watchtower owns classification and routing. Independent edges may coexist and run concurrently when planned.

Each repair incident durably records stable lineage IDs, separate infra/gate counters, limit 3, and cause. Mutating repairs increment one repair counter; diagnosis does not. Counters never reset or charge implementation/replan. Two same-root failures require a checkpoint; attempt 3 requires changed hypothesis/owner; no fourth attempt.

A mission's role list remains closed unless it explicitly opts in. Delivery opts in. Each ad-hoc instance is one declared job with durable attribution, normal ADR-0012 routing and execution-time availability verification, explicit stop/evidence boundary, and no transfer of operator, Watchtower, policy/contract, Planner/Replanner, Coder, Reviewer, Tester, Runner, or Merger authority. Third equivalent creation triggers review; fourth requires graduation or a decision-authority exception and bounded review point.

At repository evolution boundaries, Coder flags and supplies the check, Planner maps it, and No-Mistakes Runner independently verifies meaningful execution before broad judgment fan-out. A functioning check exposing a defect is not gate repair.

## Compatibility

This is policy/report metadata, not a runtime, daemon, protocol, or schema change. Old handoffs are not rewritten; ambiguous history records a known lower bound and requires a checkpoint. ADR-0012 precedence and ADR-0013 composition/mission ownership remain authoritative. This ADR only supersedes ADR-0009's fixed delivery-role roster and implementation-only repair-accounting boundary.

## Consequences

Repair retries and improvised roles are bounded and reconstructable. Every candidate mutation still invalidates exact-head evidence and re-enters the gate. Missions other than delivery gain no ad-hoc authority by implication.
