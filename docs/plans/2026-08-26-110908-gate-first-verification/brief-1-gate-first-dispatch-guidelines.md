> **STATUS: DELIVERED** — implemented and merged as [PR #116](https://github.com/odjhey/rozoro/pull/116), which extended the brief with final-head provenance rules and a labeled red-candidate judgment exception. Retained for provenance.

# Crew brief: encode gate-first verification and narrowed review/test roles

**Repo:** /Users/odz/proj/rozoro · **Task kind:** Coder (docs/policy edit, no runtime code)
**Branch:** one branch, one PR. Do not touch AGENTS.md.

## Intent

Cut driver round trips per deliverable by reordering verification: the no-mistakes
gate runs mechanics (build, tests, lint, mechanical review with auto-fix) FIRST and
on every re-entry; judgment crews (Reviewer, Tester) run only on gate-green
candidates and never execute the test suite themselves. Rationale (measured): a
deliverable currently pays ~6 driver hops (code → review → test → repair →
rereview → retest → gate → merge) at ~12+ min per hop; gate-first plus
gate-mediated re-verification collapses this to ~3–4 hops. The repo's own
`.no-mistakes.yaml` history note ("32 of 33 pipeline fixes came from review,
nearly all auto-fix") shows the gate already absorbs mechanical findings.

## File to edit: `templates/watchtower-crew-dispatch-guidelines.md`

1. **New short subsection "Verification ordering"** (place after the Planner
   section, before the Coder role at line ~52): mechanics before judgment. On
   coder-done with a committed candidate, the default next hop is the No-Mistakes
   Runner. Reviewer/Tester dispatch only after the gate reports green (or when the
   Watchtower explicitly needs judgment on a red candidate, e.g. suspected design
   dead-end). After a repair, verification re-enters through a gate re-run — a
   fresh rereview/retest crew is dispatched only when the repair itself needs new
   judgment, not to re-execute mechanical checks.
2. **Coder section (lines ~52-59):** add that the coder's done-report should name
   the exact committed head ready for the gate (it already reports the candidate
   head — extend the sentence, don't restructure).
3. **Reviewer section (lines ~61-66):** add: reviews gate-green candidates;
   judgment only (design, contracts, correctness reasoning, acceptance fit); does
   NOT execute the test suite — the gate binds execution evidence to the exact
   head (delivery-evidence skill terminology).
4. **Tester section (lines ~68-73):** reframe from test-runner to test-designer.
   Keep the existing coverage list (boundaries, invalid inputs, retries, partial
   failures, state transitions, integrations, weak-test risks) but the deliverable
   is new/extended tests that JOIN the repository suite so the gate enforces them
   on every future candidate (the ratchet). Exploratory behavior-driving stays in
   scope; hand-running the full existing suite as the verification of record does
   not. Bind results to the tested head (keep that sentence).
5. **No-Mistakes Runner section (lines ~98-132):** add one paragraph: the gate is
   the FIRST verification hop and the re-entry point after repairs; its re-run —
   not fresh review/test crews — is the verification of record for mechanical
   confidence.
6. **The ratchet rule (add to both Reviewer and Tester sections, one sentence
   each):** the boundary between crew and gate is *codified vs novel judgment*,
   and it moves. Whenever a crew finding is a repeat of a class seen before, the
   crew's handoff must propose the codification that retires it: a
   `review.path_instructions` entry in `.no-mistakes.yaml`, a test that joins the
   suite, or a lint rule. Crews work the frontier; anything expressible as a
   rule/test/instruction belongs to the gate, which then enforces it on every
   future candidate for free.

## Also edit: `templates/crew-guidelines.md`

Add a reusable block for review/test crews: "Do not execute the repository test
suite as your verification step; the no-mistakes gate owns execution evidence
bound to the exact head. Reviewers: judgment only. Testers: write tests that join
the suite." Match the file's existing tone/format.

## Constraints

- Do NOT change role model/effort defaults (that is a separate experiment).
- Do NOT touch AGENTS.md, `.no-mistakes.yaml`, or any bin/lib code.
- Keep edits surgical; preserve the document's voice and section structure.
- Check the whole file for now-contradictory sentences (e.g. any text implying
  review/test happens before the gate or that testers run the suite) and fix them.

## Acceptance

- The four role sections + new ordering subsection read coherently end-to-end.
- `templates/crew-guidelines.md` block present.
- PR opened; no other files changed.
