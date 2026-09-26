# Decisions

Every significant design decision, one file each, written when it was made and not edited
afterwards. Code and tests cite them by number (`ADR-0014`), so numbers are permanent. A
decision that was later replaced stays, and says what replaced it.

Each line below states **what was decided**, not just the topic. Open a file for the
context, the alternatives rejected and the consequences.

## Start here

Five decisions shape the rest. Read these and you can explain the design.

| ADR | Decision |
|---|---|
| [0001](0001-stale-is-currency-not-conclusion.md) | Whether a result is out of date (its currency) is a separate question from what it concluded, and the two are never merged. |
| [0007](0007-assessment-results-are-the-source-of-truth.md) | A requirement's conclusion is read only from the stored assessment result, never recomputed by a page. |
| [0014](0014-selective-dependency-invalidation.md) | When an input changes, only the results whose rules declared that input go out of date, in the same transaction as the change. |
| [0021](0021-evidence-attaches-to-a-travel-record-not-a-fact.md) | A document supports a trip by linking to the travel record, and the coverage rule asks about any kind of link. |
| [0028](0028-the-trust-gate-has-one-implementation.md) | Whether a trip can be trusted is decided in one function, and every read model, including the browser, uses its answer. |

## Trust boundary and provenance

| ADR | Decision |
|---|---|
| [0021](0021-evidence-attaches-to-a-travel-record-not-a-fact.md) | A document supports a trip by linking to the travel record, and the coverage rule asks about any kind of link. |
| [0025](0025-extraction-runs-reference-model-runs.md) | An extraction run points at the model call that produced it rather than copying its cost and provider, and can exist without one when a call was refused. |
| [0028](0028-the-trust-gate-has-one-implementation.md) | Whether a trip can be trusted is decided in one function, and every read model, including the browser, uses its answer. |
| [0029](0029-the-claim-extractor-is-three-capabilities.md) | Reading documents is three separate AI capabilities, one per document kind; the immigration status one is held back until its values can be cross-checked. |
| [0035](0035-a-trip-reason-is-not-an-assessed-input.md) | A trip's reason is a note on the trip, not an assessed input, so editing it stales nothing; the travel list shows every trip and marks the untrusted ones. |

## Assessment history and currency

| ADR | Decision |
|---|---|
| [0001](0001-stale-is-currency-not-conclusion.md) | Whether a result is out of date (its currency) is a separate question from what it concluded, and the two are never merged. |
| [0007](0007-assessment-results-are-the-source-of-truth.md) | A requirement's conclusion is read only from the stored assessment result, never recomputed by a page. |
| [0009](0009-case-phase-is-derived-not-stored.md) | The case phase is worked out on every read from the current results, never stored. |
| [0010](0010-group-currency-inherits-the-weakest-member.md) | A group of requirements is as out of date as its most out-of-date member, and a group with no results has no currency rather than "current". |
| [0016](0016-a-failed-recalculation-is-recorded-best-effort.md) | A failed recalculation is recorded in a separate transaction, and recording it can never hide the original error. |
| [0032](0032-an-application-date-that-has-passed.md) | A past date cannot be chosen, and a saved date that has since passed is flagged on read rather than stored as a limitation. |
| [0034](0034-the-case-next-step-is-derived-at-read-time.md) | The overview's next steps come from fixed rules over the case's current state, worked out on every read. |

## Invalidation

| ADR | Decision |
|---|---|
| [0008](0008-blunt-stale-invalidation-at-m3b.md) | Any residence input change staled every residence result. *Replaced by 0014.* |
| [0014](0014-selective-dependency-invalidation.md) | When an input changes, only the results whose rules declared that input go out of date, in the same transaction as the change. |
| [0022](0022-activating-a-second-rule-version-stales-the-first.md) | Switching to a new rule version marks every current result of the old version out of date. |
| [0027](0027-a-conflict-widens-the-residence-fan-out.md) | The absence and presence rules also depend on confirmed facts and document links, so a document conflict stales them; over-firing is accepted. |

## Issues

| ADR | Decision |
|---|---|
| [0015](0015-issues-are-a-reconciled-projection.md) | Issues are recomputed from current state and compared with what is stored, so opening, resolving and reopening all come from one comparison. |
| [0033](0033-what-the-issue-count-counts.md) | The issue count counts things you must act on or review, with all out-of-date and failed-processing issues counted as one; notes are counted apart. |

## Security, tenancy and storage

| ADR | Decision |
|---|---|
| [0005](0005-defer-postgres-rls-to-a-hardening-slice.md) | The ownership check in code shipped first, with database row-level security tracked as a gap. *Resolved by 0006.* |
| [0006](0006-postgres-rls-via-a-non-superuser-role.md) | Every case request switches to a database role without superuser rights, so row-level security policies actually apply. |
| [0017](0017-the-rls-tenant-is-transaction-scoped.md) | The current user is re-applied to the database at the start of every transaction, so no connection carries a user over. |
| [0018](0018-presigned-downloads-with-a-review-trigger.md) | Documents are served by signed links that expire in 60 seconds, returned as JSON so they never reach the address bar. |
| [0019](0019-the-storage-key-travels-in-a-signed-token.md) | Starting an upload writes nothing; a signed token carries the storage key, and the document is recorded once its bytes arrive. |
| [0023](0023-the-tombstone-keeps-the-storage-key.md) | A deleted document's record keeps its storage key but clears its name everywhere it was copied. |
| [0026](0026-embedded-pdf-javascript-is-accepted-not-sandboxed.md) | JavaScript in a PDF is allowed to run in the preview, because sandboxing breaks it, and the risk is limited in other ways. |
| [0030](0030-the-purge-holds-the-tenant-and-borrows-privilege-twice.md) | Deleting a case runs as the owning user, so a wrong query cannot reach other users' data, and uses elevated rights in only two places. |

## Interface structure

| ADR | Decision |
|---|---|
| [0002](0002-timeline-simulation-follows-the-rules.md) | Design mockups that show calculated values must agree with the rules spec. |
| [0011](0011-absent-rather-than-zero-for-uncounted-things.md) | A figure nothing has counted yet is left out, not shown as zero. |
| [0012](0012-the-case-workspace-is-destinations-not-one-page.md) | The case is split into pages with their own URLs, sharing one header and navigation. |
| [0013](0013-currency-is-carried-by-the-case-header.md) | Whether results are out of date, and the button to update them, live in the case header on every page. |
| [0031](0031-the-design-system-replaced-radix-and-shadcn.md) | The design system is hand built, because the components the product needs are not ones a UI kit ships. |

## Sequencing and infrastructure

Decisions about order and platform, kept for their reasoning.

| ADR | Decision |
|---|---|
| [0003](0003-deploy-targets.md) | The web app runs on Vercel, and the API, worker, Postgres and Redis on Railway, all deploying from `main`. |
| [0004](0004-route-support-is-a-service-in-m2.md) | The route checks started as plain functions in a service, and moved behind the rules engine once it existed. |
| [0020](0020-polling-before-sse.md) | Document progress is polled while something is moving, not streamed. |
| [0024](0024-document-preview-moves-to-m8.md) | Document preview waited until there were AI-proposed values to check against it. |

## Writing a new one

Take the next number and name the file after the decision, for example
`0036-what-was-decided.md`. Then add its one-line decision to the right group above.

Keep it short, with these sections:

- **Status and date:** Accepted, or Replaced by ADR-XXXX.
- **Context:** what forced a decision. The constraint, not the solution.
- **Decision:** what was decided, in one paragraph.
- **Alternatives rejected:** each with its reason. This is the section a reviewer reads,
  because a decision with no rejected alternatives reads as a default.
- **Consequences:** what it makes easier and harder, and what it commits to.
- **Invariants touched:** which rules in `CLAUDE.md` §2 it affects, and why they still hold.
