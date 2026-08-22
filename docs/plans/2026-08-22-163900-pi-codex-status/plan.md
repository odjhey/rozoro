# Add focused Codex account status to Pi

Status: accepted implementation plan

Created: 2026-08-22 16:39:00 Asia/Manila

Scope: documentation-only plan for a future Pi extension

## Outcome

Rozoro's Pi environment gains a small, repository-owned status extension that
reports two facts for the active `openai-codex` provider:

- whether the serialized request asks for OpenAI's priority service tier; and
- the account's provider-reported rolling usage windows, including the weekly
  window when the account returns one.

The extension augments Pi's built-in footer with `ctx.ui.setStatus()`. It does
not replace the footer, estimate subscription quota from session tokens, scrape
the ChatGPT UI, or install the full `@shvax/pi-statusline` package.

The compact target display is:

```text
⚡ fast • wk 41% ↻4d6h
```

Only valid available fields render. Non-Codex models clear the status. “Fast”
means **priority requested in the effective outgoing payload**, not proof that
the provider ultimately served the request at that tier.

## Current-state and coordination evidence

- Pi 0.84.2 supports persistent extension statuses through
  `ctx.ui.setStatus(key, text)` and exposes serialized provider payloads in
  `before_provider_request` plus normalized HTTP headers in
  `after_provider_response`.
- Pi's built-in token and cost totals are session-local accounting. They do not
  expose ChatGPT account quota or a weekly allowance.
- Installed `@earendil-works/pi-ai` serializes OpenAI Responses
  `serviceTier` as `service_tier`, recognizes `priority`, and prices it, but Pi
  has no documented active-fast property for an extension to read.
- The installed Codex SSE path emits response headers to extensions. Its
  WebSocket path does not, so header-only quota reporting is incomplete.
- Rozoro master already persists and forwards `fast` for the native Codex
  harness. It intentionally rejects `fast:true` for Pi profiles today. This
  plan reports Pi's effective provider payload; it does not expand Rozoro's
  launch-profile policy or silently enable priority tier.
- The repository already owns a project-local Pi extension at
  `.pi/extensions/rozoro-watchtower.ts`. Keep Codex account status separate so
  provider/account concerns do not enter the crew lifecycle reducer.
- Open PR #38 changes the watchtower/status lifecycle protocol but does not add
  provider quota or fast-tier reporting. The future implementation should be
  rebased after it lands and must not couple account status to its task-status
  schema.
- Open PR #32 is a work-graph planning artifact and has no overlap.

## External reference and decision

`@shvax/pi-statusline` 0.9.1 is an MIT-licensed configurable replacement footer.
Its source demonstrates working Codex account usage retrieval and defensive
parsing:

1. resolve Pi's `openai-codex` OAuth access token;
2. decode the ChatGPT account id from the JWT claim
   `https://api.openai.com/auth.chatgpt_account_id`;
3. derive the trusted origin from the Codex model base URL;
4. call `GET /backend-api/wham/usage` with bearer token,
   `chatgpt-account-id`, and `originator: pi`;
5. parse `rate_limit.primary_window` and `secondary_window`; and
6. supplement polling with `x-codex-primary-*` and
   `x-codex-secondary-*` response headers.

The package does not implement service-tier detection. Its `⚡` denotes token
throughput, not fast mode. It also takes exclusive ownership of the footer and
does not render statuses installed independently through
`footerData.getExtensionStatuses()`.

Do not add `@shvax/pi-statusline` as a runtime dependency and do not import its
internal source paths. It has no stable narrow quota-library API, installation
auto-loads the full footer, and its settings, polling, rendering, and provider
features are disproportionate to this requirement.

Instead, create a small attributed in-house adaptation of only the relevant
Codex concepts. Also offer the focused parser/adapter or fast-segment work
upstream when practical, but do not block Rozoro's implementation on an
upstream review or release.

## Proposed layout

Add a directory extension so logic remains independently testable:

```text
.pi/extensions/codex-status/
  index.ts              # Pi lifecycle, provider correlation, status rendering
  codex-usage.ts        # trusted fetch, JWT account lookup, payload parser
  codex-headers.ts      # Codex response-header parser and merge rules
  cache.ts              # validated quota-only cache and TTL
  format.ts             # duration/reset/status formatting
  LICENSE.pi-statusline # retained MIT notice for adapted portions

tests/pi-codex-status/
  codex-usage.test.ts
  codex-headers.test.ts
  cache.test.ts
  extension.test.ts
```

If the repository's test runner cannot execute TypeScript extension tests
directly at implementation time, add the smallest explicit runner/configuration
needed. Do not test behavior by grepping implementation source. Exercise parser,
fetch, cache, lifecycle, and rendered-status interfaces.

Expected production size is roughly 180–300 lines. Do not copy the upstream
662-line extension entrypoint, provider settings app, custom renderer, Git and
throughput code, or multi-provider coordinator.

## Data model and parsing

Use one internal normalized type:

```ts
interface CodexUsageWindow {
  key: "primary" | "secondary";
  label: string;
  used: number;       // fraction in [0, 1]
  resetAt?: number;   // epoch milliseconds
}

interface CodexUsageSnapshot {
  windows: CodexUsageWindow[];
  observedAt: number;
  source: "endpoint" | "headers" | "cache";
}
```

### Account endpoint

For an available `openai-codex` model:

1. Resolve the access token with Pi's model registry. Do not read auth files
   directly.
2. Decode only the JWT payload needed for the ChatGPT account id. Treat malformed
   base64, JSON, claim shape, and missing ids as unavailable.
3. Validate the model/provider and destination before attaching credentials.
   The token must never be sent merely because an arbitrary custom model labels
   itself `openai-codex`. Restrict origins to the known Codex/ChatGPT hosts Pi
   registers, or compare against Pi's trusted effective provider configuration.
4. Fetch `${origin}/backend-api/wham/usage` with a 3-second timeout,
   `Authorization: Bearer`, `chatgpt-account-id`, and `originator: pi`.
5. Require an OK response and bounded JSON. Parse no unrelated account fields.
6. Parse only `rate_limit.primary_window` and `secondary_window`. Require finite
   `used_percent` in 0–100 and positive finite `limit_window_seconds`.
7. Derive labels from actual duration: 10,080 minutes is `wk`; otherwise use an
   honest compact duration such as `5h`, `2d`, or `90m`. Never assume that the
   secondary window is weekly.
8. Accept reset epochs in seconds or milliseconds and normalize to milliseconds.
   Missing reset data is valid and simply omits the countdown.

`/backend-api/wham/usage` and the JWT claim are private ChatGPT contracts. Keep
the adapter isolated and fail closed when either changes.

### Response headers

Normalize header names to lower case and recognize:

```text
x-codex-primary-used-percent
x-codex-primary-window-minutes
x-codex-primary-reset-at
x-codex-secondary-used-percent
x-codex-secondary-window-minutes
x-codex-secondary-reset-at
```

Apply the same range, duration, and reset validation as endpoint data. Ignore a
zero-percent placeholder that has neither duration nor reset. A response with
no quota headers must not erase a good endpoint or cache snapshot.

Headers are opportunistic freshness, not the only source. Direct fetching is
required because successful WebSocket requests may produce no
`after_provider_response` event in the installed provider implementation.

### Fast-tier detection

Register `before_provider_request`, safely narrow its unknown payload, and set
`fastRequested` only when all of these are true:

- the current model provider is `openai-codex`;
- the payload is an object; and
- `payload.service_tier === "priority"`.

`default`, `auto`, `flex`, missing, malformed, or another provider all mean no
fast indicator. Reset fast state on session start and model selection until a
new effective request is serialized. Do not infer fast mode from model name,
reasoning effort, Rozoro metadata, cost, or the presence of a lightning icon.

The extension is reporting only. A separate future plan is required before Pi
profiles can set `fast:true` or the extension can mutate provider payloads.

## Refresh, cache, and lifecycle

Use event-driven refresh rather than a permanent 10-second poll:

- load a fresh validated cache at `session_start`;
- fetch at Codex session start and Codex model selection;
- refresh after `agent_settled` or `turn_end`, subject to a 60-second TTL;
- parse headers whenever `after_provider_response` provides them; and
- stop/abort outstanding work at `session_shutdown`.

Maintain one in-flight fetch promise per process. Use a session epoch or abort
controller so a late request cannot update a replaced session or newly selected
provider.

Persist only normalized windows, schema version, and observation time beneath a
status-specific directory. Never persist a bearer token, JWT, account id, raw
headers, response bodies, or provider errors. Validate every read, cap maximum
age at five minutes, reject future timestamps, use a `0700` directory and
`0600` file, and write with temporary file plus atomic rename.

Initially avoid `proper-lockfile`: it is the only runtime dependency required by
pi-statusline's exact cross-process cache implementation, and adding package
installation for a rare race is not justified. A 60-second shared cache TTL,
atomic writes, and process-local coalescing may permit an occasional duplicate
fetch across concurrent Pi processes but cannot corrupt the cache. Add
cross-process locking and persisted 429 backoff only if testing or telemetry
shows amplification. Any later lock must recover stale owners and remain safe
across crashes.

On 401/403, discard no credential and expose no detail; hide usage and allow Pi's
normal auth flow to own recovery. On 429, network failure, timeout, malformed
JSON, or schema drift, retain a still-fresh prior snapshot, back off until the
next TTL opportunity, and render nothing once stale.

## UX

Use one atomic status key such as `codex-account`:

- `⚡ fast • wk 41% ↻4d6h`
- `wk 41% ↻4d6h`
- `⚡ fast` when usage is unavailable
- no status for non-Codex providers

Prefer percent **used**, matching provider data. Use the active theme: accent
for fast, warning at 80% or greater, error at 95% or greater, and dim reset
text. Sanitize to one line. Keep text compact because Pi sorts all extension
statuses onto one footer row and truncates at terminal width.

Do not display `fast off` or `usage unavailable` continuously. Add an optional
`/codex-status` diagnostic command only if implementation/manual testing needs
it. Diagnostics may show source, age, recognized window labels, and a sanitized
failure category; they must never show token, account id, destination headers,
or raw provider response.

## Security boundaries

1. **Credential destination is the primary boundary.** Verify the active
   provider and trusted OpenAI/ChatGPT origin before adding the bearer token. A
   custom base URL must not receive an OAuth token merely by claiming the
   `openai-codex` provider id.
2. **Secrets are memory-only.** Never log or persist token, JWT, account id,
   request headers, raw body, or thrown fetch objects that may contain them.
3. **Cache is advisory private state.** Store only normalized quota and time,
   enforce restrictive permissions, validate ownership/symlinks where feasible,
   and tolerate deletion/corruption.
4. **Network work is bounded.** Three-second timeout, bounded body, TTL,
   in-flight coalescing, and failure backoff prevent a footer feature from
   blocking Pi or amplifying provider load.
5. **Private API failure is non-fatal.** Missing quota never blocks a model
   request or Pi startup.
6. **Requested is not effective.** The status must not claim provider acceptance
   of priority tier because Pi does not expose the response's effective
   `service_tier` field.

## MIT provenance and attribution

`@shvax/pi-statusline` 0.9.1 is MIT licensed:

```text
Copyright (c) 2026 Martin Tahli
```

MIT permits use, modification, and redistribution but requires the copyright
and permission notice in copies or substantial portions. If parser, fetch, or
cache code is copied or closely adapted:

- ship the complete upstream MIT text as
  `.pi/extensions/codex-status/LICENSE.pi-statusline` or in the repository's
  established third-party notices location;
- annotate adapted modules with
  `Adapted from @shvax/pi-statusline 0.9.1, commit 17813caf..., MIT`;
- preserve the notice in any packaged redistribution; and
- document local changes and the private endpoint dependency.

Even if implementation rewrites generic mechanics, retain attribution because
the endpoint, headers, claim, and schemas were learned from that source. Confirm
the repository's third-party notice policy during implementation. This plan is
an engineering record, not legal advice.

## Implementation phases

### Phase 1: pure contracts and fixtures

- Add normalized types and strict endpoint/header parsers.
- Add duration/reset/status formatting.
- Add sanitized fixtures representing valid, partial, malformed, and changed
  provider responses. Fixtures must contain no live account data.
- Add unit tests before network/lifecycle integration.

### Phase 2: secure adapter and cache

- Resolve Pi-managed auth and verify trusted destination.
- Implement bounded endpoint fetch and sanitized failures.
- Add validated, permission-restricted, atomic TTL cache and in-process request
  coalescing.
- Test with mocked fetch/filesystem boundaries; no live provider call in CI.

### Phase 3: Pi lifecycle and status

- Register provider/model/session/request/response/settled hooks.
- Implement session epoch/abort cleanup and merge freshness rules.
- Detect priority from the effective serialized payload.
- Render and clear a single status without replacing Pi's footer.

### Phase 4: manual verification and documentation

- Test OAuth Codex under SSE and default/WebSocket transports.
- Compare normalized values with the ChatGPT usage page without recording
  secrets.
- Test concurrent Pi processes, model switches, `/reload`, offline startup,
  revoked auth, timeout, and stale cache.
- Document feature semantics, private-API limitation, cache location/removal,
  and requested-versus-effective fast wording.
- Consider offering the isolated adapter/parser and fast detection upstream.

## Automated test plan

### Parsing and formatting

- Valid one- and two-window endpoint payloads.
- Weekly and non-weekly duration-derived labels.
- Missing reset, epoch seconds, epoch milliseconds, expired reset.
- Missing fields, wrong types, NaN, infinity, negative, over-100 usage, zero or
  invalid duration, and schema drift all fail closed.
- Mixed-case valid headers, malformed headers, zero placeholders, and responses
  without quota headers.
- Compact formatting, warning/error thresholds, reset countdown, one-line
  sanitization, and omission of unavailable fields.

### Auth and fetch

- Valid account claim and malformed JWT/base64/JSON/missing claim.
- Known trusted origin succeeds; untrusted/custom origin receives no token and
  no request.
- Missing model/base URL/token/account id.
- Timeout, abort, 401, 403, 429, 5xx, oversized/malformed JSON.
- Assertions prove secrets are absent from logs, errors, status, and cache.

### Cache and merge

- Valid fresh cache, stale cache, corrupt JSON, invalid windows, future time,
  unreadable path, symlink/permission handling, and interrupted atomic write.
- Concurrent calls share one process-local request.
- Header snapshot refreshes endpoint/cache data only when valid; headerless
  WebSocket flow preserves good fetched data.
- Failed refresh retains only a still-fresh snapshot.

### Extension behavior

Use a fake Pi extension API/UI and mocked model registry/fetch:

- handlers register and non-Codex providers perform no auth/fetch/status work;
- session start/model select fetch and clear correctly;
- late async completion after session replacement is ignored;
- `priority` displays fast while default/missing/malformed payload does not;
- model switch clears stale priority until the next request;
- only one status key is updated atomically and output is sanitized;
- shutdown aborts work and leaves no timer or handle.

Do not add source-grep tests. Assert public parser outputs, fetch calls,
filesystem records, registered handler behavior, and rendered UI status.

## Manual validation

Before shipping the future implementation:

1. Run repository tests and TypeScript/type checks from a clean worktree.
2. Start Pi with OAuth `openai-codex`, verify initial quota appears from endpoint
   polling before an HTTP response header is observed, and compare values with
   the account usage UI.
3. Exercise SSE and WebSocket/default transport; quota must remain available in
   both.
4. Capture only recognized field/header **names** and normalized synthetic
   values in evidence—never credentials or raw account payloads.
5. Verify a real serialized priority request shows `fast`, while default does
   not. Record the wording as requested, not provider-confirmed.
6. Open concurrent Pi sessions and confirm cache remains valid and request rate
   stays bounded.
7. Switch away from Codex, reload, revoke auth, disconnect network, corrupt the
   cache, and confirm Pi remains usable with no misleading stale status.
8. Inspect cache permissions and contents to prove no secret/account identifier
   is stored.

## Risks and mitigations

| Risk | Mitigation |
| --- | --- |
| Private endpoint, JWT claim, or schema changes | Isolate adapter, strict parser, synthetic fixtures, fail closed, document provenance, periodically compare upstream |
| OAuth token sent to a malicious custom base URL | Provider plus trusted-origin validation before attaching credentials; test that rejected origins receive no fetch |
| Tokens/account data leak through logs or cache | Store normalized windows only; sanitize failures; secret-absence tests; restrictive permissions |
| Concurrent Rozoro sessions amplify polling | 60-second TTL, shared cache, in-process coalescing, bounded lifecycle refresh; add lock/backoff only on evidence |
| Stale async fetch updates another session/model | Session epoch and abort controller; provider check before commit/render |
| Priority requested but not honored | Derive only from effective outgoing payload and document “requested”; do not claim served tier |
| Pi extension API changes | Keep Pi calls in `index.ts`, pin/test supported Pi version, prefer typed public APIs |
| Copied code misses upstream fixes | Record package version/commit, keep copied surface small, assign periodic provenance/security review |
| Footer/status extension conflict | Use `setStatus`, one namespaced key, never call `setFooter` |
| Added lock dependency increases supply-chain surface | Start with Node built-ins; add `proper-lockfile` only after demonstrated cross-process need |

## Explicit non-goals

- Installing or wrapping the complete `@shvax/pi-statusline` footer.
- Replacing Pi's built-in footer or rendering provider-tracking rows.
- Anthropic, Z.AI, OpenRouter, API organization billing, throughput, Git, time,
  context, model, or effort status.
- Enabling/toggling priority tier, changing Rozoro's Pi profile validation, or
  mutating outgoing provider requests.
- Estimating plan quota from session tokens/cost.
- Scraping ChatGPT HTML.
- Treating the private endpoint as a stable public contract.
- Adding a third-party lock dependency before evidence requires it.

## Acceptance criteria

- A future implementation is a focused repository-owned Pi extension and does
  not load or depend on the full `@shvax/pi-statusline` package.
- It uses `ctx.ui.setStatus()` and leaves Pi's built-in/custom footer ownership
  untouched.
- Valid Codex account windows come from the authenticated account endpoint,
  supplemented by response headers, and labels derive from reported duration.
- Weekly usage works without requiring SSE response headers.
- Fast appears only for an effective outgoing Codex payload with
  `service_tier: "priority"` and is documented as requested, not guaranteed.
- Non-Codex providers neither receive OAuth credentials nor show stale Codex
  state.
- Untrusted origins never receive the bearer token.
- Cache and UI contain no token, JWT, account id, raw header, raw response, or
  unsanitized provider error.
- Network/cache failures and private API drift never block Pi or model calls.
- Adapted upstream code carries the complete MIT notice and source provenance.
- Automated tests cover strict parsing, trusted destination, secret absence,
  cache freshness/corruption, lifecycle races, fast detection, and observable
  status behavior without source-grep assertions or live provider calls.
- Manual evidence covers OAuth, SSE/WebSocket, concurrency, stale/offline/auth
  failure, permissions, and requested-tier semantics.
