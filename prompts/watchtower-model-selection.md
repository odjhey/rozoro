# Retrieve Watchtower model-selection policy

**Execution owner: Watchtower.** This prompt is for orchestration/routing. Do not
put it in a crew brief as that crew's operating instructions.

Use this prompt when you need the current Watchtower role/model-selection criteria without relying on memory or copying policy into another skill.

Read `templates/watchtower-crew-dispatch-guidelines.md` from the current checkout. Treat that file as the source of truth for **standard crew** role assignment, model IDs, reasoning effort, and current no-mistakes execution-target fallback policy.

Then read `.agents/skills/quick-crew-routing/SKILL.md` only to decide whether the task qualifies for the bounded Quick Crew fast path. Quick Crew does not replace or rewrite the standard model map.

Return a compact table with these columns:

- role;
- when to use it;
- canonical model ID;
- reasoning effort;
- important routing constraints;
- crew-facing briefing source, when one exists.

Then report separately:

1. whether the task qualifies for Quick Crew and why; if so, Quick Scout or Quick Coder uses `gpt-5.3-codex-spark` low;
2. the current standard no-mistakes execution-target fallback order, including any configuration/custody requirements;
3. the criteria for escalating from coder/reviewer/tester loops to the replanner;
4. any distinction between harness/profile/target names, model IDs, and reasoning effort that callers must preserve;
5. whether each selected role is Watchtower-owned work or requires dispatch to crew.

Rules:

- Read the canonical files before answering. Do not answer from remembered defaults.
- Current standard role/model/effort selection wins over older snapshots or machine-local policy copies.
- Current no-mistakes target/fallback policy wins over older snapshots or machine-local policy copies.
- Use canonical model IDs exactly as written. Do not invent shorthand model names.
- Do not reinterpret this prompt as policy. If it differs from the canonical dispatch guidelines, the dispatch guidelines win.
- Do not copy standard model-selection rules into crew skills as a second authority.
- If asked to choose a model for a specific task, first check Quick Crew eligibility. If the task does not qualify, identify the appropriate standard Watchtower role and apply that role's current model/effort entry from the dispatch guidelines.
- For a crew-facing role, tell the Watchtower which briefing source to read and incorporate into the crew brief. Rozoro does not currently pass skill objects/references into crew sessions.
- Do not infer a global Pi-harness rule from older machine-specific policy.
- If a canonical source is missing, ambiguous, or internally inconsistent, report that instead of guessing.
