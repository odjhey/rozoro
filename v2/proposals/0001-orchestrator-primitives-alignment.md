---
name: v2_proposal_0001_orchestrator_primitives
description: "Alignment of the external research team's orchestrator primitive/seam catalogue against the v2 charter and mirror: convergences, gaps on both sides, divergence verdicts, and proposals P1–P14."
type: proposal
tags: [v2, proposal, research, primitives]
status: proposed
generated: "Claude Fable 5, 2026-08-28"
created_at: 2026-08-28T00:00:00+08:00
---

# Proposal 0001 — Orchestrator primitives alignment

Input: the research team's primitive set for "an orchestrator product intended to deliver work" (§1–§38, Goal→Lesson primitives, node states, 12 seams, minimal protocol). Compared against the [v2 charter](../charter.md), the [v2 mirror](../README.md), and the live v1 evidence base ([rewrite seams](../rewrite-seams.md)).

**Headline:** the two models are ~70% convergent, and most of the research catalogue's "make these explicit" list is *exactly* the list our rewrite-seams doc flagged as prose-only concepts (worksets, attempts/budgets, evidence-binds-to-head, integrator role). The real divergence is a single axis — **where planning/scheduling/judgment lives** — plus a set of hard-won layers the research model omits entirely (hosting/liveness, injection boundary, operator authority, conservative evidence). The strongest observation in their favor: **Rozoro's own founding principle ("fleet state must not live in conversational memory") is currently violated by the plan itself** — the work graph today exists only in the watchtower's context window. The research model completes our principle; it doesn't contradict it.

## 1. Alignment map

| Research primitive | v2 today | Verdict |
|---|---|---|
| Goal | Operator intent / brief body (implicit) | **Gap** — partial; see P1 |
| Contract (machine-checkable completion) | Assurance map + external gate (prose, ADR-0008/0009); handoff `verdict` is a claim, not proof | **Gap** — P3 covers the evidence half; full auto-acceptance is deliberately declined (P12) |
| Workset | Prose-only (missions); flagged in rewrite-seams | **Adopt** — P1 |
| WorkItem | **Task** (identity, brief, handoff, session link) — richer on identity/resume, poorer on inputs/outputs/dependencies | **Adapt** — keep `Task`, add graph fields; P1/P14 |
| Dependency / WorkGraph / typed edges / GraphPatch | Nothing — the graph lives in the watchtower's head | **Adopt** — P1, the largest structural change |
| Attempt (first-class, durable) | Turns + derived lineage view + prose budgets | **Adopt** — P2 |
| Loop (bounded, progress-measured) | attempt-budget skill (prose arithmetic) | **Adopt** as data consumed by the skill — P2 |
| Artifact (typed, versioned, hashed) | Free-text `artifacts:` field; `heads:` line (charter D3) | **Adopt** — P3 |
| Evidence (typed, binds to artifact version) | delivery-evidence skill + changed-head reconciliation (prose) — the *insight* is identical ("evidence must identify which head it validates") | **Adopt** — P3 |
| Gate / Evaluator separation | no-mistakes as external gate (ADR-0008); evaluator-facts vs mission-routing split exists in prose | **Adapt** — P3/P4; gate stays external, verdicts become typed records |
| Node states (`produced ≠ completed`) | Same insight, stronger: `done ≠ accepted`, report ≠ runtime, availability ⊥ verdict, frozen tuple matrix | **Aligned** — merge vocabularies; P14 |
| Failure taxonomy | 9-status routing set (mission-owned, test-pinned) + protocol `actionable_reason` | **Adapt** — P4: core failure classes *under* mission routing statuses |
| Executor via capability | Harness adapters + "capability descriptors are data" (already guideline #3 in [ports-and-adapters](../ports-and-adapters.md)) + machine.md (prose) | **Adopt** the schema — P5 |
| Scheduler component | Watchtower judgment via skills (crew-model-selection, quick-crew-routing) per ADR-0012 | **Adapt** — P10: watchtower *is* the scheduler, behind their seam |
| Claim / lease | Home lock + tracked-task refusal (a crude lease); ADR-0001 = one primary watchtower | **Decline for now** — P9 |
| Events (work-level) | Protocol v1 events are *hosting-level* only (session/turn/background) | **Adopt** work-level events — P6 |
| Commands vs events split | Already ours ([core-and-commands](../core-and-commands.md)) | **Aligned** |
| Decision record | Attention ledger (handling log) + dispatcher attribution + ADRs — no alternatives/rationale schema | **Adapt** — P7 |
| Lesson | Nothing durable | **Adopt** — P8 |
| Budget (tokens/cost/wall time) | Attempt counts only, in prose | **Adopt** fields on Attempt/Loop — P2 |
| TerminalState | Task verdicts + operator acceptance (no auto-terminal) | **Adapt** — terminal states exist, but `success` requires operator acceptance; P12 |
| Policy objects (executable) | Missions/policies as LLM-read prose (ADR-0005/0013) | **Decline as executable code**; adopt as *typed inputs* where P2/P4/P5 create schemas |
| Control vs data plane | Already ours, twice over (send/control split; artifacts stay in repo; wake is content-free) | **Aligned** |
| StateStore seam | EventStore/TaskRecordStore ports | **Aligned** |
| Executor/harness/runtime as separate descriptors | Already recorded separately (harness, model, herdr pane) | **Aligned** — formalize in P5 descriptor |
| Seam 4 (start/status/cancel/message/result by run_id) | TerminalHost + Harness ports ≈ this, plus what they lack: exact resume, interactive send | **Aligned+** |
| Seam 9 (Integrator) | Workset Merger role (prose) | **Adopt** as graph-node kind — P1/P11 |
| Seam 11 (Notification adapters) | Wake delivery: deliberately single, fixed, content-free | **Decline for driver wakes** (injection boundary); open for *operator* channels later — P12 |
| §33 minimal protocol | Command catalogue | **Adopt** — fold in; P13 |
| §34 freeze schemas early | Our contracts-first method | **Aligned** |

## 2. Gaps in *their* model (what v2 must keep that the research catalogue omits)

The research model assumes executors are stateless `run_id` jobs. Rozoro's crews are **stateful, resumable, interactive conversations**. Everything below is load-bearing, evidence-backed v1 machinery with no counterpart in the catalogue:

1. **Hosting/liveness layer** — host bindings, panes, exact resume, availability derivation, quiescence, the live gate. Their `run.status` has no notion of "safe to interrupt."
2. **The injection boundary** — their notification seam routes typed events to channels; ours proves the *only* string that may enter a resident conversation is a fixed constant. Non-negotiable.
3. **Conservative evidence discipline** — `unknown` over inference, certified background axes, frozen report tuples, sequence-gap de-certification. Their model trusts evaluator outputs; ours also distrusts *absence*.
4. **Operator authority** — acceptance, priority, human gates, `/afk` merge authority. Their `TerminalState: success` has no human in it.
5. **Registration/driver identity/authority** — who may be woken, validated against live evidence, attributable by policy digest.
6. **Durability orderings and the security posture** — spool→send, commit→ack, no-follow/owner-private discipline, the same-UID threat fence.
7. **Attempt ≠ fresh run** — their Attempt has no `native_session`/`turn` linkage; ours must, because retrying *inside* a conversation (send follow-up) and retrying *fresh* (restart) are different moves with different budgets (v1 already distinguishes them in prose).

## 3. The one real divergence, and the resolution

**Research:** a durable engine owns graph, scheduling, and recovery; planner/evaluator are pluggable components.
**Rozoro (ADR-0001/0005/0012):** an LLM watchtower owns planning, scheduling, and routing judgment, steered by prose policy; the core stays small.

Proposed resolution — *adopt their seams, keep our implementation*:

> The work graph, attempts, evidence, and decisions become **durable core state** (their primitives). The watchtower remains the **planner, scheduler, and replanner implementation** behind their seams (Planner→GraphPatch, Graph→ready-query, Failure→Replanner), steered by missions exactly as today. A deterministic scheduler or non-LLM planner can be slotted in later without a rewrite — which is precisely the researchers' own argument for the seams.

This keeps ADR-0005 (workflow policy above the core) intact: the core stores and validates the graph; it never decides what the graph should be. It also *finally* satisfies "no conversational memory for fleet state" for plans, not just tasks.

## 4. Proposals

Each has a disposition; accepted ones become decision-log entries (D5+) and mirror edits.

| # | Proposal | Disposition | Lands in |
|---|---|---|---|
| **P1** | New bounded context **Work Graph**: `Workset` (goal, policy ref, budget, terminal state), `Task` gains graph membership, typed edges (start with `requires`, `must_verify_before`, `fallback_to`, `invalidates`; add others on demand), `GraphPatch` with lineage as the *only* mutation, integrator/merge nodes as first-class node kinds. Amends charter **D3** (worksets leave prose). | **Adopt** | new `bounded-contexts/work-graph.md` + `contracts/work-graph.md` in the mirror; command catalogue (`workset.create/get`, `graph.patch`, `graph.ready`) |
| **P2** | First-class **Attempt** records: executor descriptor (model/harness/runtime), `native_session` + turn range, `parent_attempt`, `kind ∈ {fresh, follow-up, restart}`, input snapshot ref, budget fields (attempts/tokens/cost/wall). **Loop** as a typed record (progress measure, stop rule, escalation). The attempt-budget skill switches from deriving counters out of history prose to reading/writing these records. | **Adopt** | `contracts/attempts.md`; amends attempt-budget skill contract |
| **P3** | Typed **ArtifactRef** (kind, location, version/content hash, producer attempt) and **Evidence** (typed, `subject_artifact@version`, method, result, producer). This formalizes v1's changed-head reconciliation and the `heads:` line (charter D3) instead of inventing a parallel scheme: `heads:` becomes sugar over evidence records bound to exact SHAs. Gate verdicts become records consuming evidence refs. | **Adopt** | `contracts/artifacts-evidence.md`; extends `contracts/handoff.md` |
| **P4** | **Failure classes** in the core (`contract, execution, environment, dependency, verification, integration, resource, timeout, no-progress, conflict, unknown`) as Attempt fields, *underneath* the mission-owned 9-status routing set — statuses stay routing policy (test-pinned prose), classes become facts routing can key on. Include the mapping table. | **Adopt** | `contracts/attempts.md`; note in `contracts/policy-composition.md` |
| **P5** | **Capability/ExecutorDescriptor schema**: promote adapter capability descriptors (already guideline #3) + `config/machine.md` facts into typed records (`capabilities[]`, cost class, concurrency, trust level, health). Scheduling *judgment* stays with the watchtower skills; the data they judge over becomes validated. | **Adopt** | `contracts/harness-adapters.md` (descriptor section), `ports-and-adapters.md` |
| **P6** | **Work-level events** (`WorkItemReady`, `AttemptStarted`, `ArtifactRecorded`, `EvidenceRecorded`, `GatePassed/Failed`, `GraphChanged`, `WorksetCompleted`, `EscalationRequested`) added beside — never replacing — protocol v1 hosting events. Same closed-schema discipline. Driver wakes stay content-free; work events feed projections, lineage, and future operator channels. | **Adopt** | `contracts/event-protocol.md` (new section) |
| **P7** | **Decision records**: extend the attention ledger item (or a sibling record) with `alternatives[]`, `selected`, `rationale`, `evidence_refs[]` for genuine choice points (executor selection, retry-vs-replan, merge order, accept-despite-warning). | **Adapt** (extend, don't replace) | `contracts/attention-ledger.md` |
| **P8** | **Lesson** as a dated-artifact category (`pattern, applicability, evidence, confidence, recommendation`), reusing the existing immutable-artifact discipline; feeds the level-4 meta loop. | **Adopt** | `contracts/dated-artifacts.md` |
| **P9** | **Claims/leases**: decline for phase 1 — ADR-0001 (one primary watchtower) makes tracked-task refusal a sufficient lease. Record the seam so multi-watchtower work adds `claim/renew/expire/steal` without redesign. | **Decline for now** | note in `contracts/work-graph.md` |
| **P10** | **Scheduler**: no scheduler component. The core answers `graph.ready` (mechanical: dependencies + states + budgets); the watchtower answers "where should it run" (judgment, ADR-0012 precedence). The seam is preserved; the implementation is the LLM. | **Adapt** | `bounded-contexts/work-graph.md` boundary rule |
| **P11** | **Planner/Replanner crews emit GraphPatch data, not prose plans.** A planning handoff carries (or references) a machine-valid patch; the watchtower applies it via `graph.patch`. Replans consume structured failure + evidence and return patches with lineage. This is the research seams 1/2/8 mapped onto our role model. | **Adopt** | mission/dispatch templates (phase 2+), `contracts/work-graph.md` |
| **P12** | **Keep our deviations, explicitly**: operator acceptance gates `success` (their TerminalState is subordinate to it); the driver wake stays fixed/content-free (their notification adapters apply only to *operator-facing* channels, later); the hosting/liveness/evidence/security layers (§2 above) carry over unweakened. | **Keep ours** | charter ground rules (already) + this record |
| **P13** | Fold their §33 minimal protocol into the command catalogue: adds `workset.create/get`, `graph.patch/ready`, `artifact.record`, `evidence.record`, `gate.verdict.record`, `decision.record`, `attempt.*`. `run.*` maps onto existing session commands. | **Adopt** | `core-and-commands.md` |
| **P14** | **Vocabulary reconciliation** in the mirror's ubiquitous language: keep `Task` (≈ their WorkItem), `Crew` (≈ executor instance); adopt `Workset`, `Attempt`, `Evidence`, `Gate verdict`, `GraphPatch`, `Capability`, `Lesson`, `Failure class`; record the mapping so both teams read each other. | **Adopt** | `ubiquitous-language.md` (mirror) |

## 5. Phasing impact

- **Phase 1 (core)** grows by the Work Graph + Attempt + Artifact/Evidence domain model and their commands — all pure-core, fake-backed, no new integrations; this is where the primitives are cheapest to get right and matches the charter's core-first rule.
- The **behavioural suite** gains the graph/attempt/evidence promises; the **technical** list gains graph-patch lineage integrity and evidence-binds-to-version.
- **Phase 2+** unchanged in shape; P11 (planner crews emitting patches) is the first mission-template change and waits for phase 2.
- Charter **D3** is amended by P1–P3 (worksets, budgets, evidence leave prose); **D4** unchanged.

## 6. What we explicitly do not adopt

- An autonomous acceptance path (`Contract` auto-completing a Workset) — operator acceptance remains terminal authority.
- Executable policy objects replacing missions — policy stays LLM-read prose with hash attribution (ADR-0005/0013); what changes is that the *facts* policy reasons over become typed.
- A standalone scheduler/planner component in phase 1 — seams yes, components no.
- Leases/multi-writer orchestration — deferred with the seam recorded.
- Routing all notifications through channel adapters — the driver wake's injection boundary is not a notification feature; it stays as is.
