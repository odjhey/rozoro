---
name: contract_policy_composition
description: "Presets, missions, and policy composition: crew presets, watchtower presets, the mechanics-core + exactly-one-mission rule, policy digests, and the precedence chain."
type: contract
tags: [architecture, contracts, policy, watchtower]
status: current
generated: "Claude Fable 5, 2026-08-28"
created_at: 2026-08-28T00:00:00+08:00
---

# Presets and policy composition

Part of the [contracts index](./README.md). Presets describe **HOW** an agent boots, never **WHAT** its task is. Policy describes what a watchtower's fleet is for, composed at launch and attributable by hash afterward.

## Crew presets

`$ROZORO_HOME/crew/<name>.json`: `{harness, model, permission_mode, effort, fast, rules}`.

- `rules` are crew-behavioral text, distinct from repository rules the agent loads from its `--cwd`.
- Malformed known fields are rejected; **unknown keys are tolerated** (forward compatibility with a newer Rozoro).
- A virtual `default` exists only when no `default.json` is present.
- `fast` is currently hard-pinned to one codex model — the only model name in executable code (a stage-1 placeholder).

## Watchtower presets

`$ROZORO_HOME/watchtower-presets/<name>.json`, harness restricted to `claude|pi`:

```json
{ "schema": 1, "version": 3, "harness": "pi", "model": "…", "effort": "low|medium|high|xhigh|max",
  "permission_mode": "…", "mission": "eager-delivery", "notes": "…" }
```

- The file must be 0600, owned, `st_nlink == 1`, in an owned 0700 directory; it is read once through no-follow descriptors and **hashed as the same bytes that were parsed** (`preset sha256`).
- There is deliberately **no virtual default** — no preset preserves legacy launch behavior exactly.
- Preset names are metadata (attribution), never delivery identity; driver ids stay transport-derived (ADR-0011).

## Mission composition (ADR-0013)

Every Pi watchtower's policy = **mechanics core + exactly one mission**, in that order:

- Core: `templates/watchtower.md` (checkout-owned). It defines mechanics — dispatch loop, edge-triggered monitoring, terminology — and **never overrides a mission's role boundaries**. It names no models.
- Mission: resolved by name from exactly one of `templates/missions/<name>.md` (source `shipped`) or `$ROZORO_HOME/watchtower-missions/<name>.md` (source `operator`). **Both present → ambiguous, fail. Neither → missing, fail.** Default mission: `delivery`.
- Text validation: strict UTF-8, non-empty, no BOM, no C0 (except tab/newline/CR), no C1 controls.
- **Policy digest**: `policy_sha256 = sha256(core_bytes ‖ mission_bytes)` — recorded in the registration, re-derivable from a policy snapshot (`composed_policy_sha256`). This is how you tell, after the fact, which policy a driver actually ran under.
- The launcher re-resolves policy immediately before `exec` and dies if it changed (TOCTOU guard). Operator `--append-system-prompt` is rejected: policy prompt options are launcher-owned.
- The Pi launcher's argv shape is itself a versioned external contract: the policy-snapshot skill pins the launcher's SHA-256 and re-parses its `exec` line to prove exactly `[core, mission]` are appended.

**Claude watchtowers are policy-blind**: preset-only launch, no mission, no system-prompt injection — recorded as `unverified-no-consumed-policy-args-array` in policy snapshots. This asymmetry is deliberate today and a rewrite seam.

## Shipped missions

- **`delivery`** — full role separation: the closed 9-status routing taxonomy (`DONE`, `NEEDS_IMPLEMENTATION`, `NEEDS_TESTS`, `NEEDS_REVIEW`, `NEEDS_DECISION`, `NEEDS_REPLAN`, `NEEDS_INFRA_REPAIR`, `NEEDS_GATE_REPAIR`, `BLOCKED_EXTERNAL`), worksets and Workset Mergers, attempt/replan/repair budgets, ad-hoc specialists under ADR-0014 declarations, `/afk` merge-authority rules.
- **`eager-delivery`** — the one-hop counter-mission for non-mission-critical products: closed 3-role list (Ship Crew, Delivery Planner-Merger, Contract Keeper), a deliberately "dumb" routing watchtower, merge-early/repair-forward doctrine, success metric ≈1 driver hop per deliverable.

Two contradictory doctrines coexist safely **because** composition is explicit and attributable.

## Policy-as-code enforcement

Policy prose is under referential-integrity tests (`policy-contracts`): the 9-status set must be set-equal across the mission, the dispatch template, and the operator runbook; only `NEEDS_REPLAN` may be documented as charging `replan_count`; the repair-metadata field names and the literal caps `repair_limit: 3` / `infra_repair_count + gate_repair_count <= 3` must appear in all four authorities; the precedence chain must appear **in order**:

```text
operator > repository > durable policy > machine availability > compatible preset realization
```

Editing any of these files without running the suite will break the build — the policy layer's prose is load-bearing code.

## What has no code representation

Worksets, attempt/replan/repair counters, lineage ids (`repair_lineage_id`, `implementation_lineage_id`), and role rosters are **prose-only**: defined in missions/skills/runbooks, derived from durable history by the watchtower, with no schema, store, or validator in Rozoro. This is a deliberate boundary (ADR-0005: workflow policy stays above the core) and a candidate for contract work in the rewrite.
