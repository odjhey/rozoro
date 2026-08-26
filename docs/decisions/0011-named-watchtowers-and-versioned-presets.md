# ADR 0011: Named Watchtowers and versioned presets

Status: accepted

## Context

A transport-derived driver id is necessary for wake-ledger reattachment, but it does not identify an operator experiment. Ambient launcher configuration also cannot be attributed after the fact.

## Decision

Watchtower names are metadata; driver ids remain derived from immutable backend identity. Optional JSON presets under `$ROZORO_HOME/watchtower-presets/` select harness, model, and effort. Launch captures the operator-managed version and SHA-256 of the preset bytes. Pi additionally captures the shipped `templates/watchtower.md` hash; v1 has no policy override.

Registration remains filesystem-only. `target.json` contains the current optional attribution, while owner-private append-only `registrations.jsonl` is the interval history. Dispatch copies a best-effort match into task metadata and `session.json`; absent or ambiguous identity never prevents a spawn.

## Consequences

No preset preserves existing launcher behavior. Editing without bumping a version remains detectable through the byte hash. Reports can later join durable records without daemon, protocol, or database changes. The report aggregation itself is deferred.
