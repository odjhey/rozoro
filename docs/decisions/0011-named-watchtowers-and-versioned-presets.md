# ADR-0011: Named Watchtowers and versioned presets

review: approved
date: 2026-08-26

## Context

A transport-derived driver id is necessary for wake-ledger reattachment, but it does not identify an operator experiment. Ambient launcher configuration also cannot be attributed after the fact.

## Decision

Watchtower names are metadata; driver ids remain derived from immutable backend identity. Optional JSON presets under `$ROZORO_HOME/watchtower-presets/` select harness, model, and effort. Launch captures the operator-managed version and SHA-256 of the preset bytes. Pi additionally captures the shipped `templates/watchtower.md` hash; v1 has no policy override.

Registration remains filesystem-only. Every schema-1 target and history record has a non-empty `registration_id` of at most 120 safe metadata characters (no `=`, C0, or DEL). `target.json` is the authoritative current attribution. Owner-private `registrations.jsonl` is append-only audit history. Rozoro writers for one driver serialize through an advisory per-driver registration lock. A registration commits when the atomically replaced `target.json` is fsynced; the history record is appended immediately afterward. If a process dies after that commit but before the history append, the next registration detects the target/history registration-id gap and appends a recovery record before recording the new tenure. No multi-file transaction or journal is required.

Dispatch copies a best-effort match into task metadata and `session.json`; absent or ambiguous identity never prevents a spawn.

Filesystem safety for this state means owner-private directories, no-follow traversal, owned regular files, exclusive temporary creation, and fail-closed handling when suspicious state is detected. An actively malicious or continuously racing process running as the same Unix UID is outside this contract. Rozoro does not promise forward progress or checked-inode rename/unlink semantics under same-UID sabotage; adding that guarantee requires a separate architectural decision and an isolation boundary stronger than pathname hardening. Reviews of this feature must not silently broaden that threat model; any stronger guarantee is a new architectural decision.

## Consequences

No preset preserves existing launcher behavior. Editing without bumping a version remains detectable through the byte hash. Normal concurrent Rozoro registrations cannot lose history or interleave current attribution because they share the per-driver lock. Abrupt process death can temporarily leave history one committed target behind, but the next registration repairs that gap from the authoritative target before proceeding.

Reports can later join durable records without daemon, protocol, or database changes. The report aggregation itself is deferred.
