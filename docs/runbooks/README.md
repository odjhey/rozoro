# Watchtower runbooks

These runbooks capture reusable operating practices exercised during a Watchtower session. They are guidance for operators and crews; they do not extend Rozoro's lifecycle protocol or replace repository-specific instructions.

## Runbooks

- [Dispatch and lifecycle](dispatch-and-lifecycle.md) — route work, follow handoffs, and retain crew context.
- [Role-separated delivery](role-separated-delivery.md) — separate implementation, independent review/test, pipeline custody, and merge authority.
- [No-mistakes custody](no-mistakes-custody.md) — safely enter, drive, and leave a no-mistakes run.
- [Human gates and exact-head evidence](human-gates-and-evidence.md) — preserve human decisions and bind claims to immutable evidence.

## Precedence

Explicit operator instructions and repository rules take precedence. A later instruction supersedes an older one only where they conflict; preserve unaffected constraints. Stop rather than invent authority for a destructive action, product decision, secret-bearing operation, protection bypass, or custody exception.

## Provenance and inventory

The source inventory was established from durable task handoffs and briefs, not filenames alone, and checked against the active Watchtower policy set and repository templates. Session-specific paths, identities, commit IDs, model preferences, temporary configuration hashes, and private evidence were removed or generalized. The `WT-TR-*` keys below are stable sanitized identifiers for the durable task records; `WT-POL-*` keys identify the policy document or category consulted.

| Provenance keys | Source material | Evidence of use | Disposition |
|---|---|---|---|
| `WT-TR-DISPATCH-01`; `WT-POL-BOUNDARY-OPS`; `templates/watchtower.md` | Active Watchtower boundary/operations policy and dispatcher handoffs | Standing policy loaded for the session; task records consistently use Watchtower as dispatcher/judge and crew as repository worker | Generalized into dispatch and lifecycle |
| `WT-TR-ROLE-01`; `WT-TR-REVIEW-01`; `WT-TR-TEST-01`; `WT-TR-REPLAN-01`; `WT-POL-ROLE-MODEL`; `WT-POL-ROLE-REPORT` | Active role/model and role-report policies plus role-specific task records | Coding, independent reviewer/tester, replanner, and dedicated no-mistakes tasks record those boundaries; handoffs use `attempt_count` and `caused_by` | Generalized into role-separated delivery; transient model assignments omitted |
| `WT-TR-PUBLISH-01`; `WT-POL-NO-MISTAKES` | Active no-mistakes policy and dedicated publication brief | The publication task explicitly assigns sole pipeline control, custody checks, no manual branch movement, exact-head reporting, and no merge | Generalized into no-mistakes custody |
| `WT-TR-HUMAN-GATES-01`; `WT-POL-DELIVERY-PRODUCT`; `WT-POL-HUMAN-GATES-2-6` | Active delivery/product policy and the durable Human Gates 2–6 guide | Task records distinguish machine evidence from required human decisions and forbid claiming human gates from agent approval | Generalized into human gates and evidence |
| `WT-TR-PR28-RECOVERY-01` | PR #28 authorization/recovery plan | Durable record says it was prepared read-only, remained unauthorized, and was not executed | Excluded as a procedure. Its generally valid stop/CAS/evidence principles appear only where they agree with supported custody rules; no exception recipe is included |
| `WT-TR-PR27-SETTLEMENT-01` | PR #27 operator-pair settlement | Durable record describes a proposal, not an approved or executed procedure; the work was abandoned | Explicitly excluded and not revived or approved |
| `WT-TR-ARTIFACT-REVIEW-01`; `WT-TR-ARTIFACT-TEST-01` | Dated artifact skill reports and review/test evidence | Used to validate policy/progress artifact behavior, but concern a feature branch not included in this documentation PR | Excluded from runbook content; no private `/tmp` artifacts or volatile snapshots copied |
| `WT-TR-RUNTIME-PRIVATE-01` | Task `session.json`, identities, system prompts, acknowledgement cursors, and operator-local audit snapshots | Runtime/private records rather than reusable procedures | Excluded |

The manifest records stable sanitized provenance keys rather than private absolute source paths. The Draft PR description should retain this distinction so review does not imply that a proposal was operationally approved.
