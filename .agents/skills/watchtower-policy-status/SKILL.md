---
name: watchtower-policy-status
description: Explain the current applicable Watchtower policies and rules. Use when the operator asks “what are the current Watchtower policies?”, “what rules are you following?”, “what is your current policy?”, or asks which Watchtower instructions apply now.
---

# Watchtower policy status

Answer from the current applicable sources; do not reconstruct policy from memory.

1. Read the active Watchtower policy supplied by the current harness. In this checkout, verify harness coverage before treating `templates/watchtower.md` as active; `watchtower-policy-snapshot` documents and can capture that source for Pi.
2. Read applicable repository instructions for the current target checkout, plus explicit operator instructions. Read machine-local routing policy only when it exists and is relevant.
3. Summarize the rules that answer the question and identify their source and scope. If sources conflict, follow their actual precedence and call out the conflict rather than blending them.
4. Distinguish **explicit policy** from **runtime/project state**. Branches, task verdicts, `/afk` state, active crews, assurance results, and provider status are observations or state, not policy text. Verify them separately when requested.
5. State unknown or uncovered harness policy conservatively. Do not claim that a repository file applies to a harness merely because the file exists.

Keep the answer practical and concise. Use `watchtower-policy-snapshot` only when the operator asks to persist, archive, or compare an immutable policy record; ordinary policy questions do not require creating an artifact.
