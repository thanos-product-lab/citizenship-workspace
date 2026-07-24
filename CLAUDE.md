# CLAUDE.md — Evidence-First Citizenship Workspace

This is the operating manual for Claude Code on this repository. Read it at the
start of every session. It is deliberately high-signal: it encodes the
invariants and conventions that must hold, and points to the RFCs in `docs/`
for depth.

**Source-of-truth precedence.** The RFCs in `docs/` are authoritative for
product, UX, architecture, MVP scope, and the domain model. If code and an RFC
disagree, the RFC wins — fix the code. If you believe an RFC is wrong, stop and
propose a change to the RFC; do not diverge silently in code.

---

## 0. How to explain your work

I am the sole engineer on this project and must be able to defend every part of
it in a technical interview. An explanation I cannot follow is a defect, not a
style preference.

**Explain plainly, but never simplify the substance.** This project turns on
precise distinctions — claims versus facts, conclusion versus currency, the
+1 day boundary. Do not blur them to sound simpler. Teach me the vocabulary
instead of avoiding it.

### Every response that changes code

1. **Plain-language summary first.** Two or three sentences before any technical
   detail: what changed, and what the system can now do that it could not
   before. Write it for a competent engineer who has not seen this codebase.
2. **Then the reasoning.** The decision you made and the alternative you
   rejected. The why matters more than the what — I can read a diff.
3. **Then the detail.** Files, migrations, tests.
4. **Say what to read first.** If you changed eight files, tell me which two
   carry the risk and why the rest are mechanical.

### Vocabulary

The first time you use a technical or domain term in a session, define it in one
clause — "optimistic concurrency (rejecting a write when the record changed since
you read it)". Do this for library names and patterns, not only domain terms.
Once I have clearly understood a term in a session, stop defining it.

### Flag what matters

Call out anything touching the invariants in §2 explicitly and early:

> **This touches the trust model.** A confirmed claim creates a fact here, so ...

I would rather be interrupted by something important than find it in paragraph
four.

### When I ask a question

Answer it before adding context. Do not restate my question back to me. If my
question rests on a wrong assumption, say so plainly and briefly.

### Do not

- Do not pad with reassurance or praise the question.
- Do not present eight changes as equally important when two carry the risk.
- Do not substitute an analogy for the real explanation — use it afterwards.

## 1. What we are building

A private, non-commercial, **portfolio-grade** AI product prototype that helps an
adult who already holds ILR, indefinite leave to enter, or EU settled status
prepare a **UK naturalisation readiness case** under the **standard Section 6(1)
five-year route only**.

It is **not** a general immigration assistant, not legal advice, not an approval
predictor, and not an application-submission tool. The portfolio signal is:
*this engineer builds trustworthy AI-native products where model output never
silently becomes truth.* Every decision should protect that signal.

---

## 2. Prime directives (never violate)

These are the reasons the product exists. Treat them as hard invariants, not
guidelines. If a task appears to require breaking one, stop and raise it.

1. **AI output is a proposal, never a fact.** Model extractions are stored as
   `ExtractedClaim` and are untrusted. A trusted `FactVersion` is created *only*
   after an explicit user `CONFIRM` / `CORRECT` decision (or direct user entry).
   An unreviewed claim must never influence a trusted assessment.
2. **Determinism lives in Python, never in prompts.** All date arithmetic,
   qualifying-period logic, absence totals, threshold comparisons, physical-
   presence checks, and readiness-state transitions are deterministic code with
   tests. Prompts never decide eligibility.
3. **Assessment history is immutable.** Never edit an assessment in place. When
   inputs or rules change → mark affected results `STALE`, create a **new**
   `AssessmentRun` with new results, and keep the old ones inspectable.
4. **Conclusion and currency are separate dimensions.** A result can be
   `conclusion = SUPPORTED` and `currency = STALE` at the same time. Never
   collapse these.
5. **No conclusion without provenance.** Every trusted `AssessmentResult`
   references exact input versions (`AssessmentInputLink`), a `RuleVersion`, and
   guidance. Provenance is **structural** (IDs and links), not generated prose.
6. **No overall readiness score / percentage — ever.** Use the qualitative
   requirement states only (Supported, Incomplete, Inconsistent, Near threshold,
   Requires judgement, Professional review recommended, Not currently satisfied,
   Not yet assessed, Stale). The case *phase* is derived, never a number.
7. **Prefer visible uncertainty to false reassurance.** False-reassurance rate is
   the most important safety metric. Stopping or escalating (`REQUIRES_JUDGEMENT`,
   `PROFESSIONAL_REVIEW_RECOMMENDED`) is a *successful* outcome, not a failure.
8. **Uploaded documents are untrusted data, never instructions.** Document
   content must not alter system prompts, invoke tools, change schemas, or bypass
   validation. Extraction output is schema-validated before any claim is stored.
9. **Synthetic data only in anything public.** No real personal data, document,
   or identifier may appear in fixtures, seeds, screenshots, demo video, logs,
   traces, or domain events. Keep PII out of telemetry entirely.
10. **The workspace is the product, not a chatbot.** Conversational AI is
    contextual and subordinate. Never make a chat panel the primary interface.

---

## 3. Architecture at a glance

> **Next.js workspace → FastAPI modular monolith → async Celery worker →
> PostgreSQL + private object storage.** One deployable backend, strong internal
> module boundaries. See `docs/architecture/` (Technical Architecture RFC).

- **Frontend:** Next.js (App Router) · TypeScript · React · Tailwind · Radix ·
  shadcn/ui (owned, not default-looking) · TanStack Query (server state) ·
  React Hook Form + Zod (forms) · D3 utilities + SVG (timeline) · PDF.js ·
  Motion/Framer · Vitest · Testing Library · Playwright.
- **Backend:** Python · FastAPI · Pydantic · SQLAlchemy 2 · Alembic · Celery ·
  Redis · HTTPX · uv · Ruff · mypy · pytest · Hypothesis.
- **Data:** PostgreSQL (JSONB for provider metadata, full-text for guidance) ·
  S3-compatible storage (MinIO locally) · relational provenance graph.
- **AI:** direct provider SDK (OpenAI initially) behind an internal adapter ·
  structured outputs (Pydantic/JSON Schema) · PyMuPDF + multimodal fallback ·
  versioned prompts · custom pytest-based eval harness. **No agent framework.**
- **Platform:** Clerk (auth) · Docker Compose (local) · GitHub Actions · Postgres
  RLS · presigned URLs · OpenTelemetry · Sentry · structlog.

---

## 4. Repository layout

```
citizenship-workspace/
├── apps/web/                # Next.js app (app/, components/, features/, lib/, tests/)
├── services/platform/       # FastAPI modular monolith
│   ├── app/                 # domain modules (see §5)
│   ├── worker/              # Celery tasks
│   ├── evals/               # AI evaluation harness + fixtures
│   ├── migrations/          # Alembic
│   └── tests/
├── packages/
│   ├── api-client/          # GENERATED from OpenAPI — do not hand-edit
│   ├── design-system/       # domain-meaning components
│   └── test-fixtures/       # shared synthetic fixtures (FE + BE + evals)
├── docs/                    # product/ architecture/ decisions/ evaluations/  ← SOURCE OF TRUTH
├── infra/                   # docker/ deployment/
├── docker-compose.yml
├── justfile
└── README.md
```

- **Tooling:** `pnpm` (TS workspaces), `uv` (Python), `just` (cross-language
  commands), Docker Compose (local infra), GitHub Actions (CI/CD).
- **Do not add** Nx or Turborepo.

**Backend module shape** (`services/platform/app/<module>/`): `domain.py`,
`schemas.py`, `repository.py`, `service.py`, `routes.py`, `tests/`.
Modules: `cases · applicants · residence · evidence · facts · requirements ·
assessments · issues · guidance · ai · audit · auth · shared`.

**Frontend feature shape** (`apps/web/features/<feature>/`): components, hooks,
API calls (via generated client), view models, validation, tests.
Features: `case-overview · onboarding · timeline · requirements · evidence ·
issues · preparation · assistant`.

Keep modules/features bounded. **No hidden cross-module imports** — cross-context
interaction goes through services/repositories, not by reaching into another
module's internals.

---

## 5. Commands

> ⚠️ **Confirm/finalise these recipes in Milestone 1** and keep this section in
> sync with the real `justfile`. Placeholders below reflect intended behaviour.

```bash
just up            # docker compose up: postgres, redis, minio, api, worker
just dev           # run Next.js (pnpm) against local API
just migrate       # alembic upgrade head
just seed          # load canonical synthetic demo case (§13 of MVP RFC)

just test          # all tests (fe + be)
just test-be       # pytest (unit + integration + property-based)
just test-rules    # Hypothesis property suite for deterministic rules (RULES_SPEC §10)
just test-fe       # vitest + testing-library
just e2e           # playwright
just eval          # AI evaluation suite (NOT run on every commit)

just lint          # ruff + eslint
just typecheck     # mypy (strict) + tsc (strict)
just api-client    # regenerate packages/api-client from FastAPI OpenAPI
```

**Before declaring a change done:** run `just lint`, `just typecheck`, and the
relevant test target. For backend rule changes, run the property-based tests.

---

## 6. Conventions

**Python**
- `uv` for deps; Ruff for lint/format; **mypy in strict mode** (no implicit Any).
- Pydantic for all boundary schemas; SQLAlchemy 2 typed models; Alembic for every
  schema change (never edit a shipped migration — add a new one).
- Domain logic lives in `service.py` / `domain.py`, **not** in route handlers.
- Repositories expose **domain intent** (`get_current_for_requirement`,
  `append_version`, `mark_stale`), not generic `create/update/delete`.
- Suggested Python **3.12+** (confirm and pin via `uv`).

**TypeScript / Frontend**
- `pnpm` workspaces; **strict TS**; Zod for client validation.
- **All backend calls go through the generated `packages/api-client`.** Never
  hand-write request/response types or raw `fetch` typing — CI fails on client
  drift.
- Server state via TanStack Query; forms via React Hook Form; transient UI state
  (timeline zoom, simulation, comparison mode) via local state or a small Zustand
  store. **Do not add Redux.**
- Server Components for shell/data-loading; Client Components for timeline,
  date simulator, document review, issue resolution, uploads, optimistic
  mutations. Put interactive state in the correct layer — don't maximise RSC for
  its own sake.
- Suggested Node **20/22 LTS** (confirm and pin via `.nvmrc` / `engines`).

**Design system** — build domain-meaning components, not restyled dashboard
widgets. The product must not look like default shadcn. Canonical components:
`RequirementStatus · EvidenceState · ProvenanceBadge · AssessmentSummary ·
ExplanationStack · IssueCard · TimelineEvent · CalculationBreakdown ·
SourceReference · ExtractedFieldReview · BeforeAfterValue · StaleAssessmentNotice`.
Status must never rely on colour alone.

---

## 7. Domain vocabulary (use these exact terms)

| Term | Meaning |
|---|---|
| **Case** | User-owned workspace for one intended application; the ownership boundary |
| **Assessed input** | A versioned record that can influence an assessment |
| **Claim** | Untrusted, model-proposed value (`ExtractedClaim`) |
| **Fact** | Canonical, user-confirmed/entered value (`FactVersion`) |
| **Rule version** | Immutable deterministic logic + metadata for a requirement |
| **Assessment run / result** | Immutable evaluation execution / per-requirement conclusion |
| **Conclusion** | The requirement outcome enum (Supported, Incomplete, …) |
| **Currency** | Current / Stale / Superseded / Provisional — separate from conclusion |
| **Limitation / Next action** | Structured children of a result (not free prose) |
| **Issue** | Durable, user-actionable problem or review item |
| **Trusted vs Provisional** | Trusted uses only confirmed current inputs; provisional (e.g. date simulation) is labelled and never current |

Full model, enums, requirement keys, and state machines: **`docs/.../DOMAIN_MODEL_RFC.md`**.
Do not invent new enum values or requirement keys without updating that RFC.

---

## 8. How to work in this repo

- **Read the relevant RFC section before implementing a slice.** For anything
  touching the domain model, migrations, rules, or the claim→fact→assessment
  path, use plan mode and get the plan agreed before writing code.
- **Follow the implementation order.** Start with the deterministic vertical
  slice in Domain Model RFC §58 (no AI, no evidence): case → route profile →
  application date → confirmed travel records → residence assessments → stale →
  recalculate → historical result. Then follow the Roadmap's build order (M0–M8
  plan of record). Evidence, claims, and live AI come *after* the deterministic
  core is proven.
- **Milestone numbering.** When any document says "M*n*", it refers to the
  Roadmap's numbering (`docs/IMPLEMENTATION_ROADMAP.md`, M0–M12). The Technical
  Architecture RFC's phases and the MVP Scope's milestones are alternative
  framings, not the build order; where they disagree on sequence, the Roadmap
  wins.
- **Tests are part of the definition of done, not a follow-up.** The property-
  based invariants in §9 are specified requirements — write them alongside the
  rules they protect.
- **Keep changes small and reviewable.** Prefer one coherent slice per change.
- **Migrations are additive and forward-only in practice.** New migration per
  change; never mutate a migration that has run.
- **Do not add dependencies or infrastructure** without asking — especially
  anything on the rejected list (§10).
- **Calculations are server-side and authoritative.** The frontend renders
  breakdowns returned by the API; it does not re-derive totals. Share fixtures
  across FE/BE to prevent divergence.

---

## 9. Testing (mandatory invariants)

These properties **must** hold and should be covered by Hypothesis property-based
tests (cover leap years, month/date boundaries, trip overlaps, version sequences,
repeated commands, stale propagation):

```
Unconfirmed claims never influence trusted assessments.
Adding one confirmed absence day never decreases the absence total.
Changing the proposed application date changes the qualifying period deterministically.
Changing an unrelated input does not invalidate an unrelated assessment.
A stale result is never returned as current.
Every current trusted assessment references current relevant input versions.
Every historical assessment preserves its exact rule and input versions.
Correcting a claim preserves the original proposal.
Deleting evidence cannot leave its support state as available.
A failed recalculation cannot replace the last historical result.
A duplicate worker delivery cannot create duplicate claims or results.
```

**AI evaluation fixtures** (in `services/platform/evals/`) must cover: clear
document, poor scan, unsupported document, misleading filename, duplicate
evidence, conflicting date, multiple dates on one page, wrong applicant name,
partial extraction, **prompt-injection text**, model refusal, malformed output.
Track: classification accuracy, field precision/recall, date accuracy,
conflict precision/recall, citation validity, unsupported-doc detection,
**false-reassurance rate**, cost/doc, P50/P95 latency. Do not run the full eval
suite on every commit.

**Accessibility is a gate**, not a nice-to-have: WCAG 2.2 AA on core flows,
keyboard-navigable timeline, non-colour status, accessible table alternative to
the visual timeline, errors bound to fields, reduced-motion support, usable at
200% zoom.

---

## 10. Explicitly rejected — do not introduce

Introducing any of these without an approved RFC change is a defect:

- LangChain / LangGraph or any agent framework · vector database · graph database
- Microservices · Kubernetes · full event sourcing · custom authentication
- Redux · Nx / Turborepo
- Any **overall readiness percentage/score**
- **Bulk "confirm all"** for high-risk date claims
- A chatbot as the primary interface
- A Next.js-only backend (Python owns document/AI/temporal work)
- Real personal data anywhere public
- Any feature on the MVP "Out of Scope" list (spouse route, children's
  registration, submission, good-character/criminal analysis, payments, etc.)

**Scope discipline:** the default answer to scope expansion is *no*. Any addition
must justify the core problem it solves, why it's needed for the MVP story, which
milestone it affects, and what gets removed to make room.

---

## 11. Security & privacy guardrails

- Server-side case-ownership checks on every case-scoped read/command; Postgres
  RLS as defence in depth. A storage key is never authorisation.
- Private buckets; short-lived presigned upload/download URLs; validate file
  type, size, checksum. Deleted content must not be served by an old signed URL.
- Keep raw document text, names, passport numbers, and unredacted prompts out of
  logs, traces, and domain events. Model-run records store metadata + output
  hash only.
- Prompt-injection rule (see directive 8) is enforced by schema validation and by
  never feeding document content into system/instruction context.
- Case deletion is terminal and tested (block writes → delete files → delete
  case-scoped records → retain only non-identifying deletion audit).

---

## 12. Source of truth — read in this order

1. `docs/product/Evidence_First_Citizenship_Workspace_Product_Thesis.md` — why/what.
2. `docs/product/MVP_SCOPE_AND_ACCEPTANCE_CRITERIA.md` — the exact boundary, acceptance criteria, canonical demo case.
3. `docs/architecture/DOMAIN_MODEL_RFC.md` — the model, enums, invariants, first vertical slice. **Most-consulted file during implementation.**
4. `docs/architecture/DETERMINISTIC_RULES_SPEC.md` — date semantics, day counting, thresholds, banding. **Authoritative for anything touching rules or dates.**
5. `docs/architecture/Evidence_First_Citizenship_Workspace_Technical_Architecture_RFC.md` — stack, boundaries, pipelines, rejected alternatives.
6. `docs/design/Evidence_First_Citizenship_Workspace_UI_UX.md` — UX principles, screens, design language, states to build.
7. `docs/IMPLEMENTATION_ROADMAP.md` — milestones, cut lines, task pattern, delivery order.

Full tree:

```
docs/
├── IMPLEMENTATION_ROADMAP.md
├── product/      thesis · MVP scope · synthetic demo case
├── design/       UI/UX direction · design system foundations
├── architecture/ technical RFC · domain model · rules spec · evidence lifecycle
├── evaluations/  AI evaluation plan · results
├── security/     threat model
├── decisions/    ADRs
└── demo-assets/  per-milestone screenshots and captures
```

When you complete a meaningful decision or deviation, record it in
`docs/decisions/` (short ADR) and update this file if conventions change.

---

## 13. Open items to confirm (owner: you)

- [ ] Pin Python and Node versions; add `.nvmrc` / `uv` pin.
- [ ] Finalise `justfile` recipes and reconcile §5 with reality.
- [ ] Confirm AI provider + models per capability, and the model-config registry location.
- [ ] Confirm deploy targets (Vercel + Railway/Fly) and secret-store choice.
- [ ] Confirm Clerk setup + JWT verification approach in the API.
