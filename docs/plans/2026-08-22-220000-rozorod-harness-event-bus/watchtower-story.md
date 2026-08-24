# Harness event-bus watchtower story and task index

This is the concise navigation record for the accepted event-bus plan. The
architecture and contracts remain in [`plan.md`](plan.md); release operations
remain in [`../../event-bus-cutover.md`](../../event-bus-cutover.md).

## Chronology

Planning task `rozorod-event-bus-planning--01M0MX7HZN0TNQ2D3WSAEMNRR3`
converted the accepted design into eighteen bounded PRs and gates G0-G5. The
implementation PRs 1-16 landed on `master` in this order:

| PR | Landed SHA | Slice | Coding task | Review task(s) |
|---|---|---|---|---|
| [#47](https://github.com/odjhey/rozoro/pull/47) | `f0e9929` | 1 protocol v1 | `eventbus-01-protocol--01M0MXKWZTHJPYYC14QKG87DXC` | `eventbus-01-protocol-review--01M0MXXRY2HEKPPEQ8G88XHA00`, `eventbus-01-protocol-review-retry--01M0MXZR2JCHCR0VRKM06692ZJ` |
| [#48](https://github.com/odjhey/rozoro/pull/48) | `8a0a776` | 2 reducer | `eventbus-02-reducer--01M0N6W69QSWEPJZQW6T2AN4M7` | G0/stack review history |
| [#49](https://github.com/odjhey/rozoro/pull/49) | `dcd98d0` | 3 SQLite store | `eventbus-03-store--01M0N8X85ZT9STNCPSX4TKG78Y` | `eventbus-03-store-review--01M0N98PRSCNVFCWJWNEAN6ADW` |
| [#51](https://github.com/odjhey/rozoro/pull/51) | `0d500b8` | 4 client/spool | `eventbus-04-client-spool--01M0N8X85ZAEB7GZK5HYME9469` | `eventbus-04-client-review--01M0N9WZ7T5AMDSEGJZYQ9YKWK` |
| [#52](https://github.com/odjhey/rozoro/pull/52) | `f5354e8` | 5 AF_UNIX server | `eventbus-05-server--01M0NZZ5Z74F4J9VR2A3PPVRKS` | `eventbus-05-server-review--01M0P0A5WRRJ86RXCQDB8CQ9VS` |
| [#53](https://github.com/odjhey/rozoro/pull/53) | `158053e` | 6 lifecycle/spool/health | `eventbus-06-lifecycle-spool-health--01M0P7ZV9PE2H7GFMXDGGYGFR3` | G1 review train |
| [#54](https://github.com/odjhey/rozoro/pull/54) | `a0775d7` | 7 task/report projections | `eventbus-07-projections-report--01M0PADJ04FQF2R7Q415WWY25N` | `eventbus-07-projections-review--01M0PAWEZG0M4DM9E09H2Y1DE0` |
| [#55](https://github.com/odjhey/rozoro/pull/55) | `96e10f6` | 8 delivery ledger | `eventbus-08-delivery-ledger--01M0PCJSAHYE54XCHMBJZR9D91` | G2 review train |
| [#57](https://github.com/odjhey/rozoro/pull/57) | `01ea41b` | 9 coalescer/actuators | `eventbus-09-coalescer-actuators--01M0PF2AYN7FJSKG6P64TZH376` | G2 review train |
| [#58](https://github.com/odjhey/rozoro/pull/58) | `8ba4cbd` | 10 CLI compatibility | `eventbus-10-cli-compat--01M0PH7GC5GP237CSSCHSG9PGP` | no-mistakes/review train |
| [#59](https://github.com/odjhey/rozoro/pull/59) | `c2d28e8` | 11 Herdr membership | `eventbus-11-herdr-membership--01M0PWAB2W6B89NZ0GN2JPV6H1` | `eventbus-g2-review--01M0PWRF7WG1BVXRN3D4A91QNG` |
| [#50](https://github.com/odjhey/rozoro/pull/50) | `2aff34c` | 12 Claude capability | `eventbus-12-claude-capability--01M0N8Y6ZKTAX4WQYW947E1680` | `eventbus-12-capability-review--01M0N97EJNWY0282N2393PYA0A` |
| [#61](https://github.com/odjhey/rozoro/pull/61) | `cb4360c` | 13 Claude producer | `eventbus-13-claude-producer--01M0Q2JPB1EM9SW4JS1KHK7XFD` | `eventbus-13-claude-review--01M0Q36TZ2CTWY5FXDPXRRBA5F` |
| [#60](https://github.com/odjhey/rozoro/pull/60) | `9484094` | 14 Pi adapter | `eventbus-14-pi-adapter--01M0Q2JPB1E514JH64YG7S62JV` | `eventbus-14-pi-review--01M0Q3279ZAMPD93FWH7NB4KCK` |
| [#62](https://github.com/odjhey/rozoro/pull/62) | `20e9cb0` | 15 Claude watchtower/G3 | `eventbus-15-claude-watchtower-live--01M0Q5XHHEA7BK6P1KVAPSH3EM` | `eventbus-15-g3-review--01M0Q98KC643AFMA5W9YB47YK9` |
| [#63](https://github.com/odjhey/rozoro/pull/63) | `f9a9a825` | 16 production cutover/G4/G5 | `eventbus-16-cutover-docs--01M0QEYE3390YGWTN713R3SB4Y` | `eventbus-16-release-review--01M0QH6N3Q3X4C7FHJNTDMT09B` |

PR #63 passed final G4/G5 review, squash-merged as `f9a9a825`, and its
post-merge macOS syntax and full container jobs passed. Issue
[#25](https://github.com/odjhey/rozoro/issues/25) was closed: `rozorod` now owns
that resident-monitor scope, so no second monitor will be built.

The long final cycle was investigated independently by
`eventbus-16-fable-investigation--01M0RASRDDBF6R6FDP0MWZK0S1`. Its handoff
reconstructed the timeline and concluded that the elapsed time was legitimate
review, blocker repair, repeated live/process validation, and release gating—not
environmental blockage.

Post-cutover preparation is recorded by
`eventbus-postcutover-upgrade-prep--01M0RD7J4Q26180B4DB54ZMBPT`. It created
`safety/pre-eventbus-cutover-b5966c2`, advanced the root checkout to exact merged
`f9a9a825`, validated the daemon/rollback path in an isolated home, and removed
only proven orphan test daemons. The live control watchtower was deliberately
left untouched. Its pending quiet-window operation is a clean exact-session
restart on the merged checkout, which will switch that same watchtower to daemon
authority and then verify health/reconcile; this is not a new session or PR.

After a stable Pi+Claude soak, the accepted sequence continues with PR 17
(`eventbus/17-codex-adapter`) and PR 18 (`eventbus/18-copilot-adapter`). They are
adapter proofs, not permission to redesign the protocol/store.

## Finding the durable records

For any task ID in the table, inspect the configured home (default
`~/.rozoro`, otherwise `$ROZORO_HOME`):

```sh
home="${ROZORO_HOME:-$HOME/.rozoro}"
id='eventbus-16-cutover-docs--01M0QEYE3390YGWTN713R3SB4Y'
less "$home/tasks/$id/brief.md"       # assignment and constraints
less "$home/tasks/$id/handoff.md"     # append-only turn/review history
jq . "$home/tasks/$id/session.json"   # exact resumable harness session
```

Some early historical handoffs contain malformed or superseded blocks. Do not
rewrite them: later valid append-only blocks are the correction and current
record. Read the full file in order and use the latest valid block while
preserving earlier evidence.
