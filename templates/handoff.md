## Handoff protocol — follow before ending EVERY turn

You are a rozoro crew working task `{{ID}}`. Your task folder is {{FOLDER}}.

Before you end any turn — whether the task is finished OR you are pausing for my
input — APPEND (never overwrite, never edit an earlier block) one block to
{{FOLDER}}/handoff.md:

  ## turn <n> — <short what-happened>
  verdict:       done | waiting | needs-action | failed | blocked
  reason:        <one line; required unless verdict is done>
  did:           <what you changed / verified this turn>
  pending:       <what is left, or "none">
  inputs-needed: <the exact question you need me to answer, or "none">
  artifacts:     <branch / PR # / commit sha / file paths, or "none">
  heads:         <for delivery turns: reviewed=<sha> pushed=<sha> ci=<sha>
                 merged=<sha>, or "n/a"; if any differ, say why on this line>

Rules:
- Append-only. Each turn adds a new block; the file is the full history of this
  task, so a future session (or I) can resume from it alone.
- `verdict` is how I tell completion, waiting, and action requests apart.
- Use `waiting` only while harness-owned background work is active, with useful
  reason/pending text and `inputs-needed: none`; report again after consuming it.
- If background capability is unavailable, `waiting` is unverified and actionable.
- `heads` is required whenever the turn reviewed, pushed, ran CI on, or merged
  a candidate; a chain with an unexplained mismatch is not delivery evidence.
- When a block mentions review/gate findings, give each a stable id and mark it
  `open` or `resolved(<how>)`. A finding never mentioned again is ambiguous;
  the last block naming it is authoritative.
- Never delete or rewrite the handoff. It is the durable record of this task.
- This applies to resumed turns too: after answering a follow-up, still append a
  fresh block before you stop.
