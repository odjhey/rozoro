# Add first-class private Claude profile selection across Rozoro and no-mistakes

**Status: proposed; planning document only. Nothing in this document is implemented.**

This plan defines two coordinated but independently owned changes:

1. **Rozoro** selects and durably resumes Claude crews under an explicitly named,
   machine-local Claude profile, including propagation through Herdr into the
   real Claude process and Rozoro hooks.
2. **no-mistakes** separately selects a named Claude profile for its own
   review/fix/document/CI-repair subprocesses and resident AXI daemon.

The no-mistakes work belongs in the separate no-mistakes project and release.
Rozoro must not read or modify no-mistakes configuration, and no-mistakes must
not read or modify Rozoro configuration. The integration boundary is an opaque
profile name with the same operator-facing semantics, not a shared state store,
ambient environment inheritance, or a runtime dependency between projects.

## Outcome

An operator can define an opaque local name such as `secondary-a` and use it
without exposing the private account path:

```sh
./bin/rozoro start task-name --body task.md --cwd /path/to/repo \
  --claude-profile secondary-a

# Exact resume resolves the profile recorded by the original launch.
./bin/rozoro resume <task-id> --prompt 'Continue with this follow-up.'

# Independent selection for no-mistakes' own Claude pipeline agent.
no-mistakes axi run --intent 'the original user intent' \
  --claude-profile secondary-a
```

The profile name resolves locally to both a Claude configuration directory and
an exact Claude executable. Neither value is committed to a repository, copied
into a handoff, printed in normal output, or inferred from the process that
invoked the tool.

The design must provide these invariants:

1. Profile selection is explicit, named, local, and harness-specific.
2. A fresh launch and every exact resume use the same selected account root.
3. The actual Claude process and its hooks prove they received the selection.
4. A supported, version-certified executable is the one actually launched.
5. A profile mismatch, unsafe directory, unsupported binary, or missing proof
   fails before task delivery rather than silently using the primary account.
6. Concurrent crews and no-mistakes runs may select different profiles without
   changing a global default or leaking into one another.
7. Quota exhaustion never silently changes account, provider, or conversation.
8. Existing callers that select no profile retain current behavior.
9. Private account paths and credentials never enter public GitHub artifacts.

## Current architecture and reproduced boundary

### Rozoro today

`bin/rozoro` is only a dispatcher. `rzr-start.sh` reserves and renders a task,
then delegates to `rzr-spawn.sh`. Spawn creates a Herdr tab and invokes:

```text
herdr agent start <name> --kind claude --pane <pane> -- <claude args>
```

The dispatcher process is not the Claude process parent. Herdr 0.8.2's resident
server owns the pane shell. Its `agent start` API accepts a canonical agent kind
and passthrough arguments, but no per-agent environment map. Herdr constructs
`claude <args>` and submits it to the existing pane shell.

Herdr 0.8.2 does provide a supported per-tab environment interface:

```text
herdr tab create ... --env KEY=VALUE
```

That environment belongs to the shell created for the tab and therefore can
reach the later `agent start` process. It is the smallest supported propagation
seam, but passing a private absolute path directly on the Herdr command line
would expose it in argv and potentially logs. The implementation must use the
seam without placing the account path in Herdr argv.

Current Claude crews always use the event bus. Spawn preallocates a Claude UUID,
generates a task-local `--settings` overlay, and certifies Claude Code 2.1.240
before launch. The generated hook proof records the executable selected by the
Rozoro caller, but current Herdr launch still resolves the bare command
`claude` inside its pane shell. Those can be different executables. A caller-side
`command -v claude` check alone therefore does not prove which binary Herdr
launched.

`rzr-link.sh` currently scans the primary Claude project store under the user's
home and ignores alternate Claude configuration roots. `session.json` persists
conversation ID, harness, cwd, resume text, and resolved model profile. Resume
reconstructs Claude argv from that descriptor but has no durable account-root
selection. Teardown preserves the task folder; restart preserves the model
profile while deliberately creating a new conversation.

### no-mistakes today

no-mistakes is normally invoked as a terminal CLI, but AXI is a client of a
resident daemon. The daemon independently resolves its login-shell environment,
constructs its configured pipeline agent, creates run worktrees, owns pipeline
custody, and directly launches Claude with `os/exec` for each model-producing
step.

Its Claude adapter supports stream JSON, structured output, bounded retries,
and exact fixer-session reuse via `claude -p --resume <id>`. Run/session state is
persisted so an approval gate can survive daemon restart. Review, review-fix,
test/evidence, document/lint, rebase/PR assistance, and CI repair all reach the
shared agent invocation seam. The CI monitor itself is provider polling, but a
later CI repair or conflict-fix turn launches the run's configured agent.

The initiating terminal or crew harness does not select that agent. A Pi crew
may invoke no-mistakes while no-mistakes independently launches Claude. This is
why a Pi crew can appear healthy while the no-mistakes Claude account is out of
quota.

### When a terminal prefix works and when it does not

This distinction must be documented explicitly:

| Invocation | Result |
| --- | --- |
| `CLAUDE_CONFIG_DIR=<private> claude` | Works because Claude is the direct child of that shell command. |
| Prefixing `./bin/rozoro start` | Not sufficient: Herdr's already-running server creates the pane and launches Claude later. |
| Prefixing `no-mistakes axi run` | Not sufficient with a resident daemon: AXI sends IPC; the existing daemon launches Claude later. |
| Prefixing no-mistakes daemon startup | May affect all daemon children, but is daemon-wide, races concurrent profiles, and is not a supported per-run selector. |

Ambient `CLAUDE_CONFIG_DIR` may remain a Claude CLI feature, but neither project
may treat its accidental inheritance as first-class profile selection or
acceptance evidence.

## Responsibility boundary

### Rozoro owns

- Local Claude profile definitions for Rozoro-managed Claude crews.
- CLI/preset resolution for fresh start and exact resume.
- Herdr tab environment, launcher shim, executable certification, hook proof,
  task/session durability, linking, restart, reap, and diagnostics.
- Refusing a Claude profile flag for a non-Claude effective harness.

### The separate no-mistakes project owns

- Its own local Claude profile definitions.
- AXI CLI and IPC protocol fields for per-run selection.
- Resident daemon resolution, run/session persistence, direct Claude process
  environment, attestation, retry/fallback classification, custody recovery,
  status output, and documentation.
- Applying the selected profile to every no-mistakes-owned Claude invocation,
  regardless of the shell or harness that invoked AXI.

### Neither project owns

- Claude credentials, account migration, subscription state, or quota routing.
- Copying Claude settings, auth files, transcripts, or sessions between roots.
- Mutating Claude's global defaults.
- Automatically choosing another account after a service or quota error.
- Reading the other project's private configuration.

## Named profile contract

A profile is one account root plus one exact executable. It is not an arbitrary
environment map, an account credential, or an ordered fallback chain.

Use conservative opaque names:

```text
[a-z0-9][a-z0-9._-]{0,63}
```

Operators should prefer neutral labels such as `primary-a` or `secondary-a`, not
email addresses, organization names, or billing labels. Profile names are local
metadata but must still be redacted to placeholders in public evidence.

### Rozoro local schema

Store one JSON file per profile outside all repositories:

```text
$ROZORO_HOME/claude-profiles/<name>.json
```

Proposed schema:

```json
{
  "schema": 1,
  "config_dir": "~/<private-claude-config-directory>",
  "executable": "~/<private-certified-install>/bin/claude"
}
```

`config_dir` and `executable` are intentionally absent from crew presets. A crew
preset contains only the opaque reference:

```json
{
  "harness": "claude",
  "model": "sonnet",
  "permission_mode": "auto",
  "effort": "",
  "fast": false,
  "claude_profile": "secondary-a",
  "rules": []
}
```

Rozoro never creates, migrates, or rewrites these operator files.

### no-mistakes local schema

The separate project adds a global-only mapping under its existing machine
configuration. Illustrative shape:

```yaml
claude_profiles:
  secondary-a:
    config_dir: ~/<private-claude-config-directory>
    executable: ~/<private-certified-install>/bin/claude
```

This block defines names but does not change the selected global agent or
profile. Repository `.no-mistakes.yaml` must ignore or reject the field, even
when trusted repo commands are enabled. Profile definition and selection decide
which credentials a daemon uses, so they remain operator-only machine policy.

The two local maps may use the same name and values, but neither is authoritative
for the other. This small duplication is preferable to a shared registry,
shared daemon, or package dependency whose failure or version skew could break
both tools.

## Resolution, canonicalization, and validation

Both implementations should follow equivalent behavior, with tests in their own
language/runtime.

### Path normalization

1. Trim neither arbitrary path content nor shell syntax into a new meaning.
2. Expand only exact `~` and a leading `~/` against the current user's home.
3. Reject `~other`, environment substitutions, command substitutions, NUL,
   control characters, and relative paths.
4. Resolve `.` and `..` lexically, then canonicalize against the filesystem.
5. Require the configuration directory to exist before any Herdr tab, AXI run,
   worktree, or model subprocess is created.
6. Store and compare an internal non-path fingerprint, not the canonical path,
   in durable runtime descriptors.

### Configuration-directory checks

- `lstat` the requested leaf and reject a symlink.
- Require a directory owned by the effective user.
- Require owner read/write/search and no group/world permission bits.
- Refuse a replaced device/inode between validation and launch.
- Do not chmod, repair, initialize, or recursively inspect the directory.
- Let Claude own the format and permissions of files inside it.

### Profile-file checks

- Profile root directory is current-user-owned, non-symlink, and mode `0700`.
- Definition file is a current-user-owned, non-symlink regular file, mode `0600`.
- Reject malformed JSON/YAML, unknown schema versions, duplicate names, empty
  known fields, and unsupported keys that would affect execution.
- Never print the definition file's values in normal errors or doctor output.

### Executable checks

Global npm and version-manager launchers commonly use symlinks, so executable
validation differs from config-root validation:

1. Resolve the entire executable symlink chain.
2. Require the final target to be a regular executable owned by the current user
   or root and not group/world writable.
3. Reject a writable or unsafe chain component that could redirect execution.
4. Invoke that exact target with `--version` under a short timeout.
5. Match an explicitly certified version/capability set.
6. Record resolved target, version, device, and inode only in owner-private proof
   state; expose only version and a non-path fingerprint diagnostically.
7. Revalidate immediately before every fresh launch and resume.

Rozoro's lifecycle hook certification remains independent of no-mistakes'
Claude adapter certification. A binary used by both profiles must satisfy both
projects' supported capability sets. A newer globally installed Claude must not
silently replace an isolated certified npm executable named by a profile.

## Rozoro CLI and precedence

Add `--claude-profile <name>` to `start`, `spawn`, and `resume`, and add the
known string field `claude_profile` to crew presets.

### Fresh start/spawn

```text
explicit --claude-profile > configured crew preset > unset
```

Unset means today's primary/default behavior. Rozoro must not read ambient
`CLAUDE_CONFIG_DIR` as another precedence level. If a profile resolves while the
effective harness is not Claude, fail before render or Herdr mutation so the
operator cannot believe a profile applied to Pi, Codex, or Copilot.

Profile resolution happens after effective harness/preset resolution but before:

- handoff/settings generation;
- resident monitor mutation attributable to the task;
- task tab creation; and
- live state metadata.

`start` passes the resolved name through to spawn exactly as it already does for
model/effort/fast flags.

### Exact resume

```text
persisted session profile > matching explicit assertion > legacy/unset
```

- A descriptor with a profile always uses that profile.
- Passing the same name is accepted as an assertion.
- Passing a different name fails before tab creation.
- A legacy descriptor with no profile uses current default behavior.
- An explicit profile may supply missing profile context for a legacy descriptor
  only when the descriptor has no stored profile; successful relink persists it.
- A missing, changed, unsafe, or unsupported stored profile never falls back to
  the primary account and never cold-spawns.

Changing accounts is not exact resume. There is no force flag to redefine that
identity in this scope.

## Propagation through Herdr

### Why direct `--env CLAUDE_CONFIG_DIR=<path>` is not enough

It would reach the pane shell, but it places an account path in the Rozoro-to-
Herdr CLI argv and potentially Herdr logs. It also does not prove the pane shell
resolved the certified executable checked by Rozoro.

### Task-private launcher

Generate an owner-private task-local launcher directory and put it first in the
new tab's `PATH` using Herdr's supported `tab create --env` interface. The
launcher is named `claude`, because Herdr's `--kind claude` intentionally uses
the canonical executable name.

The launcher must not embed credentials or copy account files. It should invoke
a checkout-owned helper with only:

- opaque profile name;
- task-private proof path;
- launch nonce or capability token; and
- original argv as an array.

The helper revalidates the profile, sets `CLAUDE_CONFIG_DIR` in memory, exports
an opaque nonce/fingerprint for hook attestation, and `exec`s the exact certified
binary. The private config path appears only in the final process environment,
not in Herdr argv, task metadata, generated hook commands, or normal output.

The tab may also receive a non-sensitive task/profile marker for diagnostics,
but no-mistakes must not treat that marker as its own profile selection. Its AXI
run still needs an explicit no-mistakes selection.

### Fail-closed startup attestation

Extend generated Claude settings and capability proof so the first certified
`SessionStart` hook verifies:

- expected preallocated Claude UUID;
- effective role/task identity;
- launch nonce;
- selected profile fingerprint;
- inherited `CLAUDE_CONFIG_DIR` equals the currently validated profile root;
- expected certified executable proof; and
- owner-private proof/settings destinations.

The hook writes an atomic, owner-private startup acknowledgement containing no
path. Spawn waits for that acknowledgement after `herdr agent start` reports
interactive readiness and before `herdr agent prompt` delivers the task.

No acknowledgement, wrong nonce, wrong session, wrong profile, capability drift,
or timeout means `agent_start=failed`. Rozoro leaves the already-created tab for
inspection under its existing failure contract but sends no task prompt and
prints no private path.

This proof closes two current gaps: a Herdr login shell that rewrites `PATH`, and
an actual Claude executable that differs from caller-side `command -v`.

### Hooks and settings

- Continue using a task-local `--settings` overlay; never edit user or project
  Claude settings.
- Hook subprocesses inherit the selected Claude environment.
- Generated settings command text contains proof paths and opaque identifiers,
  not the account path.
- Capability proof/settings/ack files are regular, owner-owned, `0600`, written
  atomically in a `0700` task directory, with unpredictable temporary names.
- Existing background-work/event-bus semantics remain unchanged after startup
  attestation succeeds.

## Linking and durable exact resume

### Durable descriptor

New Claude links add a capability requirement and profile fields without storing
the path:

```json
{
  "requirements": ["claude-profile-v1"],
  "id": "<task-id>",
  "harness": "claude",
  "cwd": "<task-cwd>",
  "session_id": "<uuid>",
  "profile": {
    "harness": "claude",
    "model": "sonnet",
    "effort": "",
    "permission_mode": "auto",
    "fast": false,
    "claude_profile": "secondary-a",
    "claude_profile_fingerprint": "<non-path-digest>"
  }
}
```

The exact schema version may be coordinated with the capability-aware session
plan, but these invariants do not change:

- requirements are data, not shell text;
- profile name and fingerprint are durable;
- account path and secret contents are absent;
- unknown required capabilities fail closed;
- resume argv is reconstructed from validated fields, never evaluated text.

Write `session.json` atomically with mode `0600`; ensure its task directory is
mode `0700`. Existing descriptors remain readable without eager rewrites.

### Link algorithm

For a supported managed Claude launch, the preallocated UUID is authoritative.
After startup attestation:

1. Prefer validated Herdr `agent_session` metadata when available and matching.
2. Otherwise use the exact preallocated UUID under the selected profile's
   project store for the canonical cwd.
3. Confirm UUID/cwd/task marker where the format supplies them.
4. Never scan the primary store when a named profile is selected.
5. Fail on mismatch or ambiguity; never pick the newest transcript.
6. Do not print the selected store path in retry output.

This can share the safe identity helpers proposed by the capability-aware
session-linking plan, but it must not wait for a broad descriptor refactor if the
preallocated Claude UUID provides a smaller safe implementation.

### Lifecycle behavior

| Operation | Profile behavior |
| --- | --- |
| `start`/`spawn` | Resolve, validate, attest, and persist the selected profile. |
| `send` | Same live process; no new profile resolution. |
| `teardown`/reap | Remove live state only; preserve task/session/profile descriptor and never touch the Claude root. |
| `resume` | Re-resolve stored profile and exact UUID; mismatch fails; no cold fallback. |
| `restart` | Preserve profile and launch settings, create a new UUID/conversation, and refresh the link. |
| `--keep-tab` | No special account cleanup; existing process remains operator-owned. |

## Independent no-mistakes/AXI design

Everything in this section is proposed work in the **separate no-mistakes
project and release**, not Rozoro implementation scope.

### CLI and precedence

Add `--claude-profile <name>` to new-run entrypoints:

```text
no-mistakes axi run
no-mistakes rerun
```

Do not add arbitrary `--env` or a raw path flag.

Precedence is lifecycle-aware:

1. A reattached/recovered active run's persisted profile is authoritative.
2. An explicit flag selects the profile for a new run or terminal rerun.
3. An optional machine-only default may apply when no explicit selection is
   supplied, but is not the recommended default and must preserve old behavior
   when absent.
4. The initiating shell's `CLAUDE_CONFIG_DIR` and initiating harness are never a
   selection source.

Definitions alone do not mutate global defaults. A conflicting flag while AXI
is reattaching an active run returns a stable `profile_locked` error rather than
changing future children. A terminal `rerun --claude-profile <other>` creates a
new run with the new selection and does not reuse an old Claude session.

If the effective no-mistakes agent/fallback set contains no Claude adapter, an
explicit Claude profile is rejected as inapplicable rather than reported as
active.

### AXI protocol and daemon custody

Add an optional opaque `claude_profile` field to the AXI run/rerun IPC request.
The CLI sends the name over the owner-private socket; it never sends a resolved
path or executable. The daemon:

1. loads the global-only profile map;
2. resolves and validates the selected profile before run/worktree mutation;
3. persists name and non-path fingerprint in the run row;
4. constructs every Claude adapter from that persisted selection;
5. revalidates immediately before every child; and
6. reloads the persisted selection, not ambient daemon environment, after
   daemon restart or approval-gate recovery.

Status, logs, TOON, telemetry, PR updates, and errors may show a redacted profile
placeholder or opaque name according to privacy policy, never its path.

### Direct Claude subprocess and attestation

no-mistakes can execute the exact profile binary directly, so it does not need
Rozoro's Herdr launcher. Its Claude adapter should:

- select the profile executable ahead of generic `agent_path_override` for that
  per-run Claude adapter;
- append invocation-scoped `CLAUDE_CONFIG_DIR` to `cmd.Env` after inherited
  daemon values so it wins;
- generate a private per-invocation settings/nonce proof;
- pass a managed settings overlay that cannot be displaced by raw agent args;
- retain current project-setting neutralization semantics;
- require a certified SessionStart acknowledgement; and
- refuse the invocation if acknowledgement is absent or mismatched.

The managed settings flag becomes reserved in no-mistakes' Claude args while the
feature is active. Real capability work must certify that the overlay composes
correctly with Claude print mode, user settings, `--setting-sources user`, and
exact resume on each supported Claude version.

The acknowledgement proves the real direct child inherited the selected root.
A unit assertion that `cmd.Env` contains a value is necessary but not sufficient.

### Pipeline scope

Persisted selection must reach every no-mistakes-owned Claude invocation:

| Pipeline duty | Session/profile behavior |
| --- | --- |
| Intent inference/disambiguation, when it uses the pipeline agent | Selected profile, cold invocation. |
| Review and rereview | Selected profile, intentionally session-free. |
| Review fix | Selected profile; durable fixer session may resume only with matching profile fingerprint. |
| Test evidence and test repair | Selected profile, independently bounded invocation. |
| Document/lint housekeeping | Selected profile. |
| Rebase conflict repair and PR assistance | Selected profile. |
| CI monitor | No model process while only polling. |
| CI/merge-conflict repair after monitoring | Selected profile from the persisted run, including after daemon recovery. |

Extend durable fixer-session metadata from `(run, role, agent, session_id)` to
also bind the profile name/fingerprint. A profile mismatch is not a resumable
session. Recovery fails closed rather than dropping to an unprofiled Claude.

### Quota and fallback behavior

no-mistakes currently retries transient Claude failures and can try another
configured agent when a process appears unavailable. Profile support must make
error classes explicit:

- transient overload/network/rate-limit errors retain bounded retries under the
  same profile;
- hard account quota, billing, authentication, profile validation, attestation,
  and session/profile mismatch are semantic failures, not executable
  unavailability;
- those semantic failures never select another Claude profile or another
  provider automatically;
- error output is categorized and path-sanitized before logs/TOON; and
- pipeline custody and unpublished commits remain recoverable under existing
  terminal-run rules.

To use another account, the operator waits for a terminal outcome, follows AXI's
structured custody/sync instruction, and runs a new terminal rerun with another
explicit profile. The old fixer session is not resumed. An active run cannot
switch profile at an approval response.

## Primary and fallback account policy

The default recommendation is deliberately manual:

- **Primary:** no named profile, preserving current behavior.
- **Fallback:** an operator-defined named profile selected explicitly.

Do not encode an ordered account chain in a profile. Automatic quota failover
would make billing identity nondeterministic, could start a new conversation
under the wrong account, and cannot exactly resume a transcript that exists only
under another configuration root.

For Rozoro, switching after quota means starting a new task under the alternate
profile; the durable handoff remains the portable continuation mechanism. For
no-mistakes, switching means a new terminal rerun under the alternate profile,
with custody preserved but Claude session reuse reset.

## Threat model

### Assets

- Claude credentials and account identity.
- User/project Claude settings and hooks.
- Private transcript/session stores.
- Exact conversation identity.
- Selected executable and capability proof.
- no-mistakes pipeline custody and unpublished fixes.
- Privacy of local account paths and profile labels.

### Threats and controls

| Threat | Control |
| --- | --- |
| Dispatcher environment stops at a resident process | Explicit tab env/launcher for Herdr; explicit AXI IPC field for no-mistakes. |
| Wrong Claude binary runs after caller-side version check | Exact profile executable, shim/direct exec, inode proof, SessionStart acknowledgement. |
| Symlink or ownership attack redirects credentials | Non-symlink private config root/profile file, owner/mode checks, safe executable-chain resolution, revalidation. |
| Profile changes during an active session | Persist non-path fingerprint; refuse mismatch on resume/recovery. |
| Concurrent runs bleed accounts | Task/run-scoped environment and nonce; no global export or daemon mutation. |
| Malicious repository chooses an account | Definitions and defaults are global/local only; repo config cannot set them. |
| Raw env surface injects secrets or loaders | No arbitrary `--env`; closed profile schema only. |
| Private path appears in CLI/process logs | Do not pass config path through Herdr or AXI argv/IPC; redact known paths from child stderr and diagnostics. |
| Hook/settings generation overwrites user state | Explicit temporary overlay only; atomic owner-private task/run files; no user config edits. |
| Quota error silently uses another account/provider | Semantic error classification; no automatic profile/provider fallback. |
| Old reader ignores new profile fields | Required-capability floor before descriptors are written. |
| Public evidence leaks local state | Redaction checklist and tests; retain only placeholders, versions, UUIDs, fingerprints, and outcomes. |

The effective user is trusted to read their own profile definitions and process
environments. This design does not attempt to defend against the same user
intentionally replacing credentials or debugging their own child process. It
does defend against accidental ambient selection, repository-controlled config,
filesystem redirection by another local principal, and public artifact leakage.

## No secret copying or logging

Neither implementation may:

- copy credentials, OAuth state, settings, plugins, hooks, caches, or transcripts;
- serialize profile paths into task handoffs, identity files, PR bodies, issue
  comments, CI artifacts, test fixtures, or telemetry;
- print paths in normal `start`, `resume`, `doctor`, AXI, status, or quota errors;
- place the path in Herdr or AXI command arguments;
- include raw Claude stderr without replacing every known profile path;
- use a real account label in committed tests or examples; or
- publish raw hook/debug output from a live probe.

Owner-private local proof files may contain the minimum canonical path needed to
launch and verify a child. They are runtime capability state, never evidence.

## Compatibility and migration

### Existing Rozoro users

- No profile definition or flag produces current launch behavior and argv.
- Existing crew JSON remains valid.
- Existing safe task IDs, task folders, and descriptors remain readable.
- Legacy Claude descriptors resume under current default behavior unless the
  operator explicitly supplies a profile to fill missing context.
- Other harnesses do not inspect profile files or Claude stores.
- Rozoro never creates or rewrites personal profile/preset files.

### Descriptor rollback floor

Before profile-tagged descriptors exist, land a reader change that understands a
`requirements` array and refuses unknown required capabilities. Profile-aware
writers then include `claude-profile-v1`. Rolling back the writer/lifecycle code
to that reader floor remains fail-closed. Rolling back below the reader floor
while such descriptors exist is unsupported because current older readers may
ignore unknown profile fields and resume under the primary account.

### no-mistakes database compatibility

The separate project uses an additive migration for run profile name/fingerprint
and session binding. New runs without a profile store null and behave exactly as
before. Active profile-tagged runs require a profile-aware daemon; downgrade is
blocked or requires draining/terminating those runs first. A daemon restart must
not reconstruct profile selection from its environment or current global
default.

### No eager migration

Do not rewrite old task descriptors, crew presets, no-mistakes runs, global
settings, or account directories. New fields appear only when a named profile is
explicitly used or a legacy descriptor is explicitly upgraded.

## Proposed implementation surface

### Rozoro repository

Expected files for later implementation, not this plan PR:

- `bin/rzr-lib.sh`: profile name/schema/path/executable validation, fingerprint,
  launcher/proof/settings acknowledgement helpers, private writes.
- `bin/rzr-spawn.sh`: CLI/preset precedence, pre-mutation validation, Herdr tab
  environment, acknowledgement gate, durable live metadata.
- `bin/rzr-start.sh`: pass the explicit selector unchanged.
- `bin/rzr-link.sh`: selected-store/preallocated-UUID linking and private atomic
  descriptor writes.
- `bin/rzr-resume.sh`: stored-profile authority, matching assertion, launcher and
  attestation on exact UUID.
- `bin/rzr-control.sh`: preserve profile on restart.
- `bin/rzr-crew.sh`: display only profile name and validate the known field.
- `bin/rzr-doctor.sh`: profile-specific safe diagnostics without paths.
- `hooks/claude-rozoro-event.py`: certified startup acknowledgement without
  weakening existing lifecycle proof.
- lifecycle/fake/live tests and operator documentation.

Do not refactor unrelated harnesses, status v2, the event protocol, or teardown
policy merely to add this adapter field.

### Separate no-mistakes repository/release

Expected external work:

- global config schema/validation and docs;
- AXI run/rerun flags and IPC schema;
- run/session database migration and custody recovery;
- per-run agent construction and direct Claude environment;
- managed settings/SessionStart attestation;
- quota/fallback classification and sanitizer;
- status/TOON/doctor output;
- deterministic and opt-in live tests; and
- a released version before Rozoro documents the integration as available.

Rozoro must not vendor, patch, or manage the no-mistakes daemon as part of its
implementation.

## Automated test matrix

Tests must execute public behavior. A source grep is not proof that an env value,
launcher, prompt, hook, or daemon protocol works.

### Rozoro deterministic tests

| Area | Cases |
| --- | --- |
| Name/schema | Safe names, unsafe/traversal names, missing profile, malformed/unknown schema, wrong known-field types. |
| Paths | Quoted/unquoted `~`, absolute path, relative path, `~other`, missing dir, leaf symlink, wrong owner fixture, mode 0755/0777, mode 0700. |
| Executable | Safe npm/global symlink chain, unsafe writable chain, non-executable target, replaced inode, timeout, supported and unsupported version. |
| Precedence | Flag beats preset; preset beats unset; ambient env ignored; selector with non-Claude harness refused before mutation. |
| Herdr launch | `tab create` receives only non-secret shim/PATH markers; `agent start` remains canonical Claude; config path absent from fake Herdr log. |
| Attestation | Real fake process executes shim, receives env, runs hook, writes matching ack; missing/wrong nonce/profile/session/binary refuses prompt. |
| Linking | Named profile uses only selected store and preallocated UUID; primary store trap is not touched; mismatch/ambiguity fails. |
| Resume | Stored name wins; matching assertion passes; mismatch/missing/changed profile fails before tab creation; UUID is unchanged. |
| Reap/restart | Teardown preserves descriptor/profile; restart preserves profile but replaces UUID and refreshed link. |
| Concurrency | Two same-cwd crews with different profiles have distinct shims/nonces/stores and no cross-link. |
| Compatibility | No-profile Herdr argv and legacy descriptor behavior remain fixture-compatible; other harness paths do not read Claude profiles. |
| Privacy | Paths and sentinel secret strings absent from stdout, stderr, fake Herdr log, session/handoff/identity, generated settings commands, and failure output. |

### no-mistakes deterministic tests in the separate project

| Area | Cases |
| --- | --- |
| Config trust | Profiles accepted only globally; repository profile blocks ignored/rejected; unsafe files/paths/binaries fail. |
| AXI protocol | Explicit name reaches daemon over IPC; resolved path does not; active reattach conflict returns `profile_locked`. |
| Resident daemon | Daemon starts without ambient selector; two later concurrent runs choose different explicit profiles with no bleed. |
| Child proof | Fake Claude observes exact binary/env and emits a real SessionStart ack; env-only setup without ack fails. |
| Pipeline duties | Review, review-fix, test/evidence, document/lint, rebase/PR, and CI-fix all carry persisted selection. |
| Sessions | Fixer resume binds profile; daemon restart recovers it; mismatched profile never resumes or cold-falls to unprofiled Claude. |
| Custody | Terminal failure preserves unpublished head and structured sync/rerun guidance; new rerun may explicitly choose another profile. |
| Quota | Transient retry stays same profile; hard quota/auth do not retry another profile/provider; categorized output is sanitized. |
| Fallbacks | Missing executable may use configured agent fallback; account/profile semantic failures may not. |
| Privacy | Config path and fixture secrets absent from daemon log, step logs, TOON, telemetry, PR body, evidence, and errors. |
| Compatibility | Null profile gives byte-compatible Claude args/environment and current run recovery. |

Run both projects' complete deterministic suites, syntax/lint checks, link checks,
and `git diff --check`. Rozoro CI remains networkless and does not use real
credentials.

## Required real-process gates

Environment inheritance alone is unverified until these opt-in gates pass.
They may incur model cost and must never run in ordinary CI.

### G1 — real Herdr Claude fresh launch

Use real Herdr 0.8.2 and an isolated npm/global Claude executable whose version
is certified for Rozoro hooks.

1. Start Herdr before selecting the profile.
2. Launch a Claude crew by opaque profile name.
3. Verify task prompt is withheld until SessionStart acknowledgement.
4. Verify the actual process executable identity/version matches the proof.
5. Verify the transcript with the preallocated UUID appears only under the
   selected root.
6. Verify no new matching UUID appears under the primary root.
7. Record only redacted name, version, UUID, proof digest, and pass/fail facts.

### G2 — real exact resume and concurrency

1. Complete a turn containing a unique non-sensitive context marker.
2. Reap the task.
3. Resume without restating the profile and prove the marker remains in context.
4. Confirm the same UUID and profile acknowledgement in a new pane/incarnation.
5. In parallel, run a second profile in the same cwd and prove transcript/root
   isolation.
6. Restart one task and prove it keeps the profile but receives a new UUID.

### G3 — real no-mistakes resident daemon

This gate belongs to the separate no-mistakes release.

1. Start its daemon without the selected `CLAUDE_CONFIG_DIR`.
2. From a plain terminal or Pi-launched shell, start AXI with an explicit opaque
   Claude profile.
3. Prove a real review child and review-fix child acknowledge that profile.
4. Exercise document/housekeeping and a controlled CI-fix/monitor recovery path.
5. Park at a gate, restart the daemon, and prove subsequent fixer/CI child uses
   the persisted profile and exact eligible fixer session.
6. Confirm normal daemon/AXI output contains no account path.

### G4 — quota behavior

A deterministic fake is the required gate because intentionally consuming a
real account to exhaustion is inappropriate. If a naturally exhausted test
account is available, an optional local observation may confirm the sanitized
category, but no raw account response or path is retained. The required result
is no automatic account/provider switch and intact pipeline custody.

### Evidence handling

Raw hook/debug streams, environment dumps, process listings, account labels,
settings, and transcript content stay in an owner-private temporary directory
for local review and are deleted afterward. Committed evidence may contain only:

- redacted profile placeholders;
- supported versions;
- opaque task/run IDs and UUIDs;
- non-path proof fingerprints;
- expected lifecycle transitions; and
- pass/fail summaries.

## Documentation and operator UX

### Rozoro docs

Document:

- profile definition location and private mode requirements;
- placeholder-only examples;
- CLI/preset precedence;
- exact resume authority and mismatch behavior;
- restart versus resume;
- profile-specific doctor/check output;
- no automatic quota fallback;
- direct-child versus Herdr-resident environment behavior;
- cleanup (remove only the local definition after no descriptor needs it);
- privacy/redaction rules; and
- supported Claude/Herdr evidence.

Recommended operator flow:

```sh
# Definitions are created manually outside repositories and kept private.
./bin/rozoro doctor --claude-profile secondary-a
./bin/rozoro start task-name --body task.md --cwd /path/to/repo \
  --claude-profile secondary-a
./bin/rozoro teardown <task-id>
./bin/rozoro resume <task-id>
```

`doctor` prints the name, version, and safe/unsafe result, not resolved paths.
`crew list/show` prints only the opaque reference.

### no-mistakes docs in its separate release

Document:

- independent profile definitions and global-only trust boundary;
- `axi run`/`rerun --claude-profile`;
- why a Pi or Claude initiating shell does not select the pipeline agent;
- why a terminal env prefix does not retarget a resident daemon;
- active-run immutability, daemon recovery, fixer-session binding, and CI repair;
- hard quota behavior and terminal rerun switching;
- profile-path sanitization; and
- the minimum released no-mistakes version that provides these semantics.

Rozoro documentation may link to that released feature but must not claim it
exists before its release and live gate.

## Alternatives rejected

### Ambient `CLAUDE_CONFIG_DIR`

Works only across a real parent/child boundary. It caused the motivating failure
through both Herdr and resident AXI. It also cannot safely isolate concurrent
runs.

### Arbitrary Rozoro/no-mistakes environment injection

Too broad: it creates secret/logging and loader-injection surfaces unrelated to
Claude account selection. A closed named schema is smaller and auditable.

### Raw `--claude-config-dir <path>` in CLI or crew presets

It would spread private paths into shell history, Herdr argv, task metadata,
JSON presets, screenshots, and handoffs. Names provide reusable local indirection.

### Export globally or restart resident services under another account

Changes every future child, races existing tasks, prevents per-run concurrency,
and makes exact-resume identity depend on operator timing.

### Bypass `herdr agent start`

Typing `env ... claude` through a raw pane command loses Herdr's managed agent
name, readiness, foreground verification, and public session metadata.

### Trust caller-side `command -v claude`

The Herdr pane's login shell resolves the real executable independently. Profile
launcher plus startup acknowledgement proves the actual child.

### Shared Rozoro/no-mistakes profile registry

Creates an unnecessary cross-project runtime dependency, configuration owner
ambiguity, and release/version skew. Independent local maps with one opaque UX
contract are the minimal integration boundary.

### Copy credentials or transcripts into a shared root

Expands the security boundary, violates Claude ownership, and makes exact resume
ambiguous. Explicitly forbidden.

### Automatic account or provider failover

Makes billing identity nondeterministic and cannot preserve an exact transcript
across roots. Explicit terminal selection is safer.

## Five-PR implementation stack and merge order

This docs-only proposal PR is not one of the five implementation PRs.

### PR 1 — Rozoro descriptor requirements and rollback floor

Repository: Rozoro.

- Add/fixture required-capability parsing.
- Unknown requirements fail closed on resume.
- No profile writer or behavior change yet.
- Prove current descriptors remain compatible.

Merge first. This is the minimum rollback floor for later Rozoro work.

### PR 2 — no-mistakes profile config, AXI protocol, and custody

Repository: separate no-mistakes project.

- Global-only definitions and validation.
- Run/rerun flag and IPC field.
- Database migration and active-run profile immutability.
- Per-run adapter construction and session/profile binding.
- Daemon recovery and deterministic protocol/security tests.

Merge after its own review; no Rozoro code dependency.

### PR 3 — no-mistakes Claude attestation and quota semantics

Repository: separate no-mistakes project.

- Exact executable/environment and managed SessionStart proof.
- All pipeline-duty propagation.
- Sanitization and semantic quota/fallback classification.
- Real resident-daemon gates and documentation.
- Publish a no-mistakes release with a named minimum version.

Merge after PR 2.

### PR 4 — Rozoro profile launch and exact lifecycle

Repository: Rozoro.

- Resolver/security helpers and preset/CLI precedence.
- Task-private Herdr launcher and startup attestation.
- Selected-store link, descriptor fields, resume/restart/reap behavior.
- Deterministic and real Herdr tests.

May be developed after PR 1 while no-mistakes PRs proceed, but must not claim
cross-project availability.

### PR 5 — operator integration docs and redacted cross-tool evidence

Repository: Rozoro, with links to the released no-mistakes documentation.

- Final operator UX and troubleshooting.
- Direct-child/resident-worker explanation.
- Redacted G1-G3 evidence and supported-version table.
- Minimum no-mistakes release requirement.
- Final privacy and rollback audit.

Merge only after PR 3 is released and PR 4 passes its live gates.

Keep each PR reviewable, behavior-first, and independently revertible above the
compatibility floor. Do not mix unrelated session-linking, status, or event-bus
refactors into this stack.

## Acceptance criteria

### Rozoro

- A machine-local opaque profile name selects one private config root and one
  certified executable without putting either path in a repo or normal output.
- Explicit flag beats preset; preset beats unset; ambient env is ignored.
- Unsafe/missing profile state or unsupported executable fails before Herdr tab
  mutation where possible and always before task prompt delivery.
- Real Herdr launches the certified executable with the selected config env and
  a matching SessionStart acknowledgement.
- Hooks use the same profile and retain current lifecycle semantics.
- New Claude descriptors persist name/fingerprint/requirement but no account
  path, credential, or shell command.
- Exact resume uses the same UUID/profile and never cold-spawns or changes
  account; restart keeps profile and creates a new UUID.
- Link never scans the primary root for a named profile.
- Reap preserves durable resume data and never edits account state.
- Concurrent same-cwd crews under different profiles remain isolated.
- No-profile and non-Claude behavior remains compatible.
- Unknown required capabilities fail closed, enabling safe rollback to PR 1.

### no-mistakes separate release

- An AXI per-run profile is explicit IPC data, not inherited daemon env.
- A daemon started before selection launches every later Claude child with the
  persisted run profile.
- Review/fix/test/document/rebase/PR/CI-fix paths use the same selected profile.
- Fixer session identity is bound to profile and survives supported daemon
  recovery without drift.
- Conflicting active-run selection fails; a terminal rerun may select another
  profile without reusing the old session.
- Hard quota/auth/profile failures do not switch account/provider; transient
  retries remain bounded to the same profile.
- Paths are absent from logs, TOON, telemetry, PR text, and evidence.
- Null profile preserves current no-mistakes behavior.

### Delivery gates

- Full deterministic suites pass in both projects.
- Shell/Python/Go formatting, lint, docs links, and `git diff --check` pass.
- Required real Herdr and resident-daemon evidence passes on explicitly certified
  versions.
- Review confirms no secret copying, no global settings mutation, no arbitrary
  env surface, no source-grep proxy tests, and no public private-path leakage.
- Every implementation PR clearly identifies which acceptance items it closes.

## Rollback

1. Stop selecting profiles for new Rozoro tasks and no-mistakes runs.
2. Let live tasks finish or reap them; drain or terminate active profile-tagged
   no-mistakes runs using their normal custody protocol.
3. Preserve task folders, session descriptors, and no-mistakes recovery refs.
4. Roll no-mistakes back only to a version that understands profile-tagged run
   rows, unless all such active/recoverable runs have been drained.
5. Roll Rozoro lifecycle/writer changes back no further than PR 1 while any
   `claude-profile-v1` descriptor exists.
6. Do not rewrite descriptors to remove requirements, copy transcripts to the
   primary root, or silently resume them unprofiled.
7. Local profile definitions may remain unused; neither project deletes account
   roots or credentials.

A narrow operational disable is safer than downgrading to a reader that ignores
account identity.

## Explicit non-goals

- Implementing any code in this plan PR.
- Managing Claude accounts, credentials, login, billing, or quota balances.
- Automatic primary/fallback routing.
- Moving an exact conversation between configuration roots.
- Supporting arbitrary environment injection.
- Changing global Claude, Herdr, Rozoro, or no-mistakes defaults.
- Coupling Rozoro to the no-mistakes daemon/config database.
- Refactoring every harness into a generic account-profile abstraction.
- Changing status v2, handoff semantics, DATA/CONTROL behavior, or teardown
  repository policy.
- Publishing real account paths, labels, settings, transcript content, or raw
  process evidence.

## Handoff to implementation crews

Start every implementation PR from current `origin/master` in a worktree under
`./.worktrees/`. Read this plan completely and re-check the current implementation
before editing because the session descriptor and Claude capability code may
advance independently.

The Rozoro crew should begin with PR 1 and behavior tests, not launcher code.
The separate no-mistakes crew should treat its global config, AXI IPC, database,
daemon recovery, and adapter as one custody boundary and must not assume the
initiating shell or crew harness. Both crews must use placeholder profile names
and synthetic paths in committed tests.

Do not repeat the motivating mistake by accepting an argv fixture or inherited
environment assertion as proof. The feature is complete only when the actual
real Claude child and its SessionStart hook attest the selected profile through
Herdr and through an already-running no-mistakes daemon, with all retained
evidence redacted.
