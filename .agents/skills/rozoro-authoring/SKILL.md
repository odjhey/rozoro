---
name: rozoro-authoring
description: >-
  Apply Rozoro's repository-specific coding and validation practices while
  modifying the Rozoro source tree. Use only for changes to odjhey/rozoro itself;
  do not apply its bash, Python, or test constraints to unrelated repositories.
metadata:
  derived-from: templates/crew-guidelines.md
---

# Rozoro authoring

This skill is repository-specific. Explicit operator instructions and repository rules take precedence.

## Before committing

Run the deterministic checks relevant to the change and fix known findings before handing work to a more expensive review pipeline:

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

Report which checks actually ran and any intentionally skipped validation. Do not claim a check passed if it was not executed.
