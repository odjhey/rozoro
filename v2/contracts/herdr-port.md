---
name: v2_contract_herdr_port
description: "The outbound port to Herdr: consumed commands, response tolerance, the event subscription stream, and what Rozoro deliberately does not trust Herdr for."
type: contract
tags: [architecture, contracts, ports, herdr]
status: v2-draft
generated: "Claude Fable 5, 2026-08-28"
created_at: 2026-08-28T00:00:00+08:00
---

> **v2 working copy** — forked from [`docs/architecture/contracts/herdr-port.md`](../../docs/architecture/contracts/herdr-port.md) at `b044dbe`. Iterate here; the v2 effort never edits the live architecture docs.

# Herdr port

Part of the [contracts index](./README.md). Herdr (0.8.x) is the terminal-hosting backend. Rozoro consumes it as an **outbound port with five facets** — and deliberately refuses to treat it as semantic truth (ADR-0002: Herdr is host abstraction only; harness-native lifecycle evidence is the authority).

## Facets consumed

1. **Session/socket directory** — `herdr session list --json` → socket paths; `RZR_SESSION` selects a named session.
2. **Tab/pane creation** — `herdr tab create --cwd <dir> --label <text> --no-focus --env "ROZORO_HOME=<home>" [--workspace <ws>]`. The `--env` on tab create is the **only** injection point for the crew's home, because Herdr's server forks the pane process and `agent start` has no `--env`.
3. **Agent oracle** — `herdr agent get <pane>` → `agent_status` (`idle|working|done|blocked|unknown`, plus derived `shell`/`gone`), `interactive_ready`, `state_change_seq`, and native session identity (`agent_session.{kind, source, value}`).
4. **Actuator** — `agent start <name> --kind <harness> --pane <pane> -- <args…>`, `agent prompt <pane> <text> [--wait]`, `agent send-keys <pane> <key>`, `agent wait <pane> --timeout … --until …`, `tab close <tab>`. Error vocabulary handled: `agent_pane_busy` (retried with backoff), `agent_not_ready` (readiness polled, never re-started), `invalid_agent_name`.
5. **Name registry** — agent names are 1–32 chars of `[a-z0-9_-]`; Rozoro derives `rzr-<sha256(task_key)[:28]>` to fit.

All calls funnel through one wrapper that prepends `--session`; response parsing is deliberately shape-tolerant (`//`-chained jq fallbacks) because upstream JSON shapes are not a stable contract. `pane.get` is treated as unreliable (the test fake stubs it as always-failing; the daemon uses it only as a fallback to distinguish absence from uncertainty).

## Event subscription stream

Push-based edges over the control socket (verified against Herdr 0.8.2, protocol 16+):

```json
→ {"id": "...", "method": "events.subscribe",
   "params": {"subscriptions": [{"type": "pane.agent_status_changed", "pane_id": "wX:pN"}, …]}}
← {"result": {"type": "subscription_started"}}
← {"event": "pane.agent_status_changed", "data": {"pane_id", "workspace_id", "agent_status", "agent", "state_change_seq", …}}
```

- Herdr rejects a whole multi-pane subscription if any pane is gone; the daemon falls back to **per-pane sharding** with a merge queue so stale metadata cannot suppress live panes.
- The standalone subscriber (`herdr-eventwait`) emits `@subscribed` then TSV lines, with a distinct exit code per failure mode (`2` transport, `3` bad ack, `4` stream closed, `0` clean timeout/stdout-closed). Push edges replaced a level-triggered wait loop: "a push edge is a real edge; there is nothing to spin."
- Subscribe-before-levels ordering: after subscribing, a synchronized level snapshot reconciles current state; a stale in-flight level read loses to a post-subscribe event (tested).

## What Rozoro refuses to trust Herdr for

- **Semantic completion**: Herdr `idle` ≠ quiescent. Terminal liveness is hosting truth, never task truth.
- **Background activity**: current Herdr has no background capability; `waiting` verdicts cannot be certified from Herdr evidence alone.
- **Event ordering across domains**: `state_change_seq` orders Herdr edges only; it never seeds the protocol's `producer_seq`.
- **Instructions**: pane/agent/event data must never become prompt content injected into a resident driver (the wake message is fixed and content-free).
