---
name: rozoro-authoring
description: >-
  Brief a Coder crew that will modify odjhey/rozoro. Use when Watchtower is
  spawning a Rozoro implementation task and needs to put the repository-specific
  Bash, Python, validation, documentation, and testing rules into that coder's
  brief. Watchtower routes the work; the dispatched coder performs the change.
---

# Rozoro authoring briefing guideline

Use this when **Watchtower is preparing the brief for a Coder crew working on
Rozoro itself**. Include the applicable authoring constraints below together with
the bounded implementation task and acceptance criteria.

Do not implement the repository change in Watchtower merely because this skill is
loaded. These are instructions to render into the coder brief.

This guideline is repository-specific. Explicit operator instructions and repository rules take precedence.

## Before committing

Require the coder to run the deterministic checks relevant to the change and fix known findings before handing work to a more expensive review pipeline:

```bash
shellcheck -x <changed .sh files>
uvx ruff check <changed .py files or dirs>
./tests/run.sh
```

Use the touched tests instead of the full suite only when repository policy and the task permit it.

## Shell

For `bin/*.sh`:

- target Bash 3.2 compatibility;
- do not use associative arrays, `${var,,}`, or `readarray`;
- execute embedded `jq` expressions against sample input when interpolation or escaping is nontrivial;
- do not assume `IFS read` over `jq -r @tsv` preserves empty leading or consecutive fields;
- account for `set -euo pipefail` and short-circuit expressions changing function exit status.

## Python

For `bin/*.py`, `lib/`, and `hooks/`:

- avoid broad exception handling around long-running or lock-holding code when specific failures can be named;
- use `finally` or context managers for file descriptor and lock cleanup;
- pass explicit `check=` to `subprocess.run(...)`;
- preserve exception context with `raise ... from exc`;
- bind loop variables intentionally in closures;
- fsync the parent directory after creating files whose existence is part of crash durability.

## Documentation follows behavior

When behavior, flags, commands, or environment variables change, update every user-facing place that states the old behavior in the same change. Check at least README documentation, `bin/rozoro help`, script usage text, and relevant files under `docs/`.

## Tests prove behavior

- assert observable behavior such as exit status, output, protocol behavior, or on-disk state;
- do not grep source text and call it behavioral proof;
- remember the suite runs in a network-disabled Linux container;
- for a bug fix, prefer a regression test that fails before the fix and passes after it.

Require the coder to report which checks actually ran and any intentionally skipped validation. Do not claim a check passed if it was not executed.
