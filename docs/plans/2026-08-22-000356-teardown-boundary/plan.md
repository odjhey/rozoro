# Remove Git policy from teardown

Status: proposed implementation plan

Created: 2026-08-22 00:03:56 Asia/Manila

Scope: issue #8

Program coordination: [architecture findings](../2026-08-22-000356-architecture-findings/plan.md)

Test prerequisite: [Bats regression harness](../2026-08-22-000356-test-foundation/plan.md)

## Issue reference

Restore the spawner boundary: remove Git/upstream policy from teardown

https://github.com/odjhey/rozoro/issues/8

## Outcome

Teardown resolves and closes an exact Herdr tab, removes ephemeral rozoro
runtime metadata, and preserves durable task data. It never inspects the task
checkout or claims that closing a terminal landed, accepted, discarded, or
deleted Git work.

Acceptance and delivery remain driver/crew/repository policy. Do not replace the
current guard with task-owned worktrees, Git attribution, PR inspection, merge
checks, or another repository policy mechanism.

## Current-state evidence

- `bin/rzr-teardown.sh` calls `rzr_unlanded_reasons` unless `--force` is used.
- `bin/rzr-lib.sh` inspects the entire checkout for dirty files, upstream
  configuration, and ahead commits.
- A task can be blocked by unrelated work because the check has no task
  attribution.
- A clean repository without an upstream is treated as potentially unlanded.
- `bin/rzr-control.sh restart` passes `--force` even though it recreates a tab
  in the same checkout.
- README and skill text describe force as discarding work, but closing a tab does
  not remove working-tree changes or commits from disk.

## Ownership invariants

1. Teardown requires an exact tracked task and never guesses a target.
2. Without `--keep-tab`, it attempts to close only the recorded Herdr tab.
3. It removes only live rozoro metadata and runtime observation files.
4. `tasks/<id>/` and the recorded checkout always survive.
5. Git state cannot allow, block, or alter teardown.
6. A failed/already-gone tab close retains existing warning behavior and does not
   expand into repository recovery logic.

## File-level implementation

### `bin/rzr-teardown.sh`

- Remove `rzr_unlanded_reasons` and all checkout-policy messages.
- Preserve exact task validation, `--keep-tab`, tab close, durable task data,
  and live state-record removal.
- Remove `--force` from documented usage and help.
- For one compatibility window, accept `--force` as a deprecated no-op and warn
  that teardown does not inspect Git. Do not call it a discard operation.
- If issue #9 has landed, also remove its structured ephemeral `runtime.json`
  and `turn.json`; coordinate filenames rather than inventing alternatives.

### `bin/rzr-lib.sh`

Delete `rzr_unlanded_reasons` after confirming there are no callers. Do not
retain unused Git helpers as an implied policy surface.

### `bin/rzr-control.sh`

Make restart invoke teardown without `--force`. Update comments to explain that
the checkout remains because teardown never mutates it, not because a force
override makes data loss safe.

### Documentation and skill

Update:

- `README.md`
- `templates/watchtower.md`
- `.agents/skills/rozoro/SKILL.md`

Remove claims that teardown verifies landed work or that force discards the
checkout. State that the watchtower/user decides acceptance and the crew follows
repository-specific delivery rules. Durable task and resume behavior remain.

## Bats coverage

Extend `tests/lifecycle.bats` using the fake Herdr and temporary repositories:

- a non-Git cwd;
- a clean Git checkout with no upstream;
- uncommitted and untracked files;
- commits ahead of an upstream;
- an unknown task failing closed;
- a failed or already-gone tab close;
- `--keep-tab` preserving the Herdr tab;
- `tasks/<id>/` surviving every successful teardown;
- restart preserving id, profile, cwd, and checkout contents;
- deprecated `--force` compatibility;
- fake-PATH evidence that teardown invokes no Git command.

Run `./tests/run.sh` on Linux and macOS, the syntax suite, and
`git diff --check`.

## Compatibility and rollout

The behavior becomes less restrictive: previously blocked teardown calls now
succeed. Existing task metadata, `--keep-tab`, task folders, and restart launch
profiles do not change.

Accepting deprecated `--force` for one release window avoids breaking scripts.
Its warning tells callers to remove the option. A later dedicated cleanup may
reject it; do not silently assign it a new meaning.

This plan depends only on the Bats-foundation PR. It can be implemented in
parallel with issues #9 and #10 afterward.

## Risks and mitigations

| Risk | Mitigation |
| --- | --- |
| Operators relied on teardown as a Git reminder | Announce the boundary and keep acceptance guidance in watchtower/crew policy |
| Scripts still pass `--force` | Accept it temporarily as a warning no-op |
| Restart behavior changes accidentally | Fixture exact teardown-and-respawn argv and preserved profile/cwd |
| Docs retain data-loss claims | Search source, help, README, template, and skill for `unlanded`, `discard`, and `--force` |

## Acceptance criteria

- Teardown succeeds in non-Git, no-upstream, dirty, and ahead-of-upstream
  disposable checkouts.
- Unknown tasks still fail closed and `--keep-tab` is unchanged.
- The checkout and durable `tasks/<id>/` folder survive teardown.
- Restart recreates the same task id/profile/cwd without a force bypass.
- No production teardown/control path invokes Git.
- No code or documentation claims tab teardown establishes landed, merged,
  accepted, or discarded state.
- Compatibility behavior for existing `--force` callers is tested and
  documented.
