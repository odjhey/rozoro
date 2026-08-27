---
name: watchtower-policy-status
description: Explain current applicable Watchtower policies and rules with verified source scope. Use when the operator asks “what are the current Watchtower policies?”, “what rules are you following?”, “what is your current policy?”, or which Watchtower instructions apply now. Route archive or comparison requests to watchtower-policy-snapshot and /afk state questions to afk.
---

# Watchtower policy status

Verify activation before reading or summarizing a candidate policy body; do not reconstruct policy from memory.

1. Establish current-process activation evidence first. The Pi launch policy is composed from the `templates/watchtower.md` core plus exactly one mission policy (shipped `templates/missions/<name>.md` or operator `$ROZORO_HOME/watchtower-missions/<name>.md`; ADR-0013). Call either file active only when the current invocation has verified Watchtower-launcher or system-prompt injection evidence for it. Pi's name, this repository or checkout, the operator's wording, file presence, and a launcher's capability do not prove that this process consumed the files.
2. If current-process injection is not verified, describe the core and mission files only as **available sources with activation unverified**. Do not read or summarize their bodies as applicable policy. A policy snapshot can establish source and launcher coverage, but not by itself that this invocation used the launcher or which mission was resolved.
3. After activation scope is established, read only the verified applicable sources needed for the question: active Watchtower policy, applicable target-repository instructions, explicit operator instructions, and relevant machine-local routing policy. Follow actual precedence and identify conflicts rather than blending them.
4. For an ordinary answer, give one short source/scope statement and at most three key rules from verified applicable sources. Do not inventory a candidate source's rules, all sources, or all rules unless the operator explicitly requests an inventory.
5. Distinguish **explicit policy** from **runtime/project state**. Branches, task verdicts, active crews, assurance results, provider status, and `/afk` state are observations or state, not policy text; verify them separately.

Route requests to persist, archive, or compare policy to `watchtower-policy-snapshot`; requests to generate or save a durable fleet report to `watchtower-progress-report`; and `/afk` state or changes to `afk`. Ordinary policy answers create no artifact.
