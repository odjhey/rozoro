> **STATUS: blocked on brief-2** — item 3 of [#114](https://github.com/odjhey/rozoro/issues/114); authoritative config values in [#117](https://github.com/odjhey/rozoro/issues/117#issuecomment-5420016890).

# Plan: wire lint + repo-specific review rules into `.no-mistakes.yaml` (SEQUENCED — after lint-baseline cleanup lands)

**Repo:** /Users/odz/proj/rozoro · **Blocked on:** `brief-lint-baseline-cleanup.md` PR merged
(a wired lint gate against a dirty baseline would fail every pipeline run).

## Context

Agreed direction: mechanical checks live in the no-mistakes gate; review/test crews
do judgment only (see `brief-gate-first-dispatch-guidelines.md`). The repo's
`.no-mistakes.yaml` already runs `commands.test: './tests/run.sh'` and absorbs
mechanical review findings with `auto_fix.review: 1` ("32 of 33 pipeline fixes came
from review"). `commands.lint` was deliberately left unset until the baseline was
clean. Once the cleanup PR lands, wire it.

## Change (single file: `.no-mistakes.yaml` — both keys are trusted-default-branch-only, so one PR covers both)

**1. Lint gate.** Add under `commands:`:

```yaml
commands:
  test: './tests/run.sh'
  lint: 'uvx ruff check . && find bin hooks tests -name "*.sh" -print0 | xargs -0 shellcheck -x'
```

Verified against installed v1.57.0 docs AND the source-traced extraction at
`/Users/odz/projs/no-mistakes-lessons/versions/v1.57.0-0fcbbff/` (pinned to this
exact binary): `commands.lint` is a plain shell string run via `sh -c` — the
form above works as-is. Source-proven mechanics the implementer should know:
- Pipeline order is Intent → Rebase → Review → Test → Document → Lint → Push →
  PR → CI. With no lint command, Document runs "combined housekeeping" and Lint
  consumes its stash; configuring `commands.lint` switches Document to
  documentation-only mode and Lint runs the command with its own repair path
  (`steps/document.go:134`, `steps/lint.go:144` per the extraction). Expect the
  document step's behavior to visibly change in the first run after wiring.
- `auto_fix.lint: 3` is already the global default (gate self-fixes lint findings).
- Rereviews are always COLD — only the Review fixer reuses a session, and "a
  rereview never resumes the session that prescribed its fixes". The
  fresh-context property our crew rereviews provided is preserved inside the
  gate by construction.

**2. Repo-specific review rules** (`review.path_instructions` — the codified
half of the crew/gate boundary; up to 32 entries, 16KB total).

**AUTHORITATIVE VALUE SET: the full 8-entry proposal (plus document.instructions
and the AGENTS.md snippet) lives in issue #117, comment
https://github.com/odjhey/rozoro/issues/117#issuecomment-5420016890 — use that,
not the 3 seeds below (kept for context only):

```yaml
review:
  path_instructions:
    - path: "bin/rzr-pi-watchtower.sh"
      instructions: |
        Byte-hash-pinned by the watchtower-policy-snapshot skill. Any edit must
        update PI_LAUNCHER_SHA256 in BOTH .claude/ and .agents/ skill copies and
        bump the artifact schema; flag any change that does not.
    - path: "lib/rozoro_monitor/protocol.py"
      instructions: |
        Event/registration schemas are a frozen wire contract: unknown fields are
        rejected at runtime. New fields must be optional; immutable identities
        (harness, role, driver_id) must stay immutable.
    - path: "lib/rozoro_monitor/**"
      instructions: |
        Broad `except Exception` is often a deliberate fail-safe/fail-closed
        choice here. Flag only catches that swallow errors without a
        justification comment; do not propose narrowing documented ones.
```

This block is the standing home for the ratchet: when review/test crews hit a
repeat finding class, its codification lands here (see the gate-first
guidelines brief). Expect this list to grow.

Scoping rule for entries (source-proven): the Review step's post-model code
"removes deferred pipeline-owned-delivery findings" — findings that a later
step (docs, lint, format) owns get filtered out of review. So path_instructions
must target REVIEW-owned judgment (correctness, contracts, invariants), never
lint/docs concerns — those entries would be silently dropped. Also note the
repo's AGENTS.md/CLAUDE.md are a live native context channel to gate agents
(project settings enabled globally), so repo instructions already shape gate
behavior implicitly; path_instructions is the explicit, review-scoped channel.

Notes for the implementer:
- `uvx` must be on the PATH of the environment the no-mistakes daemon/agent runs
  in — confirm with a real run, not by assumption (per the repo's guidance that a
  one-shot env prefix does not reconfigure a running daemon).
- Keep the existing history comment block and `auto_fix.review: 1` untouched.
- Per standing decision: NO pre-commit hooks, NO CI lint gates — the no-mistakes
  pipeline is the only mechanical gate. Do not add anything beyond `.no-mistakes.yaml`.

## Verification

1. Baseline sanity on the merged main: both lint commands exit 0 locally.
2. Submit a real candidate through no-mistakes (or reattach flow) and confirm the
   lint stage appears and passes; then intentionally introduce a scratch F401 on a
   throwaway branch and confirm the gate fails/auto-fix handles it, then discard.
3. Handoff should record the run ID and the observed lint stage behavior.

## Measurement (how we know this whole sequence worked)

Watch in `./bin/rozoro report` over the following days:
- count of `rereview`/`retest` task dispatches per deliverable → should drop;
- reviewer/tester turns per deliverable → should drop toward 1 each;
- reaction-gap median can stay flat — the win is fewer hops, not faster hops;
- crew review findings should trend toward novel classes — a repeat class means
  a missed ratchet (missing path_instruction/test), not a crew failure.

## Related (no action in this PR)

The global config already has `eval.auto_capture: true` — every finished run
feeds the local review-eval corpus. Once populated (`no-mistakes eval sets`),
`no-mistakes eval run` can replay candidates pinned to explicit model+effort and
`eval report` scores TP/FN **with tokens and cost** — the empirical way to
compare gate-review agents (e.g. claude/sonnet vs pi/luna) on this repo's own
history. Separate follow-up once the corpus has enough cases.
