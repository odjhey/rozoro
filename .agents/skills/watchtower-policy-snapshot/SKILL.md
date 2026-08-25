---
name: watchtower-policy-snapshot
description: Persist an immutable, dated snapshot of the explicit Pi Watchtower policy source in this Rozoro checkout, with accurate per-harness coverage. Use when an operator asks to archive, capture, or compare current Watchtower rules or policy.
compatibility: Requires Python 3.11+, a Rozoro checkout, and local filesystem access.
metadata:
  artifact-schema: rozoro.watchtower-policy-snapshot/v5
---

# Watchtower policy snapshot

Capture the active source, not a prose reconstruction.

## Run

From this skill directory:

```bash
python3 scripts/snapshot.py
```

The script resolves the checkout containing this skill, enforces the shipped top-level `args=(...)` plus `exec env ROZORO_WATCHTOWER=1 pi "${args[@]}" "$@"` contract, and verifies that the consumed array contains `templates/watchtower.md` as the value of `--append-system-prompt`. Conditional/dead assignments, uncalled functions, overwritten or unused arrays, echo/string decoys, and conditional/dead invocations do not count as coverage. It records that the current Claude launcher does not pass the captured source instead of claiming false Claude coverage. It prints the new run directory.

Default destination:

```text
$ROZORO_HOME/artifacts/watchtower-policy-snapshots/YYYY-MM-DD/YYYYMMDDTHHMMSS.ffffffZ-<nonce>/
```

If `ROZORO_HOME` is unset, it defaults to `~/.rozoro`. Every invocation reserves a fresh UTC timestamp-plus-nonce directory; never replace an earlier run.

## Return to the operator

Report:

- the printed artifact directory;
- `metadata.json` schema and source SHA-256;
- the copied `watchtower-policy.md` path.

Do not paste the full policy unless asked. Git provenance is accepted only when the repository pathname matches the held validated directory identity before and after every Git read and every required Git command returns a nonempty 40- or 64-hex object ID; otherwise metadata marks it indeterminate, explains the failure, and nulls all Git-derived fields. The script includes only the checked-out policy source and non-secret repository provenance; it excludes task/session data, environment, credentials, and absolute repository paths.

## Retention and safety

Artifacts are owner-private (`0700` directories, `0600` files), use no-follow descriptor-relative creation across every path component, and have no automatic retention deletion. Delete only an exact run directory after explicit operator direction. Do not create or update a `latest` alias. Treat a missing, symlinked, or non-regular policy source as a hard failure.
