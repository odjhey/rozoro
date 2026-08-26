# Claude watchtower live gate

Status: G3 evidence recorded for exact Claude Code 2.1.240

The host-installed Claude remains 2.1.241 and fails closed. G3 used an isolated
npm installation of `@anthropic-ai/claude-code@2.1.240`. The launch generator
executes that binary's `--version`, records its resolved path and device/inode in
an owner-private capability proof, and pins both paths as hook command arguments.
The hook accepts no capability environment assertion and rejects a changed
binary/proof identity.

Redacted evidence is in
`tests/fixtures/claude-watchtower-g3-2.1.240.json`. The cost-incurring native
probe observed a real native subagent in the authoritative non-empty Stop
snapshot followed by exactly one empty final Stop. Raw paths, prompts,
transcripts, commands, UUIDs, and model prose were deleted after review.

Four end-to-end scenarios used the real 2.1.240 Claude process, a real Herdr
0.8.2 pane, production hook/poller, and a real daemon/socket/SQLite store. They
proved:

- generations arriving after a quiescent Stop are observed by the resident
  same-driver/session poller;
- busy and waiting-background availability never polls/injects;
- the next certified quiescent state injects only
  `Rozoro notification pending; run ./bin/rozoro reconcile.` and confirms that
  exact generation only after Herdr succeeds;
- refusal/disconnect leaves the offer unconfirmed, and reconnect registers a new
  epoch for redelivery;
- a real authenticated 2.1.240 hook invocation while `rozorod` was down spooled
  both Stop events; daemon restart replayed two unique identities and restored
  quiescent state without duplicates.

The event-bus path is production authority after the G4/G5 cutover. `./bin/rozoro claude-watchtower` owns launch
and `--resume <session>` exact resume; optional `--preset <name>` selects a versioned resident configuration,
while `--wt-name <name>` supplies its label or labels an unpreset launch. With no preset, the ambient Claude
configuration is preserved. When a preset is selected, its bytes, version, and name are recorded in filesystem-only
registration metadata. The launcher validates the Herdr pane
after Claude is ready, retains a session-stable driver identity, and activates the existing legacy/event-bus
authority fence only after the poller proves registration readiness. Exact native resume creates a fresh
adapter incarnation under the same native session/driver: SessionEnd remains a
terminal fact for the old incarnation, while its `gone` state cannot poison the
new registration. Owner death closes the poller socket promptly. Production Pi
and supported-Claude default cutover is completed by PR #63 after this G3 gate.
