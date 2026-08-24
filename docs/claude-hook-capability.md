# Claude hook capability proof

Status: certified capability used by production event-bus wiring

## Tested target

The live probe ran against Claude Code **2.1.240** (the installed version on
2026-08-23). Planning observed 2.1.239; the patch release had advanced before
this proof ran. The committed fixture is therefore version-labelled rather than
claiming an unobserved 2.1.239 payload.

The probe supplied a temporary `--settings` file, `--setting-sources ''`, and
`--no-session-persistence`, so no user, project, or local settings were loaded
and Claude did not persist the probe sessions. It used `--debug hooks` and
`--include-hook-events --output-format=stream-json --verbose`. It did not edit,
load, or invoke the Herdr-managed user hook or user configuration. Prompts,
messages, paths, UUIDs, agent IDs, descriptions, and shell commands are redacted
in the fixture.

## Reproduce and inspect the evidence

Run the opt-in, cost-incurring probe from the repository root:

```sh
./tests/live/claude-hook-capability-probe.sh
```

The script writes three complete temporary settings files and hook programs,
then passes each settings path to Claude with standard setting sources disabled.
It reproduces (1) the background snapshot sequence, (2) a 3-second hook with a
1-second timeout, and (3) a guarded exit-2 Stop continuation. Raw hook/debug and
stream NDJSON stays in the printed temporary directory because it contains local
paths and model prose; inspect it there and delete it with the command printed by
the script. Every Claude invocation includes `--no-session-persistence`; the
probe neither loads nor writes user/project settings or persistent session
transcripts. Claude may still perform its normal non-session runtime/cache
activity, so this proof makes no broader claim that the CLI performs zero writes
anywhere under the user's home directory.

The reviewed, redacted result is committed in
`tests/fixtures/claude-hooks-2.1.240.json`. Its `outcome_evidence` object records
the three ordered Stop snapshots, timeout `hook_response`, both continuation
Stop responses, guard values, and final turn count. Tests bind the capability
claims below to those records and to the reproduction script's isolation flags.

## Observed payload contract

All configured command hooks receive one JSON object on stdin. Exact redacted
examples are in `tests/fixtures/claude-hooks-2.1.240.json`.

| Hook | Distinguishing fields observed |
| --- | --- |
| `SessionStart` | `session_id`, `transcript_path`, `cwd`, `source` (`startup`) |
| `UserPromptSubmit` | common identity, `permission_mode`, `prompt`, `prompt_id` |
| `SubagentStart` | common identity, `agent_id`, `agent_type`, `prompt_id` |
| `SubagentStop` | common identity, agent fields, `agent_transcript_path`, `stop_hook_active`, `last_assistant_message`, `background_tasks`, `session_crons`, `prompt_id` |
| `Stop` | common identity, `stop_hook_active`, `last_assistant_message`, `background_tasks`, `session_crons`, `prompt_id` |
| `SessionEnd` | common identity, `reason` (`other` in print-mode probe), and the latest `prompt_id` |

“Common identity” here means `session_id`, `transcript_path`, and `cwd` plus
`hook_event_name`. Fields are observations, not a promise that future versions
always supply them.

With hook event inclusion enabled, stream JSON emits paired `system` records:
`hook_started`, then `hook_response`. Responses identify `hook_name`,
`hook_event`, and `hook_id`; they report `exit_code`, `outcome`, `stdout`,
`stderr`, and `output`.

## Background-state finding and decision

`Stop.background_tasks` is an authoritative point-in-time snapshot exposed by
this installed build. A live native background-agent probe observed, in order:

1. `Stop` with the subagent still running;
2. a later `Stop` with only its shell task still running; and
3. a final `Stop` with `background_tasks: []`.

Entries expose opaque `id`, `type` (`subagent` or `shell`), `status`, and a
human description, with type-specific fields such as `agent_type` or `command`.
An adapter must retain only identity/type/status needed for lifecycle state, not
prompt, description, command, or assistant prose.

A `SubagentStop` callback can still contain that same agent as `running` in its
`background_tasks` snapshot. Therefore event name alone must not certify global
background clear. The adapter decision is:

- use start/stop edges for incremental bookkeeping;
- treat each present `Stop.background_tasks` array as the authoritative snapshot;
- `Stop` with a non-empty snapshot is `background=active`;
- only `Stop` with an explicitly present empty snapshot may certify
  `background=clear` for that instant; and
- if the field is absent, malformed, or capability drift is detected, publish
  `background=unknown` (never infer clear).

Print mode automatically delivered background completion notifications as
additional turns. Those turns produced additional `UserPromptSubmit` and `Stop`
hooks. Consumers must not assume one user CLI invocation means one prompt/stop
pair.

## Blocking, timeout, and Stop continuation

Command hooks are synchronous at their lifecycle boundary. A
`UserPromptSubmit` hook configured with timeout `1` and sleeping for 3 seconds
was cancelled after the configured second; stream output reported
`exit_code: 1`, `outcome: "cancelled"`, and the model turn proceeded. Thus hook
work delays the boundary until completion or timeout, but timeout is not a
reliable delivery acknowledgement and must fail conservatively/spool in future
adapter work.

A one-shot `Stop` hook exiting 2 with stderr
`Reply only STOP_CONTINUATION_CONFIRMED.` caused Claude to continue the same
session for another model turn. The next `Stop` payload had
`stop_hook_active: true`; allowing that callback to exit 0 prevented a loop.
The final print result was `STOP_CONTINUATION_CONFIRMED` with two turns.

So native Stop continuation is technically available, but it is **not the safe
default wake actuator**: it blocks settlement, incurs another model turn, and
requires a `stop_hook_active` loop guard. Future watchtower wiring may use it
only when a durable pending generation is already known and policy explicitly
selects native continuation; otherwise retain the pending generation for a safe
later actuator opportunity.
