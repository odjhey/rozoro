---
name: watchtower-attention-ledger
description: Record and re-read the Watchtower's own attention state — which task edges need action, what was already routed, what is deferred — as durable per-item files. Use during reconcile to record or supersede attention items, when a routing/handling decision is made, and on a fresh, compacted, or resumed session to re-prime before acting.
compatibility: Requires Python 3.11+, a Rozoro checkout, and local filesystem access.
metadata:
  artifact-schema: rozoro.watchtower-attention-ledger/v1
---

# Watchtower attention ledger

The Watchtower is a long-lived LLM session. Everything under it is durable — the event log,
projections, generations, task folders, handoffs — but *what the driver decided* ("already
dispatched a reviewer for task A", "deferred D's failure as a duplicate", "mid-triage on C")
lives only in its context window. ADR-0001 warns against relying on that memory; ADR-0004
designs the real fix (a first-class attention/mailbox capability) but it is unbuilt.

This skill is the interim: a driver-private notebook that makes handling state durable as files,
so a fresh, cycled, or compacted session can re-prime from disk. It records **driver decisions
and observations, never system truth.**

## When to use

- **During every reconcile.** `./bin/rozoro reconcile` prints a **delta of the tasks changed
  since the last generation ACK** — unchanged tasks are intentionally absent, carried instead by
  this durable ledger. For each surfaced task edge that needs driver attention, `add` an item (or
  let supersession replace a stale one). Pass `--full` when a complete latest-per-task snapshot
  is needed (e.g. auditing state the ledger does not cover).
- **The moment a routing or handling decision is made.** `update` the item with a note — every
  transition must say why.
- **On session start, after compaction, or after driver resume/cycling.** Run `prime` before
  acting to re-orient from disk instead of from memory — a fresh session's reconcile only shows
  the delta, so the ledger (and `--full` when needed) is how you recover unchanged state.
- **Before a deliberate driver handoff.** Ensure open items carry current notes.

## Run

From this skill directory (all subcommands accept `--home`, default `$ROZORO_HOME` then
`~/.rozoro`):

```bash
# record a surfaced edge (supersedes an existing open/deferred item for the same task+reason)
python3 scripts/ledger.py add --task fix-auth --reason needs-action \
  --summary "Crew asked which macOS matrix entry is authoritative" \
  --priority urgent --generation 41 --source reconcile --snapshot -   # snapshot body on stdin

# record a handling decision
python3 scripts/ledger.py update <id> --note "dispatched Quick Scout to check CI matrix history"
python3 scripts/ledger.py update <id> --note "answered crew via rozoro send" --status handled

# re-orient a fresh/resumed session
python3 scripts/ledger.py prime

# cheap index (frontmatter + title only); full item on demand
python3 scripts/ledger.py list --status open,deferred
python3 scripts/ledger.py show <id>

# integrity + migration feed
python3 scripts/ledger.py doctor
python3 scripts/ledger.py export
```

Items live one markdown file per attention item under
`$ROZORO_HOME/watchtowers/attention/items/` (owner-private 700/600). This is a shared sibling of
the per-incarnation driver dirs precisely so it survives driver cycling. Every mutation takes a
`flock`; reads do not. `list`/`prime` read frontmatter and the title only — the body is fetched
per item with `show` (progressive disclosure).

## Interpretation rules

- **Ledger entries are driver-recorded decisions, not verified facts.** `handled` here is not
  task open-item resolution (`rozoro ack`), not generation ACK, not a handoff verdict, and never
  operator acceptance.
- **Never mark `handled` on the basis of terminal idleness or elapsed time.** Mark it because a
  concrete handling action happened, and say what it was in the note.
- **Malformed files are surfaced, not repaired silently.** `list`, `doctor`, and `prime` report a
  malformed file by name and never count it as open or handled; repair is an explicit,
  operator-visible action. A symlink — including a dangling one — is unsafe, not missing.
- **The ledger is owner-private.** Do not paste crew handoff free-text into snapshots beyond what
  the driver needs to re-orient; link to the task's `handoff.md` instead.
- **Supersession removes stale attention from the active view without deleting history.** A new
  `add` for the same `(task, reason)` marks the prior open/deferred item `superseded` (with
  `superseded_by` and a log line). Use `--no-supersede` to keep both.

## Boundaries

This is an interim capability pending ADR-0004. `rozorod` does not read it; crews never write it;
it assumes one primary Watchtower (ADR-0001). It must not blur generation ACK, task open-item
ACK, and operator acceptance. If the ADR-0004 mailbox ships, `export` is the migration path and
this skill is retired.
