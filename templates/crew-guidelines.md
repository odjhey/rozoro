## Authoring guidelines — apply while writing, check before committing

You are working in a repo whose changes are validated by an expensive review
pipeline (no-mistakes). Every defect you prevent here is minutes saved there.
These rules encode that pipeline's most-repeated findings in this repo.

### Review/test execution boundary

When acting as a Reviewer or Tester, do not execute the repository test suite as
your verification step; the No-Mistakes gate owns execution evidence bound to the
exact head. Reviewers provide judgment only. Testers may drive focused behavior
exploratorily and design or write new or extended tests that join the repository
suite; the gate enforces those tests on future candidates.

### Working with the gate (source-verified, no-mistakes v1.57.0)

- **Binding tests ride the candidate branch.** Test files authored by the
  gate's own agents are demoted to informational, non-gating findings. If
  coverage matters, commit the test on the branch yourself — never assume the
  pipeline will author it.
- **Do not hand-write PR sections titled Intent, Risk Assessment, Testing, or
  Pipeline.** The PR step strips model/hand-authored versions of those sections
  and rebuilds them deterministically from pipeline state. Put anything durable
  in ordinary description prose or in commit messages.
- **State the task's intent plainly, early in your session.** The pipeline
  harvests local agent session transcripts to infer user intent and feeds the
  summary to its review, test, document, lint, and PR agents. A session that
  names its goal clearly gives the gate better context; garbled or implicit
  intent degrades every downstream gate step.

### Before every commit

For implementation and repair work, run the deterministic checks yourself and fix
what they report:

    shellcheck -x <changed .sh files>
    uvx ruff check <changed .py files or dirs>   # picks up repo ruff.toml
    ./tests/run.sh                               # full suite, or the touched .bats/test files

Do not commit with known lint findings; the review agent will only send them
back to you slower.

### Shell (`bin/*.sh`)

- Target bash 3.2 (macOS default). No associative arrays, no `${var,,}`,
  no `readarray`.
- jq programs embedded in single-quoted strings: verify interpolation syntax
  (`\(...)`) actually parses — run the jq expression once against sample input.
- `IFS read` over `jq -r @tsv` collapses empty leading/consecutive fields;
  guard or use a delimiter-safe format.
- Mind `set -euo pipefail` interaction with `&&`/`||` short-circuits — a
  `cmd && other` as the last line of a function changes the exit status.

### Python (`bin/*.py`, `lib/`, `hooks/`)

- Never write bare `except Exception:` around long-running or lock-holding
  code; catch the specific exceptions, and remember KeyboardInterrupt /
  SystemExit are NOT caught by `except Exception` — don't rely on it for
  cleanup. Use `finally` or context managers for fd/lock release.
- `subprocess.run(...)` always passes an explicit `check=`.
- Re-raise with context: `raise NewError(...) from exc`.
- Closures inside loops capture the variable, not the value — bind with a
  default arg or `functools.partial`.
- Filesystem durability: fsync the parent directory after creating files whose
  existence matters across crashes (locks, sequence files, spool entries).

### Docs move with code

When you change behavior, flags, or environment variables, update every place
that documents them in the same commit: README.md env-flag docs, `bin/rozoro
help` output, script usage banners, and anything under docs/ that states the
old behavior. Stale doc references to removed flags are this repo's single
most-repeated review finding.

### Tests prove behavior, not source text

- Assert observable behavior: exit status, stdout, on-disk state. Never grep
  implementation source for strings as "proof" something works.
- The suite runs in a Linux container (`tests/run.sh`, network-disabled);
  don't depend on macOS-specific behavior, and don't assume network access.
- For a bug fix, write the test so it fails before the fix and passes after.
