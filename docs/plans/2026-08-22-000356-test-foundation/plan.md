# Build an isolated Bats regression harness

Status: proposed implementation plan

Created: 2026-08-22 00:03:56 Asia/Manila

Scope: issue #11

Program coordination: [architecture findings](../2026-08-22-000356-architecture-findings/plan.md)

## Issue reference

Add a lightweight automated regression suite for protocol parsing and lifecycle
glue

https://github.com/odjhey/rozoro/issues/11

## Dependency references

Bats-core documentation

https://bats-core.readthedocs.io/en/stable/

Pinned Bats-core release

https://github.com/bats-core/bats-core/releases/tag/v1.14.0

## Outcome

Rozoro has one deterministic test command backed by Bats-core that exercises its
shell and Python protocols without a real Herdr server, coding harness, user
home, or developer checkout. The foundation lands before behavior changes for
issues #8, #9, and #10; those PRs extend it, and a final audit closes #11.

Bats-core is a suitable dependency because it is TAP-compliant, supports Bash
3.2 and later, and provides isolated test functions, `setup`/`teardown`, and
the `run` helper. Pin v1.14.0 in CI. Require `bats` on PATH for local runs and
give contributors platform-specific installation guidance.

Do not add bats-support or bats-assert initially. Keep project-specific
assertions in one helper; add another dependency only if repeated test code
demonstrates a concrete need.

## Current-state evidence

- There is no `tests/` directory or CI workflow.
- README verification is manual and tied to one Herdr 0.8.2 environment.
- Correctness depends on handoff parsing, acknowledgement cursors, raw socket
  framing, watcher deduplication, filesystem updates, locking, and failure paths.
- The project promises stock macOS Bash 3.2 compatibility, which a modern
  Linux-only syntax check cannot establish.

## Test layout

Add:

- `tests/run.sh`: the single documented entry point. It validates a supported
  Bats version, then runs `bats tests` with deterministic formatting.
- `tests/test_helper/common.bash`: shared Bats `setup`/`teardown` helpers,
  fixture-root creation, command assertions, child-process registration, and
  cleanup.
- `tests/fakes/herdr`: a PATH-injected fake driven by fixture files/environment.
  It records argv and serves tab, pane, agent, wait, session, and ordered
  transient-failure responses.
- `tests/handoff.bats`: handoff projection and acknowledgement fixtures.
- `tests/watch.bats`: initial reconciliation, event projection, deduplication,
  and overlapping watcher behavior.
- `tests/eventwait.bats`: Bats cases that start a Python standard-library Unix
  socket fixture and exercise `herdr-eventwait.py`.
- `tests/lifecycle.bats`: spawn, send/control, link/resume, and teardown paths.
- `tests/lock.bats`: live-holder refusal, stale-holder reclaim, release, and
  failure cleanup.
- `tests/syntax.bats`: `bash -n` for shell entry points and Python compilation
  using an isolated bytecode directory.
- `.github/workflows/test.yml`: Linux and macOS jobs installing Bats-core
  v1.14.0 and invoking `./tests/run.sh`.

Do not name helper files `*.bats`; only runnable suites should be discovered by
the Bats directory runner.

## Isolation invariants

Each Bats test must:

1. Create a per-test temporary `HOME`, `ROZORO_HOME`, harness config root,
   socket path, and checkout when needed.
2. Prepend `tests/fakes` to PATH and fail if production code resolves a real
   Herdr binary or socket.
3. Register background process IDs and clean them in `teardown` on pass,
   assertion failure, signal, and early exit.
4. Delete only the exact directory rooted under `$BATS_TEST_TMPDIR`.
5. Set `PYTHONPYCACHEPREFIX` under `$BATS_TEST_TMPDIR`.
6. Never inherit or inspect the invoking user's `~/.rozoro`, Claude project
   store, Herdr session, or Git checkout.

Install a sentinel outside the fake home and add a negative assertion that fails
if a command accesses paths beyond the fixture roots. Avoid relying on
`BATS_RUN_TMPDIR` details that differ across unsupported Bats versions; use the
documented `BATS_TEST_TMPDIR` and `BATS_TEST_DIRNAME` interfaces.

Background socket and watcher tests must close inherited file descriptors.
Bats documents descriptor 3 and background children as common causes of hanging
test runs; explicitly redirect or close descriptors in spawned helpers.

## Foundation PR

The first PR establishes infrastructure and characterizes current behavior. It
references #11 but does not close it.

### Handoff and status characterization

Cover:

- no handoff, one done block, open input followed by done, FIFO acknowledgement,
  malformed/missing fields, headings in Markdown content, and cursor boundaries;
- repeated status reads and `.seen-blocks`, including a named characterization
  of the current reader-relative mutation that issue #9 replaces with a purity
  assertion;
- concurrent readers producing no torn cursor state.

### Watch and event transport characterization

Cover:

- exact `events.subscribe` request and `subscription_started` acknowledgement;
- multiple pane attribution, duplicate edge suppression, two overlapping
  `--once` watchers waking on the same edge, initial level reconciliation, and
  subsequent edge persistence;
- timeout, malformed acknowledgement, server close, socket failure, and broken
  stdout handling in `herdr-eventwait.py`.

### Lifecycle and lock characterization

Cover:

- spawn metadata, transient `agent_pane_busy`, terminal start failure, unknown
  and dead targets, data/control separation, task-folder preservation, legacy
  Claude resume, live-task resume refusal, and current teardown behavior;
- live lock-holder refusal, stale-holder reclaim, release, and cleanup when the
  protected command fails.

Do not weaken assertions to hide a known bug. Give each current-bug
characterization an explicit test name and replace it in the behavior PR that
fixes the defect.

## Bats installation and version policy

Local `tests/run.sh` should:

1. Require `bats` on PATH.
2. Parse `bats --version`.
3. Reject unsupported versions with installation instructions.
4. Execute the test directory without downloading or mutating the repository.

Document Homebrew installation on macOS and the official source/npm options on
other platforms. Avoid relying on old distribution packages without checking
their version.

CI must pin v1.14.0 rather than track a moving branch. Install it into the job's
temporary/tool directory, add its `bin` to PATH, and run `./tests/run.sh`.
Keep the pin in one workflow variable so upgrades are deliberate and reviewable.

The product remains Bash 3.2-compatible. Tests may use Bats syntax and documented
Bats helpers, but project helper scripts sourced by production code must not gain
Bash 4 requirements.

## Extensions owned by behavior PRs

The #8 PR adds non-Git, clean/no-upstream, dirty, unpushed, `--keep-tab`,
restart, and no-Git-invocation teardown coverage.

The #9 PR replaces reader-mutation characterization with pure-read snapshots,
canonical handoff parsing, turn-edge classification, runtime/task schema,
overlapping watcher, and compatibility-token coverage.

The #10 PR adds public Herdr session metadata, delayed identity, Claude fallback,
alternate config root, same-cwd transcript, non-Claude, mismatch, legacy/v2,
malformed descriptor, unsupported capability, and resume argv fixtures.

Each behavior PR owns the tests for behavior it changes; do not postpone all
verification to the final audit.

## Final coverage-audit PR

After #8, #9, and #10 merge:

1. Compare the complete issue #11 checklist with the merged Bats suite.
2. Add missing failure fixtures, especially transient start failure, malformed
   subscription acknowledgement, socket close, and cleanup after failure.
3. Confirm Linux and macOS use exactly `./tests/run.sh`.
4. Update README with Bats installation, the command, supported platforms, and a
   clear distinction between automated coverage and optional Herdr smoke tests.
5. Run the suite from a clean clone with no Herdr server and close #11 only when
   every acceptance criterion is represented and green.

## Risks and mitigations

| Risk | Mitigation |
| --- | --- |
| Bats version drift changes behavior | Pin v1.14.0 in CI, enforce a supported local range, and upgrade deliberately |
| Fake Herdr drifts from 0.8.x | Keep representative raw JSON fixtures beside tests and confirm them in an optional release smoke pass |
| Tests accidentally touch user state | Replace HOME/config/socket roots, use sentinels, and fail on paths outside the fixture tree |
| Child/socket leaks hang Bats | Centralize process registration, close inherited descriptors, kill and wait in teardown, and test cleanup on failure |
| Bash 3.2 promise regresses | Run the pinned Bats suite on macOS and avoid Bash 4 features in production/shared shell helpers |
| Characterization fossilizes bugs | Name known-bug expectations and replace them in the corresponding behavior PR |

## Acceptance criteria

- `./tests/run.sh` is documented and runs the Bats suite from a clean clone.
- The suite needs no live Herdr server or installed coding harness.
- Tests never read or mutate real user homes, session stores, sockets, or
  working trees.
- Shell and Python syntax checks are included.
- Linux and macOS CI install Bats-core v1.14.0 and execute the same command.
- Local version failures explain how to install a supported Bats release.
- Failures identify the test and violated expectation and exit non-zero.
- Temporary processes, sockets, bytecode, and directories are cleaned on all
  tested exit paths.
- Coverage includes the final behavior and compatibility paths specified by the
  #8, #9, and #10 plans.
- README labels remaining real-Herdr checks as optional manual integration smoke
  tests rather than automated evidence.
