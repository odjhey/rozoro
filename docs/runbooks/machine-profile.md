# Watchtower machine profile

A Watchtower can manage more than one project and may run on machines with
different harnesses, accounts, model access, local limits, and no-mistakes
profiles. Put those **machine-local routing facts** in the optional text file:

```text
$ROZORO_HOME/config/machine.md
```

`ROZORO_HOME` defaults to `~/.rozoro`, so the normal path is:

```text
~/.rozoro/config/machine.md
```

This is a human/agent-readable preference file for now, not a stable Rozoro wire
format. No core command should depend on parsing a particular Markdown shape until
a versioned machine-config contract is deliberately introduced.

## What belongs here

Useful entries include:

- installed and usable harnesses;
- models/effort levels known to be available through each harness/profile;
- named account/config profiles and how to launch them;
- local capacity, cost, cooldown, or preference notes useful for routing;
- no-mistakes `NM_HOME` profiles and which account/harness environment they use;
- local binary/path requirements that differ between machines.

Keep credentials, tokens, passwords, and other secrets out of this file. Name the
environment variable, credential helper, or config directory rather than copying
the secret value.

## Example

```md
# Rozoro machine profile

## Harnesses

- `claude-primary`
  - harness: `claude`
  - status: available
  - config: default Claude config

- `claude-secondary`
  - harness: `claude`
  - status: available
  - launch environment: `CLAUDE_CONFIG_DIR=~/.claude-asdverse`

- `pi-luna`
  - harness: `pi`
  - status: available
  - model: `gpt-5.6-luna`
  - effort: high

## Preferences

- Among policy-authorized targets, prefer `pi-luna` when capacity is healthy.
- Treat these preferences as local routing input, never role authorization.
- Re-verify availability before each fresh selection.

## no-mistakes profiles

- `nm-primary`
  - `NM_HOME=~/.no-mistakes`
  - pipeline selection comes from that profile's `config.yaml`

- `nm-secondary`
  - `NM_HOME=~/.no-mistakes-secondary`
  - Claude identity requires `CLAUDE_CONFIG_DIR=~/.claude-asdverse` in the daemon's
    effective environment
  - verify before use with the installed no-mistakes health/config commands
```

The exact names are local conventions. The important property is that Watchtower
can understand what is available without encoding one machine's account layout in
repository policy.

## Resolution and freshness

Durable policy under `$ROZORO_HOME/watchtower-policies/` is crew assignment
authority; this profile is availability, capacity, and local preference evidence.
For a fresh crew, apply explicit operator and repository constraints, then the
role contract and all durable policy. Only then filter authorized candidates with
freshly verified machine/profile facts. Machine preferences may choose among
those candidates but cannot add one. A crew preset can realize an authorized
selection; it cannot authorize one.

Treat positive availability claims as stale unless verified for the current
selection. A dated operator prohibition does not expire with time. If a probe
contradicts an old machine fact, refresh that fact while continuing to enforce
independent prohibitions.

If an assigned harness, model, account, or profile is unavailable, use only an
ordered fallback explicitly authorized by durable policy or the current operator
instruction. Missing role policy, ambiguous or contradictory availability, and
unavailable assignments otherwise block; do not fall through to this profile, a
preset, or launcher defaults. No-mistakes target/fallback resolution remains
separate under its trusted repository/global configuration.

## no-mistakes specifics

Upstream no-mistakes global configuration lives at
`~/.no-mistakes/config.yaml`; `NM_HOME` selects a different config/state root.
Current global config supports an `agent` value or ordered fallback list, plus
`agent_config` for per-agent model/effort.

Prefer those native configuration mechanisms for no-mistakes pipeline routing.
Separate `NM_HOME` profiles are useful when the machine needs repeatable global
configurations for different account/harness setups.

`CLAUDE_CONFIG_DIR` belongs to the Claude harness environment rather than the
no-mistakes YAML schema. Normal no-mistakes gating uses a background daemon, so a
client-side invocation such as:

```bash
CLAUDE_CONFIG_DIR=... no-mistakes ...
```

is not by itself evidence that an already-running daemon will launch Claude with
that environment. If a no-mistakes profile depends on a Claude config directory,
document how that profile's daemon obtains it and verify the effective profile
before using it.

## Future contract

If Rozoro later needs machine-readable automatic target selection, introduce a
versioned config schema alongside this file or replace it deliberately. Until
then, `machine.md` is intentionally progressive disclosure for the Watchtower:
small, local, editable, and understandable without a migration layer.
