# Dispatch and lifecycle

Use this runbook when driving repository work through Rozoro.

## Boundary

The Watchtower dispatches, routes, and judges. A crew investigates the target repository, implements or evaluates the work, follows that repository's rules, and produces its handoff. Do not pre-solve repository work in the Watchtower merely to make a longer brief.

## Dispatch

1. Identify a unique task key, the target checkout, the intended outcome, and non-inferable constraints.
2. Use a **ship** task for implementation and delivery. Use a **scout** only when the requested outcome is a finding or unresolved uncertainty can change what should be built.
3. Start the crew from the Rozoro checkout with an explicit target `--cwd`.
4. Keep the brief to intent, source pointer, acceptance constraints, and delivery limits. Repository investigation belongs to the crew.
5. For independent work, use an isolated branch/worktree that cannot move another task's branch.

## Observe and steer

- On a notification, reconcile and inspect the named task.
- Treat the latest valid handoff verdict as authoritative; terminal-pane state alone is not acceptance.
- `done` means ready for verification, not accepted or merged.
- Send follow-up to the same live task. If it was reaped, resume that context instead of creating a replacement.
- A `needs-action` report must state the exact operator decision required.
- Treat `waiting` as valid only when supported background work is currently active and no input is requested.

## Verify and retain

Verify claimed repository state, immutable head, tests, pull request, and CI independently as appropriate. Keep a crew resident until its result is captured and accepted or intentionally abandoned. Reaping is lifecycle cleanup, not proof of repository cleanliness or acceptance.

## Stop conditions

Stop and request a decision for scope changes, destructive or irreversible actions, product/intent choices, protection bypasses, credentials or live-provider use without an approved gate, and any conflict between operator and repository instructions.
