# Release gate audit

> **Captures cited below** (`m4-*.jpg`, `m6-*.gif` and so on) were retired from the working
> tree in September 2026. Read any of them from git history, for example
> `git show a37b05a:docs/demo-assets/m4-case-overview.jpg > m4-case-overview.jpg`.

**Date:** 19 September 2026 · **Scope:** MVP §15's thirty seven gate items and §16's twelve
done conditions · **Build:** `de95f0b`, equal to `origin/main`

**Result: 31 pass, 3 partial, 3 gaps.** (§16 condition 8 has since moved to pass.) The three gaps are the demo video, the case study
and the preparation summary. Two of those are writing rather than engineering. The third is
outside the plan of record.

One item failed when the audit started and was fixed during it: the UI/UX design document
contained a real person's name in a mockup of the document review screen.

## How to read this

Rules held to while writing it:

- Nothing passes because it was planned, specified or given an ADR. A pass names a test, a
  file, a capture, or something observed running.
- A test that exists but has never run against the deployed environment is not a pass. It is
  recorded as what it is.
- "Partial" means the item is genuinely half met, not that it is nearly met.

## Product gate

| Item | Verdict | Evidence |
|---|---|---|
| The full supported journey works | **Partial** | 14 of MVP §14's 15 steps run. Driven deployed on 13 September and locally since; `docs/DEMO_SCRIPT.md` records the click path and which steps need setup. Step 15 has no screen. That walkthrough found four defects, all fixed in `53dc1f0`. |
| The product does not rely on a chatbot | **Pass** | There is no chat surface in the product. `apps/web/features/` holds nine features and none of them is an assistant. Verifiable by absence. |
| The explainability model is visible | **Pass** | The requirement detail renders eight real headings, confirmed in the browser: why this assessment was made, facts used, travel records used, evidence used, rule used, limitations, next action, assessment history. `m4-explanation-stack.jpg`. Reordered on 23 September 2026 (commit `80f3930`) to lead with limitations and next action; every layer is still open and still a heading, empty ones stated in one line. |
| Unsupported routes stop safely | **Pass** | `tests/applicants/test_confirm.py::test_spouse_route_is_stopped_in_draft` and `::test_unsupported_status_is_stopped`. |
| The final preparation summary is coherent | **Gap** | It does not exist. M10, outside the M0 to M8 plan of record. `KNOWN_LIMITATIONS.md`. |

## UX gate

| Item | Verdict | Evidence |
|---|---|---|
| The overview is calm and understandable | **Pass** | `m4-case-overview.jpg`. The walkthrough found it was a dead end on a *new* case, stating a fact and offering no next step; `GettingStarted` was added and is covered by five tests in `CaseOverviewPanel.test.tsx`, including one asserting no score or fraction appears. |
| The requirement detail is portfolio quality | **Pass** | `m4-explanation-stack.jpg`, `m4-assessment-history-439-to-440.jpg`. |
| The timeline is usable and accessible | **Pass** | Audited in Chrome: a real `<table>` with a caption, every `th` scoped, twelve rows, and the visual band `aria-hidden` with nothing focusable inside it. `m5-timeline-table.png`. |
| AI proposals and confirmed facts are visually distinct | **Pass** | `m8-slice3b-your-value-won.jpg`, opened and checked during this audit: three fields carry an "AI proposed" badge, the corrected one carries "Corrected" plus "What we read, and what you read", showing `11 May 2026 → 2026-05-10`. |
| Error and recovery states are implemented | **Pass** | `m6-slice4-failed-recalculation.gif` and `m7-slice5-failed-deletion.gif`, both captured against deliberately broken paths. |
| The product does not resemble a default shadcn dashboard | **Pass** | It cannot: shadcn and Radix are not installed. `apps/web/package.json` lists Clerk, TanStack Query, Next and React, plus the workspace's own `@cw/design-system`. See the note below. |

**A stack deviation, since recorded.** `CLAUDE.md` §3 and the architecture RFC named Radix
and shadcn/ui as the component layer. Neither is a dependency and neither ever was. Closed
by ADR-0031, which records the substitution, what it bought, and what it cost: the modal
shell's focus trap is ours to test, and Radix would have supplied a correct one. Both
documents are amended.

## Engineering gate

| Item | Verdict | Evidence |
|---|---|---|
| Deterministic rules are fully tested | **Pass** | 21 property tests under `pytest -m property`, across `tests/rules/` and `tests/assessments/test_invalidation_completeness.py` and `test_simulation.py`. Run green on 13 September. |
| Claims and facts are separate | **Pass** | Separate tables, separate modules, and the rules engine has no parameter a claim can arrive through. `tests/assessments/test_provenance_resolution.py::test_an_unconfirmed_trip_is_marked_as_not_counting`. |
| Assessment history is immutable | **Pass** | Migration `0032` revokes `UPDATE` on the claim and fact tables outright, so it is a privilege rather than a convention. `m4-assessment-history-439-to-440.jpg` shows a superseded run still readable. |
| Stale propagation works | **Pass** | ADR-0014, the invalidation completeness property suite, and `m6-slice1-selective-invalidation.gif` showing four conclusions going stale and a fifth correctly not. |
| OpenAPI client generation works | **Pass** | `just api-client` run during this audit produced no diff. CI carries a `contract` job that fails on drift. |
| Background tasks are idempotent | **Pass** | `tests/evidence/test_processing.py::test_a_duplicate_delivery_creates_no_second_run`, `tests/evidence/test_deletion.py::test_a_redelivered_purge_changes_nothing`, `tests/cases/test_case_purge.py::test_a_second_purge_finds_nothing_to_do`. |
| CI passes | **Partial** | Every gate green locally on this build: 1128 backend tests, 417 frontend, 21 property, ruff, `ruff format --check`, mypy strict, tsc strict, eslint. `HEAD` equals `origin/main`, so CI has had the commit, but the run status was not checked because the GitHub CLI is not installed on this machine. Confirm before release. |

## AI gate

| Item | Verdict | Evidence |
|---|---|---|
| Structured outputs are validated | **Pass** | Pydantic schemas at the provider boundary; a refusal is handled as a verdict rather than an error (`tests/ai/test_provider_retries.py::test_a_refusal_stops_immediately`). |
| Evaluation fixtures exist | **Pass** | 17 fixtures across three manifests, five capabilities. |
| False reassurance is measured | **Pass** | 0.0%, 0 of 16 measured (the 11 September run in `EVAL_REPORT.md` §13). Read with §3 of `EVAL_REPORT.md`, which names the fixture classes the corpus omits. |
| Prompt injection fixtures pass | **Pass** | Three fixtures, one per extractor family, all passing. The report also records that one of them graded no authority channel until a security review caught it. |
| Costs and latency are recorded | **Pass** | Recorded per provider call on `model_runs`. Measured during this audit over 98 successful runs: **p50 927ms, p95 2837ms, max 3051ms, total cost $0.0169**. Recorded is not the same as reported: the eval harness does not surface percentiles, which is a reporting gap rather than a missing measurement. |
| AI output cannot bypass user confirmation | **Pass** | The trust boundary in `ARCHITECTURE_OVERVIEW.md`, carried by a type signature. Blind entry sends `proposed_value` as null for high risk claims; `DocumentReview.test.tsx` asserts no date shaped string appears anywhere on the panel. |

## Security gate

| Item | Verdict | Evidence |
|---|---|---|
| Public demo contains no real personal data | **Pass, after a fix** | This item **failed** when the audit began. `docs/design/…_UI_UX.md` line 714 carried a real person's name inside a mockup of the document review screen, presented as an extracted name beside a test result and level. Replaced with the synthetic identity. A repository wide search for that name, the account email and the Clerk user id now returns nothing, and `m8-slice3b-your-value-won.jpg` was opened and checked: the traveller name reads `OKONKWO / AMARA MS`. |
| Ownership checks pass | **Pass** | `tests/cases/test_ownership.py`, plus `tests/security/test_rls_matrix.py`, `test_rls_coverage.py` and `test_rls_login_role.py`, which drive the non superuser role so a forgotten tenant fails closed. |
| Storage is private | **Pass** | `test_an_object_is_not_readable_without_a_signature` against real MinIO, green on 13 September. Confirmed against the live bucket during this slice: an unauthenticated GET returns `403 AccessDenied`. |
| Presigned URLs expire | **Pass** | `test_a_presigned_url_stops_working_when_it_expires` and `test_an_old_signed_url_cannot_reach_a_deleted_object`, both against real MinIO. |
| Logs do not contain sensitive payloads | **Pass** | Reviewed two ways during this audit. Statically: an AST pass over every `_log` call in `app/` and `worker/` found 67 distinct field names, all identifiers, counts, enums and booleans. No `filename`, `display_name`, `title`, `text`, `proposed_raw`, `checksum` or `storage_key` is bound anywhere. Two fields named for credentials log `bool(...)`, presence not value. At runtime: 276,952 lines of real API and worker output, covering document processing, searched for the synthetic case's names, filenames, booking reference, document text, checksums, JWTs and signed URLs. **Zero hits.** Residual noted below. |
| Complete case deletion is tested | **Pass** | Fourteen tests in `tests/cases/test_case_purge.py`, including one deriving the case scoped table set from the live schema so a later migration cannot silently escape it. Verified against the running stack: 11 objects gone from MinIO, 166 rows, 80 events, 22 hashes scrubbed. `m11-case-deletion-completes.txt`, ADR-0030. |

**Residual, accepted.** Four sites log `str(exc)[:300]` from infrastructure health checks:
bucket unavailable, database connect, superuser probe, Redis ping. None sits on a path that
handles user content, the engine is built with `hide_parameters=True` so bound values never
render, and a connection error can name a host and a role but not a document. The auth
rejection path logs an exception string too, scoped to `PyJWTError` and `PyJWKClientError`,
which describe a failure type rather than a token.

**Also observed.** Uvicorn's access log records full request paths. Every case scoped route
is built from UUIDs, so those lines carry identifiers and no personal data. That is a
property of the route design rather than of the logger, and it is the reason personal data
never goes in a query string.

## Portfolio gate

| Item | Verdict | Evidence |
|---|---|---|
| The application is deployed | **Pass** | Web on Vercel, API on Railway, both answering. `/health/ready` reports database, Redis and provider configuration true. The CSP and the bucket CORS policy were both wrong and were fixed during this slice; the preflight now returns 200 for POST and GET from the Vercel origin. |
| README is complete | **Pass** | Rewritten in `a7234e1`. It had said the build stopped at M6 for two milestones. |
| Architecture diagram is published | **Pass** | `docs/architecture/ARCHITECTURE_OVERVIEW.md`, `de95f0b`. Three diagrams, rendered and checked rather than assumed. |
| Evaluation results are documented | **Pass** | `EVAL_REPORT.md` plus five dated run records, including the two that failed the gate at 11.1% and 18.2%. |
| Demo video is recorded | **Gap** | Not started. Most shots exist as captures; two need recording. |
| Product case study explains key decisions and rejected alternatives | **Gap** | Yours to write. The raw material is 29 ADRs and 1674 lines of milestone notes. |
| The synthetic case can be reset and replayed reliably | **Partial** | It can be replayed: seeding is one command and produces identical figures every time. It cannot be *reset*: re-seeding creates a second case rather than replacing the first, and seeding the deployed environment needs container console access. Documented in `DEMO_SCRIPT.md`. |

## MVP §16, the twelve done conditions

| # | Condition | Verdict |
|---|---|---|
| 1 | A supported synthetic user can complete the full journey | **Partial**, 14 of 15 |
| 2 | A supported real tester can use the private environment without developer intervention | **Partial**. A tester can sign up and build their own case unaided, which the application date fix made possible. The canonical demo case still needs a developer to seed it. |
| 3 | Deterministic calculations are correct across the test suite | **Pass** |
| 4 | Every current assessment is traceable to exact facts, evidence and a rule version | **Pass** |
| 5 | AI proposed values require explicit confirmation | **Pass** |
| 6 | Fact changes create stale assessments and new immutable results | **Pass** |
| 7 | At least four document categories can be processed or safely rejected | **Pass**. Three go end to end; immigration status is classified and safely handled without an extractor (ADR-0029). The classifier also has fixtures for declining, covering unsupported and ambiguous. |
| 8 | Core screens meet the accessibility and responsive standard | **Pass**. `ACCESSIBILITY_PASS.md`: five flows audited, skip link added, both findings now closed. Reflow measured at 320px and 640px across seven destinations, which found and fixed a real overflow on the Evidence page. |
| 9 | The full demo flow works reliably in the deployed environment | **Partial**. Driven once end to end after the CSP and CORS fixes. One clean run is evidence; it is not yet reliability. |
| 10 | CI, observability, security controls and evaluation reporting are operational | **Partial**. CI, security controls and evaluation reporting yes. Observability is structured logging with a per request trace id and nothing else: no OpenTelemetry and no Sentry, both of which `CLAUDE.md` §3 names. |
| 11 | All explicit quality gates pass | **No**, by this audit |
| 12 | No out of scope feature is required to tell the product story | **Pass** |

## What has to happen before release

Ordered by what blocks the story rather than by effort.

1. **Record the demo video.** The largest remaining gap and the one a reviewer meets first.
2. **Write the case study.** Yours. The evidence is assembled.
3. **Confirm CI is green on `de95f0b`.** One look at the Actions tab.
4. ~~Finish the accessibility work.~~ Done: reflow measured and one overflow fixed, the
   `h1` resolved.
5. ~~Add the ADR for the design system substitution.~~ ADR-0031.
6. ~~Finish `KNOWN_LIMITATIONS.md`.~~ Twenty entries.

Not blocking, and worth saying out loud in the case study rather than fixing: the
preparation summary, observability beyond structured logs, and cross checking extracted
values other than dates.

## What this audit could not verify

- **The review split view at 320px.** Every other destination was measured. This one
  detaches the renderer when nested in a probe frame, because it embeds the document viewer
  and that ends up two PDF frames deep. Verified from its CSS instead, which handles the
  case deliberately: `minmax(0, 1fr)` with a comment naming this exact failure, a `60rem`
  breakpoint collapsing to one column, and `width: 100%` on the frame.
- **The CI run status** for this build, for want of the GitHub CLI here.
- **Deployed reliability over time.** The demo has been driven correctly once since the CSP
  and CORS fixes.
