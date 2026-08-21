rozoro-task: {{ID}}
task-folder: {{FOLDER}}

{{BODY}}

---
## Handoff protocol — follow before ending EVERY turn

Your task folder is {{FOLDER}}. Before you end any turn — whether the task is
finished OR you are pausing for my input — APPEND (never overwrite, never edit an
earlier block) one block to {{FOLDER}}/handoff.md:

  ## turn <n> — <short what-happened>
  verdict:       done | needs-action | failed | blocked
  reason:        <one line; required unless verdict is done>
  did:           <what you changed / verified this turn>
  pending:       <what is left, or "none">
  inputs-needed: <the exact question you need me to answer, or "none">
  artifacts:     <branch / PR # / commit sha / file paths, or "none">

Rules:
- Append-only. Each turn adds a new block; the file is the full history of this
  task, so a future session (or I) can resume from it alone.
- `verdict` is how I tell "done" from "needs-action" — set it honestly every turn.
- If you background a long command and your turn ends before it finishes, do NOT
  write verdict: done — use needs-action (or keep working) so I know to wait.
- Never delete or rewrite the handoff. It is the durable record of this task.
