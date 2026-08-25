---
name: watchtower-policy-snapshot
description: Persist an immutable, dated snapshot of the Watchtower policy currently used by this Rozoro checkout. Use when an operator asks to archive, capture, or compare the current Watchtower rules or policy.
compatibility: Requires Python 3.11+, a Rozoro checkout, and local filesystem access.
metadata:
  artifact-schema: rozoro.watchtower-policy-snapshot/v1
---

# Watchtower policy snapshot

Capture the active source, not a prose reconstruction.

## Run

From this skill directory:

```bash
python3 scripts/snapshot.py
```

The script resolves the checkout containing this skill and copies the current `templates/watchtower.md`, which the Watchtower launchers pass as the launch-time system prompt. It prints the new run directory.

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

Do not paste the full policy unless asked. The script includes only the checked-out policy source and non-secret repository provenance; it excludes task/session data, environment, credentials, and absolute repository paths.

## Retention and safety

Artifacts are owner-private (`0700` directories, `0600` files) and have no automatic retention deletion. Delete only an exact run directory after explicit operator direction. Do not create or update a `latest` alias. Treat a missing, symlinked, or non-regular policy source as a hard failure.
