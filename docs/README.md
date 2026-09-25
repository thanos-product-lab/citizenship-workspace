# Documentation

A map of what is here, what each document is for, and which ones describe the product as it
is today. Code, tests and the project's skills cite these documents by section number, so
their structure is stable: they are indexed here rather than rewritten.

## Start here

Four documents, in this order, give an accurate picture of the product in under an hour.

1. [Product guide](product/PRODUCT.md): what it is, who it is for, and how it works, in plain
   language for any reader.
2. [Architecture overview](architecture/ARCHITECTURE_OVERVIEW.md): how the system works, from
   what runs where to how the rules count days, and where to look up the details.
3. [Known limitations](KNOWN_LIMITATIONS.md): what it does not do, which gaps are deliberate,
   and which are still open.
4. [Demo script](DEMO_SCRIPT.md): the canonical demonstration, step by step, on the local
   stack.

## Current

Maintained and authoritative. If the code disagrees with one of these, the code is wrong.

| Document | Answers |
|---|---|
| [Product guide](product/PRODUCT.md) | **For any reader.** Who it is for, what it does, what the results mean, and what it does not do |
| [Architecture overview](architecture/ARCHITECTURE_OVERVIEW.md) | **The one to read.** How the system works end to end, and which spec section answers which question |
| [Deterministic rules spec](architecture/DETERMINISTIC_RULES_SPEC.md) | Look-up reference: date semantics, day counting, thresholds, banding |
| [Domain model RFC](architecture/DOMAIN_MODEL_RFC.md) | Look-up reference: entities, enums, invariants and state machines |
| [Evidence and claim lifecycle RFC](architecture/EVIDENCE_AND_CLAIM_LIFECYCLE_RFC.md) | Look-up reference: how a document is stored, read, proposed from, reviewed and deleted |
| [Known limitations](KNOWN_LIMITATIONS.md) | Open gaps, deliberate boundaries, and resolved entries (numbers are stable) |
| [Deployment](DEPLOYMENT.md) | Environments, services, secrets and how a deploy happens |
| [Demo script](DEMO_SCRIPT.md) | Running and showing the canonical demo locally |
| [Security and privacy](security/SECURITY_AND_PRIVACY_THREAT_MODEL.md) | The one security document: a two-minute summary at the top, then every threat and its control |
| [Design](design/DESIGN_SYSTEM_FOUNDATIONS.md) | The one design document: tokens, themes and contrast, how the interface behaves (§11), and the accessibility pass (§12) |
| [AI evaluation](evaluations/EVAL_REPORT.md) | The one evaluation document: the false-reassurance rate, what the corpus does not cover, the release gates, the spike, and every run |

## Reference

Authoritative for the sections the code cites, but not maintained as a whole. Read them for
the reasoning behind a decision, not as a description of the current build.

| Document | Why it is kept |
|---|---|
| [Release gate audit](RELEASE_GATE_AUDIT.md) | The record of the release decision: every release gate and its state |
| [Case study outline](product/CASE_STUDY_OUTLINE.md) | Raw material for the case study, until the case study itself exists |

## Decisions

Architecture decision records, grouped by what they protect. Identifiers are permanent,
because code and tests cite them.

**Trust boundary and provenance**
[0021](decisions/0021-evidence-attaches-to-a-travel-record-not-a-fact.md) evidence attaches to a travel record ·
[0025](decisions/0025-extraction-runs-reference-model-runs.md) extraction runs reference model runs ·
[0028](decisions/0028-the-trust-gate-has-one-implementation.md) the trust gate has one implementation ·
[0029](decisions/0029-the-claim-extractor-is-three-capabilities.md) the claim extractor is three capabilities

**Assessment history and currency**
[0001](decisions/0001-stale-is-currency-not-conclusion.md) stale is currency, not a conclusion ·
[0007](decisions/0007-assessment-results-are-the-source-of-truth.md) results are the source of truth ·
[0009](decisions/0009-case-phase-is-derived-not-stored.md) the case phase is derived ·
[0010](decisions/0010-group-currency-inherits-the-weakest-member.md) group currency inherits the weakest member ·
[0016](decisions/0016-a-failed-recalculation-is-recorded-best-effort.md) a failed recalculation is recorded best-effort ·
[0032](decisions/0032-an-application-date-that-has-passed.md) an application date that has passed ·
[0034](decisions/0034-the-case-next-step-is-derived-at-read-time.md) the case's next step is derived ·
[0035](decisions/0035-a-trip-reason-is-not-an-assessed-input.md) a trip's reason is not an assessed input

**Invalidation**
[0008](decisions/0008-blunt-stale-invalidation-at-m3b.md) blunt invalidation (*superseded by 0014*) ·
[0014](decisions/0014-selective-dependency-invalidation.md) selective dependency invalidation ·
[0022](decisions/0022-activating-a-second-rule-version-stales-the-first.md) a second rule version stales the first ·
[0027](decisions/0027-a-conflict-widens-the-residence-fan-out.md) a conflict widens the residence fan-out

**Issues**
[0015](decisions/0015-issues-are-a-reconciled-projection.md) issues are a reconciled projection ·
[0033](decisions/0033-what-the-issue-count-counts.md) what the issue count counts

**Security, tenancy and storage**
[0005](decisions/0005-defer-postgres-rls-to-a-hardening-slice.md) RLS deferred (*resolved by 0006*) ·
[0006](decisions/0006-postgres-rls-via-a-non-superuser-role.md) RLS via a non-superuser role ·
[0017](decisions/0017-the-rls-tenant-is-transaction-scoped.md) the RLS tenant is transaction-scoped ·
[0018](decisions/0018-presigned-downloads-with-a-review-trigger.md) presigned downloads ·
[0019](decisions/0019-the-storage-key-travels-in-a-signed-token.md) the storage key travels in a signed token ·
[0023](decisions/0023-the-tombstone-keeps-the-storage-key.md) the tombstone keeps the storage key ·
[0026](decisions/0026-embedded-pdf-javascript-is-accepted-not-sandboxed.md) embedded PDF JavaScript is accepted ·
[0030](decisions/0030-the-purge-holds-the-tenant-and-borrows-privilege-twice.md) the purge borrows privilege twice

**Interface structure**
[0002](decisions/0002-timeline-simulation-follows-the-rules.md) simulation mockups follow the rules ·
[0011](decisions/0011-absent-rather-than-zero-for-uncounted-things.md) absent rather than zero ·
[0012](decisions/0012-the-case-workspace-is-destinations-not-one-page.md) destinations, not one page ·
[0013](decisions/0013-currency-is-carried-by-the-case-header.md) currency is carried by the header ·
[0031](decisions/0031-the-design-system-replaced-radix-and-shadcn.md) the design system is hand built

**Sequencing and infrastructure** (decisions about order and platform, kept for their reasoning)
[0003](decisions/0003-deploy-targets.md) deploy targets ·
[0004](decisions/0004-route-support-is-a-service-in-m2.md) route support as a service in M2 ·
[0020](decisions/0020-polling-before-sse.md) polling before streaming ·
[0024](decisions/0024-document-preview-moves-to-m8.md) document preview moves to M8

New decisions start from the [template](decisions/000-adr-template.md).

## Retired

Development history that no longer describes the product lives in git history, not here:
the walkthrough scenarios and their findings, the milestone notes (M0 to the release slice),
the July 2026 reconciliation, the original technical architecture RFC (its lasting content
is in the architecture overview), the UI/UX direction document (its lasting rules are in the
design document's §11), the AI evaluation plan, spike findings and per-run results (folded
into the evaluation report), the product thesis, the MVP scope and acceptance criteria, and the
synthetic demo case specification (the product guide replaces the first two; the seed script
`app/seed/demo_case.py` now defines the demo case), and the per-milestone demo captures with their shot list (the
demo will be one video recorded at the end). Read any of them with, for example,
`git show a37b05a:docs/decisions/milestone-notes.md`.

The implementation roadmap and the milestone gates were retired once the build finished.
Code, docs and ADRs still use their milestone labels (M0 to M12) to say when something was
built; read the originals with `git show aad44b0:docs/IMPLEMENTATION_ROADMAP.md` and
`git show aad44b0:docs/MILESTONE_GATES.md`.
