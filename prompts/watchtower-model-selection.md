# Retrieve Watchtower model-selection policy

**Execution owner: Watchtower.** This prompt is for orchestration/routing. Do not
pass it to a crew member as that crew's operating instructions.

Use this prompt when you need the current Watchtower role/model-selection criteria without relying on memory or copying policy into another skill.

Read `templates/watchtower-crew-dispatch-guidelines.md` from the current checkout. Treat that file as the source of truth for role assignment, model IDs, reasoning effort, and no-mistakes execution-target fallback policy.

Return a compact table with these columns:

- role;
- when to use it;
- canonical model ID;
- reasoning effort;
- important routing constraints.

Then report separately:

1. the current no-mistakes execution-target fallback order, including any configuration/custody requirements;
2. the criteria for escalating from coder/reviewer/tester loops to the replanner;
3. any distinction between harness/profile/target names, model IDs, and reasoning effort that callers must preserve.

Rules:

- Read the file before answering. Do not answer from remembered defaults.
- Use canonical model IDs exactly as written. Do not invent shorthand model names.
- Do not reinterpret this prompt as policy. If this prompt and the dispatch guidelines differ, the dispatch guidelines win.
- Do not copy model-selection rules into a crew skill as a second authority.
- If asked to choose a model for a specific task, first identify the appropriate Watchtower role from the task shape, then apply that role's current model/effort entry from the dispatch guidelines.
- If the source file is missing, ambiguous, or internally inconsistent, report that instead of guessing.
