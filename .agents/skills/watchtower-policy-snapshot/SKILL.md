---
name: watchtower-policy-snapshot
description: Persist an immutable, dated snapshot of the explicit Pi Watchtower policy sources (core plus shipped missions) in this Rozoro checkout, with accurate per-harness coverage. Use when an operator asks to archive, capture, or compare current Watchtower rules or policy.
compatibility: Requires Python 3.11+, a Rozoro checkout, and local filesystem access.
metadata:
  artifact-schema: rozoro.watchtower-policy-snapshot/v9
---

# Watchtower policy snapshot

Capture the active source, not a prose reconstruction.

## Run

From this skill directory:

```bash
python3 scripts/snapshot.py
```

The script resolves the checkout containing this skill, requires the Pi launcher bytes to match the schema-versioned shipped SHA-256 exactly, then enforces the top-level `args=(...)` plus `exec env ROZORO_WATCHTOWER=1 pi "${args[@]}" "$@"` grammar and verifies that the consumed array carries `--append-system-prompt` for both the `templates/watchtower.md` core and the resolved `$MISSION_FILE` mission (ADR-0013). Conditional/dead assignments, uncalled functions, overwritten or unused arrays, scalar/indexed assignments, `unset`, `eval`, source/dot, function or command-substitution mutation paths, any other byte-level launcher drift, echo/string decoys, and conditional/dead invocations do not count as coverage. It captures the core plus every shipped `templates/missions/*.md`, recording each mission's SHA-256 and its composed core+mission policy SHA-256 (the value a registration records as `policy_sha256`). Operator missions under `$ROZORO_HOME/watchtower-missions/` are noted as not-captured coverage. It records that the current Claude launcher does not pass the captured source instead of claiming false Claude coverage. It prints the new run directory.

Default destination:

```text
$ROZORO_HOME/artifacts/watchtower-policy-snapshots/YYYY-MM-DD/YYYYMMDDTHHMMSS.ffffffZ-<nonce>/
```

The one shared home namespace is the first nonempty of public `ROZORO_HOME`, legacy `RZR_HOME`, and `$HOME/.rozoro`. Every selected or explicit path receives leading `~`/supported `~user` expansion and one lexical absolute normalization. Every invocation reserves a fresh UTC timestamp-plus-nonce directory; never replace an earlier run.

## Return to the operator

Report:

- the printed artifact directory;
- `metadata.json` schema and source SHA-256;
- the copied `watchtower-policy.md` (core) path and the captured `missions/*.md` files.

Do not paste the full policy unless asked. Git provenance is accepted only when the repository pathname matches the held validated directory identity before and after every Git read and every required Git command returns a nonempty 40- or 64-hex object ID; otherwise metadata marks it indeterminate, explains the failure, and nulls all Git-derived fields. The script includes only the checked-out policy source and non-secret repository provenance; it excludes task/session data, environment, credentials, and absolute repository paths.

## Retention and safety

Artifacts are owner-private (`0700` directories, `0600` files), use no-follow descriptor-relative creation across every path component, and have no automatic retention deletion. Delete only an exact run directory after explicit operator direction. Do not create or update a `latest` alias. Treat a missing, symlinked, or non-regular policy source as a hard failure.
