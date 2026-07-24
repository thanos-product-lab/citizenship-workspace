# Evidence-First Citizenship Workspace

## Implementation Roadmap

### Status

Proposed for implementation
Version: 0.2
Project: Evidence-First Citizenship Workspace
Initial route: UK naturalisation under Section 6(1), standard five-year route

---

## 0. Changes from v0.1

| # | Change | Reason |
|---|---|---|
| 1 | Plan of record is now **M0–M8 + core hardening + release** (was M0–M12) | Fits a 6-week flagship inside a 12–16 week multi-project portfolio |
| 2 | Blocking documents assigned **per milestone**, not all to M0 | M1 needs no product decisions; parallelise doc-writing with scaffolding |
| 3 | M3 split into **M3A (input versioning)** and **M3B (rules and assessments)** | M3 was the hardest milestone in the project compressed into one week |
| 4 | **Blunt stale invalidation moved into M3B**; M6 upgrades it to selective | Resolves contradiction: §8 First Slice required stale/recalculate, M6 owned it |
| 5 | **Issues and stale-state (M6) now precede the timeline (M5)** | Stale-state is the thesis; the timeline is the showcase and the safer cut |
| 6 | **Deployment moved into M1** | Every milestone becomes demoable; removes a week-7 risk |
| 7 | **Throwaway AI spike added in week 2** | De-risks extraction quality/cost before M8 depends on assumptions |
| 8 | **Model spend limits and timeouts moved from M11 to M8** | First live model calls are when runaway cost becomes possible |
| 9 | **Demo assets captured per milestone** | Avoids reconstructing seven weeks of work at the end |
| 10 | Guidance **registry** retained in the cut; only the **AI explainer** is optional | Rule-to-source provenance is load-bearing for the requirement panel |

---

## 1. Purpose

This roadmap translates the product thesis, MVP scope, UI/UX direction, technical
architecture, and domain model into an executable build plan.

The project must be implemented through **small vertical slices** that produce
usable product behaviour across frontend, API, domain logic, persistence, tests,
observability, and documentation.

The roadmap deliberately avoids:

- building the entire backend before the interface;
- building screens against mocked behaviour for too long;
- adding AI before deterministic foundations are correct;
- expanding into multiple immigration routes;
- introducing infrastructure that does not improve the core product.

The implementation strategy is:

> Prove the product thesis with deterministic, inspectable behaviour first. Add
> document AI only after the case model, rules, provenance, and stale-state
> lifecycle are reliable.

---

## 2. Source-of-Truth Documents

Implementation must remain aligned with:

```
CLAUDE.md
docs/product/Evidence_First_Citizenship_Workspace_Product_Thesis.md
docs/product/MVP_SCOPE_AND_ACCEPTANCE_CRITERIA.md
docs/product/SYNTHETIC_DEMO_CASE.md
docs/design/Evidence_First_Citizenship_Workspace_UI_UX.md
docs/design/DESIGN_SYSTEM_FOUNDATIONS.md
docs/architecture/Evidence_First_Citizenship_Workspace_Technical_Architecture_RFC.md
docs/architecture/DOMAIN_MODEL_RFC.md
docs/architecture/DETERMINISTIC_RULES_SPEC.md
docs/architecture/EVIDENCE_AND_CLAIM_LIFECYCLE_RFC.md
docs/evaluations/AI_EVALUATION_PLAN.md
docs/security/SECURITY_AND_PRIVACY_THREAT_MODEL.md
docs/decisions/            # ADRs
```

### 2.1 Document gating (revised)

A missing document blocks **only the milestone that depends on it**, not the
whole project. Write documents just in time, immediately before their milestone.

| Document | Blocks | Status |
|---|---|---|
| Product Thesis | — | ✅ exists |
| MVP Scope | — | ✅ exists |
| UI/UX Direction | — | ✅ exists |
| Technical Architecture RFC | — | ✅ exists |
| Domain Model RFC | — | ✅ exists |
| `CLAUDE.md` | M1 | ✅ exists |
| `SYNTHETIC_DEMO_CASE.md` | **M3A** | ⬜ write in week 1 |
| `DETERMINISTIC_RULES_SPEC.md` | **M3B** | ⬜ write in week 1 — *critical path* |
| `DESIGN_SYSTEM_FOUNDATIONS.md` | **M4** | ⬜ write in week 1 (tokens can be thin) |
| `SECURITY_AND_PRIVACY_THREAT_MODEL.md` | **M7** (lightweight) / M11 (full) | ⬜ |
| `EVIDENCE_AND_CLAIM_LIFECYCLE_RFC.md` | **M8** | ⬜ |
| `AI_EVALUATION_PLAN.md` | **M8** | ⬜ |

**M1 has no blocking documents.** Start scaffolding immediately and write the
rules spec in parallel.

---

## 3. Delivery Principles

### 3.1 Build vertical slices

A valid slice includes, where relevant: migration · domain model · service
behaviour · API contract · generated TypeScript client · frontend experience ·
empty/loading/error/recovery states · tests · observability · documentation.

### 3.2 Prefer product evidence over infrastructure breadth

Strongest portfolio evidence: correct temporal logic, explainable assessments,
claim confirmation, evidence provenance, stale-state handling, polished
interaction design, evaluations.

Not: excessive services, Kubernetes, abstraction-heavy frameworks, speculative
multi-route architecture.

### 3.3 AI enters only after deterministic foundations

Do not integrate live AI into the product until claims and facts are separate,
fact versioning works, assessment history is immutable, stale propagation works,
the first deterministic slice is polished, and the AI evaluation plan exists.

**Exception — the week 2 spike (new in v0.2).** A throwaway, non-integrated
script that runs sample documents through the provider with a real Pydantic
schema, to learn extraction quality, cost, and latency early. It lives outside
`services/platform/app/`, ships to nobody, and is deleted after M8 planning.
This is de-risking, not integration.

### 3.4 One canonical synthetic case

A single synthetic demo case drives seed data, development, integration tests,
Playwright flows, AI evaluation fixtures, screenshots, and the demo video.

### 3.5 Quality gates apply continuously

Do not defer accessibility, error handling, tests, observability, documentation,
or security boundaries until the end.

### 3.6 Capture demo assets per milestone (new in v0.2)

At the end of each milestone, record a short screen capture and 1–2 screenshots
of the new capability into `docs/demo-assets/`. M12 then edits existing material
rather than reconstructing seven weeks of work.

---

## 4. Roadmap Overview

```text
M0   Discovery Closeout (thin)
M1   Repository, Platform Foundation, and First Deploy
M2   Supported Case Setup
M3A  Versioned Residence Inputs
M3B  Deterministic Rules and Immutable Assessments
M4   Explainable Case Workspace
M6   Issue Detection and Stale-State Workflow      ← now precedes timeline
M5   Timeline and Application-Date Simulation
M7   Evidence Foundation
M8   Human-in-the-Loop Document AI
──────────────  plan of record ends here  ──────────────
M9   Guidance Registry (deterministic) + optional AI explanation
M10  Preparation Summary
M11  Evaluation, Security, and Reliability Hardening   (core slice pulled forward)
M12  Portfolio Polish and Release
```

Milestone numbers are retained from v0.1 for traceability; **build order is the
order listed above**.

---

# Milestone 0 — Discovery Closeout (thin)

## Objective

Resolve only the decisions that block the *next* milestone. Do not attempt to
write all remaining RFCs before coding.

## Deliverables

- `SYNTHETIC_DEMO_CASE.md`: canonical applicant, five-year travel history,
  expected absence totals, expected requirement states, the expected stale
  transition, and the alternative application date that resolves physical presence.
- `DETERMINISTIC_RULES_SPEC.md`: absence-counting semantics (inclusive/exclusive
  day rules), qualifying-period derivation, physical-presence definition,
  thresholds with cited guidance, near-threshold margins, summary codes.
- `DESIGN_SYSTEM_FOUNDATIONS.md`: colour ramp, type scale, spacing, status
  tokens, surface treatment — enough to prevent default shadcn styling.

## Acceptance Criteria

- No unresolved contradiction across thesis, MVP, UX, architecture, domain model.
- The first vertical slice can be described without inventing new entities.
- The synthetic case has *expected numeric outputs*, not just narrative.
- Every threshold in the rules spec cites a named, dated guidance source.
- The visual direction is specific enough to avoid default shadcn styling.

## Stop Conditions

Do not start **M3** if absence-counting semantics remain undefined, the synthetic
case lacks expected calculations, or the initial route scope is still changing.

Do not let these block **M1**.

---

# Milestone 1 — Repository, Platform Foundation, and First Deploy

## Objective

Create the smallest credible development platform — and get it deployed — without
implementing product features.

## Scope

**Repository:** `apps/web · services/platform · packages/{api-client,
design-system, test-fixtures} · docs · infra`

**Frontend:** Next.js App Router · strict TS · Tailwind · Radix · owned
shadcn/ui foundation · TanStack Query · React Hook Form · Zod · Vitest ·
Testing Library · Playwright · base design tokens.

**Backend:** FastAPI · Pydantic · SQLAlchemy 2 · Alembic · PostgreSQL · Redis ·
Celery · pytest · Hypothesis · Ruff · mypy (strict) · health endpoints.

**Contracts and platform:** OpenAPI generation · generated TS client · CI drift
check · Docker Compose (Postgres, Redis, API, worker, MinIO) · Clerk auth shell ·
structlog · baseline OpenTelemetry · Sentry · GitHub Actions.

**Deployment (new in v0.2):** web to Vercel, API + worker to Railway or Fly,
managed Postgres and Redis, S3 bucket. CI deploys `main` automatically.

## Explicitly Excluded

Product schema beyond placeholders · evidence uploads · live AI · complex UI.

## Acceptance Criteria

- `pnpm` and `uv` installs are reproducible; Python and Node versions pinned.
- Web, API, worker, Postgres, Redis, MinIO run locally via `just up`.
- `/health/live` and `/health/ready` work locally **and in the deployed environment**.
- OpenAPI client generation works; CI fails on drift.
- CI runs frontend and backend lint, typecheck, and baseline tests.
- A sample authenticated API request succeeds against the deployed environment.
- Structured logs include a trace identifier.
- No secrets are committed; secrets live in the provider store.
- Root README explains local setup.

## Key Tests

API health · database connectivity · worker connectivity · generated-client
drift · one Playwright smoke test against the deployed URL.

## Portfolio Signal

Low by itself. Timebox it. The exception is **design tokens** — visual direction
is expensive to retrofit, so do not ship a placeholder you intend to replace.

---

# Milestone 2 — Supported Case Setup

## Objective

Enable a user to create a case, confirm route scope, and establish the case.

## User Journey

Sign in → start a case → answer route-scope questions → receive supported /
unsupported / review-needed outcome → resume an incomplete case.

## Domain Scope

`ApplicationCase` · `CaseMembership` · `RouteProfile` · `RouteProfileVersion` ·
route support service · case lifecycle · domain events · audit entries ·
transactional outbox.

## API Scope

```text
POST   /api/v1/cases
GET    /api/v1/cases
GET    /api/v1/cases/{case_id}
POST   /api/v1/cases/{case_id}/route-profile/confirm
DELETE /api/v1/cases/{case_id}
```

## Frontend Scope

Case list · create case · guided route onboarding · save and resume ·
unsupported-route state · supported case shell · navigation scaffold.

## Acceptance Criteria

- A supported Section 6(1) user can create an active case.
- A British-spouse-route user is stopped before assessments are created.
- A user without supported immigration status is stopped.
- A user who may already be British receives a review-needed state.
- Route profile confirmation creates an immutable version.
- Another user cannot access the case by changing identifiers.
- Incomplete onboarding resumes correctly.
- Case deletion enters deletion-pending state.
- Onboarding is keyboard accessible; empty/loading/error/retry states exist.

## Key Tests

Route decision units · authorisation integration · optimistic concurrency ·
onboarding Playwright flow · unsupported-route Playwright flow.

---

# Milestone 3A — Versioned Residence Inputs

## Objective

Establish the versioned input layer that assessments will later depend on — with
no rules engine yet.

## Blocking Documents

`SYNTHETIC_DEMO_CASE.md`

## Domain Scope

`ProposedApplicationDate` + version · `TravelRecord` + version · residence
validation service · date confidence · review state · entry source.

## API Scope

```text
POST   /api/v1/cases/{case_id}/application-dates/select
POST   /api/v1/cases/{case_id}/travel-records
PATCH  /api/v1/cases/{case_id}/travel-records/{travel_record_id}
DELETE /api/v1/cases/{case_id}/travel-records/{travel_record_id}
```

## Frontend Scope

Application-date form · accessible travel-record table · add/edit/delete trip ·
confirmed vs uncertain visual distinction.

## Acceptance Criteria

- Editing a record creates a new immutable version; old versions are never mutated.
- Departure cannot be after return; impossible ranges rejected with field-bound errors.
- Removal creates a tombstone, not a delete.
- Confirmed-exact, uncertain, and estimated records are visibly distinct.
- Optimistic concurrency conflicts return a domain error, not a silent overwrite.
- The canonical synthetic travel history loads via seed.

## Key Tests

Version sequence properties · date-order validation · concurrency conflict ·
seed integrity.

---

# Milestone 3B — Deterministic Rules and Immutable Assessments

## Objective

The architecture proof. Deterministic residence calculations producing immutable,
fully-provenanced assessment results.

## Blocking Documents

`DETERMINISTIC_RULES_SPEC.md`

## Domain Scope

`RequirementDefinition` · `RuleVersion` · `RuleDependencyDefinition` ·
`AssessmentRun` · `AssessmentResult` · `AssessmentInputLink` · structured
`Limitation` and `NextAction` · **blunt stale invalidation** (any residence input
change marks all residence results stale — selective invalidation arrives in M6).

## Initial Requirements

`status.holding_period` · `residence.qualifying_period` ·
`residence.physical_presence_start_date` · `residence.total_absences` ·
`residence.final_year_absences` · `residence.travel_consistency`

## API Scope

```text
GET  /api/v1/cases/{case_id}/requirements
GET  /api/v1/cases/{case_id}/requirements/{requirement_key}
POST /api/v1/cases/{case_id}/assessments/recalculate
```

## Frontend Scope

Basic absence summary · initial requirement detail · current vs historical
result indicator · stale notice with recalculate action.

## Acceptance Criteria

- Qualifying-period boundaries are deterministic; leap years and month boundaries tested.
- Confirmed exact records drive trusted results; uncertain records do not.
- Every result references exact input versions and a rule version.
- Conclusions are immutable; recalculation creates a new run.
- Conclusion and currency are stored and rendered as separate dimensions.
- A historical result remains inspectable after recalculation.
- Calculation breakdown lists the exact trips and dates used.
- **No AI capability is used anywhere in this milestone.**
- The canonical synthetic case produces the documented expected results.

## Key Tests

Rule units · **Hypothesis date properties** · assessment input provenance ·
current-result uniqueness per case+requirement · canonical case integration test.

---

# Milestone 4 — Explainable Case Workspace

## Objective

Turn deterministic outputs into a calm, polished, inspectable product experience.

## Blocking Documents

`DESIGN_SYSTEM_FOUNDATIONS.md`

## Frontend Scope

**Case overview:** readiness narrative · requirement groups · top three priority
actions · issue and evidence placeholders · proposed application date.

**Requirement detail:** the explanation stack — Assessment → Facts used →
Evidence used → Rule used → Limitations → Next action.

**Domain components:** `RequirementStatus` · `AssessmentSummary` ·
`ExplanationStack` · `CalculationBreakdown` · `SourceReference` ·
`BeforeAfterValue` · `StaleAssessmentNotice`.

## Backend Scope

Case overview projection · requirement detail projection · summary codes and
parameters · priority action derivation · **deterministic explanation templates**.

## Acceptance Criteria

- No readiness percentage appears anywhere.
- Requirement state is understandable without colour.
- Every assessment is traceable to exact inputs in the UI.
- Current and historical results are visually distinct.
- Empty, partial, and completed states exist.
- No more than three priority actions on the overview.
- Works at mobile and desktop widths; core screens meet WCAG 2.2 AA.
- **The product does not resemble a default shadcn dashboard.**
- The synthetic case demos end to end.

---

# Milestone 6 — Issue Detection and Stale-State Workflow

*(Built before M5. This is the thesis; the timeline is the showcase.)*

## Objective

Make uncertainty, conflicts, and data changes manageable rather than alarming,
and upgrade invalidation from blunt to selective.

## Domain Scope

`Issue` · `IssueResolution` · `AssessmentInvalidationService` ·
`IssueDerivationService` · **selective dependency invalidation** (replacing M3B's
blunt version) · stale-to-superseded workflow · automatic issue resolution.

## Initial Issue Types

Uncertain travel date · overlapping travel · stale assessment · near threshold ·
missing required fact · unsupported complexity.

## Frontend Scope

Issue queue grouped by user action · conflict comparison · stale notices ·
resolution history · optimistic resolution with undo where safe · retry states.

## Acceptance Criteria

- Changing a travel record marks **only affected** results stale.
- Stale state is set in the same transaction as the input change.
- Failed recalculation leaves the old result stale; nothing is promoted to current.
- Successful recalculation creates a new current result; previous becomes superseded.
- Stale issues resolve automatically.
- Deduplication prevents duplicate open issues.
- Blocking issues cannot be dismissed.
- Issue language is calm, specific, non-alarmist.
- The canonical demo shows a complete stale → recalculate flow.

---

# Milestone 5 — Timeline and Application-Date Simulation

## Objective

The most visually and technically distinctive frontend interaction.

## Domain and API Scope

Provisional calculation mode · application-date simulation service · timeline
projection · boundary markers · overlap and uncertainty projections.

```text
POST /api/v1/cases/{case_id}/application-dates/simulate
GET  /api/v1/cases/{case_id}/timeline
```

## Frontend Scope

React + SVG timeline · D3 scales · zoom · keyboard navigation · screen-reader
summary · accessible table alternative · date comparison · before/after
calculations · save and cancel.

## Acceptance Criteria

- Simulation does not mutate case state.
- Saving creates a new date version and triggers invalidation.
- The timeline handles the canonical five-year case smoothly.
- Keyboard users can inspect trips and boundaries.
- The table alternative contains equivalent information.
- Uncertain records are textually *and* visually distinct.
- The physical-presence date is clearly marked.
- Reduced-motion preference respected.

---

# Milestone 7 — Evidence Foundation

## Objective

Private evidence storage and asynchronous processing — still without live AI.

## Blocking Documents

`SECURITY_AND_PRIVACY_THREAT_MODEL.md` (lightweight version sufficient here)

## Domain Scope

`EvidenceItem` · `EvidenceFile` · `EvidenceProcessingRun` · evidence and deletion
lifecycles · support availability · processing domain states.

## Platform Scope

Private object storage · presigned upload/download · size and media validation ·
checksum · PyMuPDF native text extraction · derived previews · Celery worker ·
SSE progress with polling fallback · transactional outbox.

## Frontend Scope

Evidence library · upload experience · processing states · document preview ·
retry · delete · unsupported state · review queue placeholder.

## Acceptance Criteria

- Files are never publicly addressable; signed URLs expire.
- Unsupported file types rejected before processing.
- Domain processing states shown — never raw Celery states.
- Worker tasks idempotent; duplicate delivery creates no duplicate output.
- Processing failure preserves the uploaded evidence.
- Evidence deletion invalidates dependent support and marks assessments stale.
- Old signed URLs cannot access deleted files.
- No raw document content in logs or traces.

---

# Milestone 8 — Human-in-the-Loop Document AI

## Objective

Narrow AI capabilities that propose structured claims and require user review.

## Blocking Documents

`AI_EVALUATION_PLAN.md` · field schemas in `EVIDENCE_AND_CLAIM_LIFECYCLE_RFC.md`

## Supported Categories

Immigration status · English-language test · Life in the UK · travel booking.

## AI Capabilities

`DocumentClassifier` · `DocumentClaimExtractor` · `TravelRecordExtractor` ·
`ConflictCandidateDetector`

## Domain Scope

`ExtractionRun` · `ExtractedClaim` · `ClaimReviewDecision` · `CaseFact` ·
`FactVersion` · `FactEvidenceLink` · claim supersession · fact creation ·
conflict candidates.

## Cost Controls (moved forward from M11 in v0.2)

Per-request model timeout · per-run retry cap · daily spend ceiling with hard
stop · cost recorded per `model_run` · dev-environment budget alert.

## User Journey

Upload → analysis → split-view review → inspect proposed fields → confirm /
correct / reject → confirmed facts update → assessments go stale and recalculate
→ trace provenance from requirement back to the document region.

## Acceptance Criteria

- Structured outputs validate against versioned schemas; unknown fields rejected.
- Invalid output creates no claim.
- **Unconfirmed claims never influence trusted assessments.**
- Correcting preserves the original proposal.
- Rejected claims cannot create facts.
- No bulk-confirm for high-risk date fields.
- Every model run records provider, model, prompt version, schema version,
  latency, cost, and trace ID.
- **Prompt injection inside a document cannot alter capability behaviour** (fixture-tested).
- Partial extraction is displayed honestly.
- Unsupported documents create no trusted facts.
- The canonical demo includes one conflicting date resolved through evidence review.

---

> ### Plan of record ends here.
> M9–M12 below are the extended plan. Before starting M9, run the release slice
> in §7.2 so the project is shippable at any point.

---

# Milestone 9 — Guidance Registry and Contextual Explanation

## Objective

Connect rules and assessments to versioned official guidance.

## Domain Scope (retained in the cut — cheap and deterministic)

`GuidanceSource` · `GuidanceVersion` · `GuidanceSection` · `RuleGuidanceLink` ·
source versioning · source-unavailable state.

## AI Capabilities (optional — first thing to cut)

`GuidanceExplainer` · `IssueSummariser`

Deterministic templates for core calculations; AI only for optional
plain-language contextual explanation.

## Retrieval Strategy

Identify requirement deterministically → retrieve approved sections mapped to the
active rule → supply exact source IDs → validate returned references. No general
web search. No broad immigration chatbot.

## Acceptance Criteria

- Every active rule references approved guidance.
- Historical assessments retain their source version.
- New guidance never rewrites old results.
- AI explanations cannot add unlinked facts; unknown source IDs rejected.
- Explanation failure does not break the structured assessment.
- The assistant stays subordinate and case-scoped.

---

# Milestone 10 — Preparation Summary

## Objective

Complete the supported journey with a clear, actionable readiness summary.

## Scope

Preparation completeness projection · checklist derivation · current-only
assessment selection · unresolved issue filtering · evidence coverage summary ·
print layout.

## Acceptance Criteria

- No stale result appears as current.
- Unresolved blocking issues remain visible.
- The page does not state or imply approval.
- Each issue links back to the affected section.
- Print layout usable; PDF export optional.

---

# Milestone 11 — Evaluation, Security, and Reliability Hardening

**Core slice (pulled into the plan of record — do this before release):**

- AI evaluation suite with **false-reassurance rate** reported.
- Object-level authorisation tests.
- Prompt-injection fixtures passing.
- Storage access and deletion tests (case deletion end to end).
- PII log review.
- WCAG 2.2 AA review of core flows; keyboard-only pass.

**Extended slice:**

- Full fixture suite; regression thresholds; cost and latency reporting.
- Failure injection: worker retries, outbox recovery, failed recalculation,
  storage failure, model timeout, partial extraction.
- Performance budgets: case overview P95, recalculation P95, timeline
  responsiveness, upload responsiveness.
- Screen-reader review, 200% zoom, reduced motion.

## Acceptance Criteria

- Defined AI regression thresholds pass; false-reassurance rate reported.
- Public environment uses synthetic data only.
- No sensitive values in logs or traces.
- Critical accessibility defects resolved.
- Performance budgets met or explicitly documented as missed.

---

# Milestone 12 — Portfolio Polish and Release

## Scope

Final visual polish · synthetic demo reset · stable deployed environment ·
onboarding copy review · consistent loading and error states · responsive pass.

## Documentation

Root README · product case study · architecture overview and diagram · data model
summary · AI evaluation report · threat model summary · key ADRs · setup guide ·
demo script · known limitations.

## Portfolio Assets

Three-to-five-minute demo video (edited from per-milestone captures) · product
overview · technical deep dive · screenshots · architecture diagram · evaluation
chart · one failure-and-recovery example · one explainability example.

## Acceptance Criteria

- A new reviewer understands the product in under two minutes.
- The deployed synthetic demo is reliable and replayable.
- Evaluation results are honest and reproducible.
- Known limitations are visible.
- No private test data in public assets.
- The case study explains rejected alternatives and trade-offs.

---

## 5. Dependency Map

```text
M0 Discovery (thin)
 └── M1 Platform + Deploy
      └── M2 Case Setup
           └── M3A Versioned Inputs
                └── M3B Rules + Assessments        ← architecture proof
                     ├── M4 Explainable Workspace
                     └── M6 Issues + Stale State
                          ├── M5 Timeline + Simulation
                          └── M7 Evidence Foundation
                               └── M8 Human-in-the-Loop AI
                                    └── [release slice §7.2]
                                         └── M9 → M10 → M11 → M12
```

M4 may proceed in parallel with M6 once M3B contracts stabilise.
Do not begin M8 before M3B, M6, and M7 are reliable.

---

## 6. Recommended Delivery Cadence

Six-week flagship, plan of record M0–M8 + release slice.

| Week | Primary focus | Parallel track |
|---|---|---|
| 1 | M0 (thin) · M1 · start M2 | Write rules spec + synthetic case |
| 2 | M2 · M3A | **Throwaway AI spike** (§3.3) |
| 3 | M3B | Design foundations finalised |
| 4 | M4 · M6 | — |
| 5 | M5 · M7 | Write evidence lifecycle + eval plan |
| 6 | M8 · release slice (§7.2) | Case study drafted |

Weeks 7+ are extension, not plan: M9, M10, extended M11, M12 polish.

If time compresses, cut in the order given in §7.3. Never cut deterministic
correctness, explainability, stale-state handling, or evaluation honesty.

---

## 7. Cut Lines

### 7.1 Plan of record

M0 → M8, plus the release slice below. This tells the complete thesis story:
input → deterministic assessment → evidence → AI claim → human confirmation →
trusted fact → stale → recalculation → traceable conclusion.

### 7.2 Release slice (must run before any extension work)

- Core M11: eval suite with false-reassurance rate, authorisation tests,
  prompt-injection fixtures, deletion test, PII log review, accessibility pass.
- Core M12: deployed synthetic demo, README, case study, demo video,
  architecture diagram, known limitations.

**Run this the moment M8 lands.** The project must be shippable before it is
extended.

### 7.3 Cut order

1. PDF export
2. `GuidanceExplainer` / `IssueSummariser` (AI explanation — *not* the guidance registry)
3. Multiple document examples per category
4. Sophisticated evidence coverage visualisation
5. Multiple stored candidate application dates
6. Advanced motion
7. Secondary settings screens
8. Preparation summary print layout

### 7.4 Must not be cut

Claims vs facts · deterministic rules · exact assessment provenance ·
stale-state lifecycle · requirement detail · canonical synthetic case ·
failure and recovery states · guidance registry (rule-to-source links) ·
AI evaluations if live AI ships.

---

## 8. First Implementation Slice

> Create and assess a synthetic Section 6(1) case with versioned travel inputs
> and inspectable residence assessments.

Spans M1 → M3B.

### Scope

Repository foundation · synthetic authenticated user · create supported case ·
confirm route profile · select proposed application date · add confirmed travel
records · run status and residence rules · case overview · one requirement detail
· change one trip · mark result stale · recalculate · show historical and new result.

### Acceptance Criteria

- Complete end-to-end flow works locally **and deployed**.
- No AI is involved.
- Every result references exact input and rule versions.
- Old results remain inspectable.
- Stale state is visible and correct.
- Core tests pass, including Hypothesis date properties.
- The UI follows the agreed visual direction.
- The slice can be shown in a two-minute demo.

This slice is the architecture proof. Everything else is elaboration on it.

---

## 9. Claude Code Task Pattern

### Task header

```text
Milestone:
Vertical slice:
User outcome:
Source docs to read:
```

### Before coding

1. Read the named source documents and `CLAUDE.md`.
2. Inspect the existing implementation.
3. State assumptions explicitly.
4. Identify affected domain modules.
5. Define measurable acceptance criteria.
6. List expected migrations.
7. List expected tests, including any property-based invariants.
8. **Use plan mode and wait for approval** for anything touching the domain
   model, migrations, rules, or the claim→fact→assessment path.

### During coding

Implement the smallest complete slice · keep domain logic framework-independent ·
add tests in the same change · regenerate contracts · include error and recovery
states · preserve observability · update documentation.

### After coding

Report: files changed · migrations added · tests run · commands run · trade-offs
made · known gaps · the next smallest task.

### Context hygiene

Start a fresh session per milestone. Long sessions drift from `CLAUDE.md`; a
compacted context is where invariants quietly get dropped.

---

## 10. Milestone Definition of Done

A milestone is done only when its user journey works, acceptance criteria pass,
the domain model remains consistent, API contracts are generated, tests pass,
empty/loading/error/retry states exist, accessibility has been reviewed, logs and
traces are present, docs are updated, the synthetic case works, demo assets are
captured, and no hidden out-of-scope dependency remains.

A milestone is **not** done because the primary component renders, an endpoint
returns 200, a model produces plausible output, or a happy path worked once.

---

## 11. Change Control

Any new feature must answer: which milestone owns it · which user outcome it
improves · whether it changes the domain model · whether it changes the supported
route · which acceptance criterion requires it · what will be removed or delayed ·
whether it materially improves the portfolio signal.

Default response to scope expansion:

> Defer until the current milestone is complete.

---

## 12. Final Delivery Standard

```text
User enters or imports personal history
→ deterministic rules produce inspectable assessments
→ evidence is uploaded and processed
→ AI proposes structured claims
→ user confirms or corrects them
→ trusted facts update
→ dependent assessments become stale
→ the system recalculates
→ every conclusion remains traceable
→ the user receives a clear preparation summary
```

The finished product should make a founder or hiring manager think:

> This engineer can design, build, evaluate, and ship a sophisticated AI product
> with strong judgement across product, frontend, backend, data, trust, and
> production quality.
