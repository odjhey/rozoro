# Claude watchtower live gate

Status: blocked closed by installed-version mismatch

PR 15 was developed against the merged, redacted Claude Code **2.1.240**
capability evidence in `docs/claude-hook-capability.md`. At validation time the
installed CLI reported **2.1.241**. The opt-in settings generator and hook retain
an exact `2.1.240` capability guard, so 2.1.241 cannot register availability or
actuate a wake by accident.

A temporary isolated capability probe was run on 2.1.241 to detect drift. It
observed the expected hook names, active then empty Stop snapshots, timeout, and
guarded Stop continuation, but that probe is not accepted as a replacement for
the reviewed 2.1.240 fixture. Its raw temporary output was deleted because it
contained local paths/model prose.

Consequently the four cost-incurring G3 scenarios were **not claimed passed** on
an unsupported version: native subagent waiting-background, final exactly-once
completion, busy watchtower deferred delivery, and daemon restart/spool replay
remain a mandatory review gate on an installed 2.1.240 binary (or after a
separate reviewed 2.1.241 capability fixture updates the certified guard).

Validated without live cutover:

- 192 Python tests, including watchtower identity and fail-closed actuator tests;
- the full 137-test container suite;
- exact fixed payload and delivery confirmation only after a successful Herdr
  prompt process;
- missing/malformed/non-empty background snapshots, continuation callbacks, a
  missing owned pane, timeout, and actuator refusal retain the pending offer;
- event-bus remains opt-in and legacy generation/delivery is fenced by existing
  one-owner authority markers.
