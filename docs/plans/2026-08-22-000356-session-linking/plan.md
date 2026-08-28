# Make conversation linking capability-aware

Status: historical — shipped and regression-tested (see docs/current-vs-target.md)

Created: 2026-08-22 00:03:56 Asia/Manila

Scope: issue #10

Program coordination: [architecture findings](../2026-08-22-000356-architecture-findings/plan.md)

Test prerequisite: [Bats regression harness](../2026-08-22-000356-test-foundation/plan.md)

## Issue reference

Make conversation linking capability-aware and prefer Herdr-reported session
identity

https://github.com/odjhey/rozoro/issues/10

## Outcome

`session.json` remains only a durable harness-conversation descriptor. Rozoro
prefers Herdr's public reported session identity, uses vendor-private discovery
only as a bounded harness-specific fallback, and enables exact resume only for
verified capabilities.

The portable contract remains `brief.md -> handoff.md`; exact transcript resume
is explicitly harness-specific. Herdr remains responsible for terminal,
process, tab, and workspace persistence.

## Current-state evidence

- `bin/rzr-start.sh` always retries `bin/rzr-link.sh`, regardless of harness.
- `rzr-link.sh` scans `$HOME/.claude/projects/<cwd-slug>/*.jsonl`, writes
  `harness: claude`, and stores a shell command string.
- The fallback ignores `CLAUDE_CONFIG_DIR` and other Claude profiles.
- Codex, Copilot, and Pi starts can emit a misleading Claude transcript lookup.
- `bin/rzr-resume.sh` reads top-level `session_id` and constructs Claude
  arguments directly, leaving no normalization point.
- Herdr 0.8.2 `agent get` exposes an `AgentInfo` object whose public
  `agent_session` contains `source`, `agent`, `kind`, and `value` when an
  integration reports them.

## Identity and capability invariants

1. Rozoro task id is work identity.
2. Herdr pane/tab/terminal id is runtime identity.
3. Harness session id/path is conversation identity.
4. Recording an identity does not automatically enable resume.
5. Start succeeds when identity or exact resume is unavailable.
6. Resume never silently creates a cold session.
7. Stored commands are argv arrays validated through an allowlisted harness
   capability; no shell text is evaluated.
8. Non-Claude paths never inspect Claude storage.

## Session descriptor v2

New links use:

```json
{
  "schema_version": 2,
  "task_id": "issue-42",
  "harness": "claude",
  "cwd": "/repo",
  "session": {
    "kind": "id",
    "value": "9b92...",
    "source": "herdr-integration",
    "integration_source": "herdr:claude"
  },
  "resume": {
    "supported": true,
    "argv": ["claude", "--resume", "9b92..."]
  }
}
```

When identity is absent or the harness is unsupported, `session` may be null and
`resume` contains `supported: false` plus a stable reason such as
`session-unavailable`, `unsupported-harness`, `unsupported-kind`, or
`agent-mismatch`. That descriptor is a successful capability result, not a
failed task start.

Claude is the only initially enabled exact-resume capability. Other reported
identities may be recorded, but resume remains disabled until invocation and
Herdr-start behavior have dedicated fixtures and real verification.

## Resolution flow

1. Read pane, harness, and cwd from `state/<id>.meta`.
2. Query `herdr agent get <pane>` and parse
   `.result.agent.agent_session` first, with Bats fixtures for supported
   defensive Herdr 0.8.x nesting.
3. Validate the reported agent against the recorded harness and validate kind and
   value as safe data.
4. If valid identity exists, write v2 atomically.
5. If Claude identity is not yet available, retry for the bounded birth window,
   then use the marker fallback under
   `${CLAUDE_CONFIG_DIR:-$HOME/.claude}/projects/<cwd-slug>`.
6. For non-Claude harnesses, record the available or unsupported capability
   without scanning Claude storage.
7. On resume, normalize v1 or v2, verify the capability, and pass validated argv
   to `herdr agent start`; otherwise fail with the precise stored reason.

## File-level implementation

### `bin/rzr-lib.sh`

Add Herdr session extraction, v1/v2 normalization, atomic descriptor writes,
safe identity validation, and a small allowlisted resume-capability table. Do
not infer support from a harness binary name alone.

### `bin/rzr-link.sh`

Read authority from task metadata. Keep positional cwd as a deprecated override.
Prefer Herdr metadata, validate harness agreement, scope the marker fallback to
Claude, respect `CLAUDE_CONFIG_DIR`, and write supported or unsupported v2
descriptors atomically and idempotently.

Marker matching remains task-specific and concurrency-safe when crews share a
cwd. If multiple files match unexpectedly, fail with evidence rather than
choosing an arbitrary transcript.

### `bin/rzr-start.sh`

Treat unsupported linking as a completed capability check. Retry only where a
supported harness identity may appear after startup. Do not print a Claude
lookup warning for Codex, Copilot, or Pi.

### `bin/rzr-resume.sh`

Normalize v1/v2, preserve live-task refusal, dispatch only validated allowlisted
argv, and return precise unsupported/unavailable diagnostics. Never fall back to
`rzr-start` or another cold conversation.

### `bin/rzr-spawn.sh` and documentation

Keep recorded harness metadata authoritative and separate from task/runtime
identity. Update `README.md` and `.agents/skills/rozoro/SKILL.md` to distinguish
portable handoff continuation from harness-specific exact resume and document
diagnostics and compatibility.

## Bats coverage

Extend `tests/lifecycle.bats` with:

- the primary Herdr 0.8.x `.result.agent.agent_session` shape and every
  supported defensive nesting;
- Claude Herdr-first linking with no transcript directory;
- delayed Herdr identity during bounded retries;
- Claude marker fallback under default and `CLAUDE_CONFIG_DIR` roots;
- multiple same-cwd transcripts and ambiguous matches;
- non-Claude start/link proving no Claude path access;
- reported-agent mismatch and malformed/unsafe identities;
- schema-v1 read compatibility without rewrite;
- schema-v2 Claude resume argv and follow-up behavior;
- unsupported harness/kind, missing identity, and malformed descriptor messages;
- live-task resume refusal and absence of cold-spawn fallback.

Run the complete Linux/macOS Bats suite, syntax checks, and `git diff --check`.

## Compatibility and migration

- Existing top-level `session_id`, `harness`, and `cwd` descriptors normalize
  at read time and remain resumable. Reads do not rewrite them.
- The next successful explicit link may write v2 atomically.
- `rzr-link.sh <id> <cwd>` remains accepted while metadata becomes authority.
- Missing Herdr `agent_session` is supported on 0.8.x and falls back only where
  an implemented harness strategy exists.
- Legacy `resume` shell strings are not evaluated; capability logic rebuilds
  validated argv from normalized identity.
- Exact resume remains Claude-only until another harness has Bats fixtures and
  real invocation verification.

## Risks and mitigations

| Risk | Mitigation |
| --- | --- |
| Herdr response nesting varies | Parse the documented shape first and allow only fixture-backed alternatives |
| Metadata reports another harness | Validate against task metadata and store a stable mismatch reason |
| Descriptor becomes command injection | Reject controls/newlines, validate kind/value, store argv, use an allowlist, and never `eval` |
| Claude fallback selects the wrong transcript | Match the unique task marker and fail on ambiguity |
| Unsupported linking makes start look failed | Model unsupported/unavailable as explicit successful capability outcomes |

## Acceptance criteria

- With Herdr session metadata, linking succeeds without scanning Claude storage.
- Claude fallback works in default and alternate config roots and remains
  task-specific under shared-cwd concurrency.
- Codex, Copilot, and Pi never perform a Claude transcript lookup.
- Existing Claude v1 descriptors remain resumable without eager rewrites.
- New descriptors name schema, harness, identity source/kind/value, and resume
  capability explicitly.
- Resume dispatches only validated argv and never shell text or cold fallback.
- Unsupported/missing/malformed capabilities fail with stable precise messages.
- Documentation separates task handoff portability, Herdr runtime persistence,
  and harness-specific conversation resume.
