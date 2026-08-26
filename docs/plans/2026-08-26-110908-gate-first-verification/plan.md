# Gate-first verification: narrow review/test crews, wire the mechanical gate

Tracking: [#114](https://github.com/odjhey/rozoro/issues/114) (initiative) ·
[#117](https://github.com/odjhey/rozoro/issues/117) (v1.57.0 source-traced
refinements + authoritative config values)

## Why

Measured across the fleet (Aug 23–26 event data): a deliverable pays ~6 driver
round trips (code → review → test → repair → rereview → retest → gate → merge)
at ~12+ min per hop (median reaction gap 7.5 min + turn time). The push
pipeline itself is instant — the cost is hop count. The v0.0.1-era backup
comparison showed the "fast" greenfield period had ~1 driver hop per
deliverable: chain depth, not per-hop speed, dominates delivery velocity.

Direction: the crew/gate boundary is **codified vs novel judgment**, and it
moves. The gate carries everything expressible as a rule, command, or test;
crews work the frontier; repeated finding classes ratchet into gate config
(`review.path_instructions`), suite tests, or lint rules.

Source-traced support (no-mistakes v1.57.0 @ 0fcbbff extraction): gate
rereviews are always cold (fresh context preserved by construction); Push is
deterministic and requires a durable Review-approved ancestry binding.

## Work items

| # | Item | Status | Document |
|---|---|---|---|
| 1 | Gate-first ordering + narrowed roles in dispatch guidelines | **Delivered — PR [#116](https://github.com/odjhey/rozoro/pull/116) (merged)** | [brief-1](./brief-1-gate-first-dispatch-guidelines.md) |
| 2 | Clear the ruff (44) + shellcheck (30) baseline | Pending dispatch | [brief-2](./brief-2-lint-baseline-cleanup.md) |
| 3 | Wire `commands.lint` + `review.path_instructions` + `document.instructions` into `.no-mistakes.yaml` | Blocked on item 2 | [plan-3](./plan-3-no-mistakes-gate-config.md) |

Authoritative config values for item 3 (8 path_instructions entries,
document.instructions, proposed AGENTS.md snippet):
https://github.com/odjhey/rozoro/issues/117#issuecomment-5420016890

## Measurement (definition of success)

In `./bin/rozoro report` over the following days:

- `rereview`/`retest` dispatches per deliverable → drops
- reviewer/tester turns per deliverable → toward 1 each
- reaction-gap median may stay flat — the win is fewer hops, not faster hops
- crew findings trend toward novel classes; a repeat class = missed ratchet

## Provenance

Plans authored 2026-08-26 from fleet metrics (`rozoro report`, PR #112),
delivery-ledger latency measurements, the v0.0.1 backup era comparison, and the
no-mistakes v1.57.0 invocation-contract extraction
(`/Users/odz/projs/no-mistakes-lessons/versions/v1.57.0-0fcbbff/`, local).
Item 1 was dispatched from the brief here and delivered as PR #116, which
extended it with final-head vs submitted-head provenance rules and the
red-candidate judgment exception.
