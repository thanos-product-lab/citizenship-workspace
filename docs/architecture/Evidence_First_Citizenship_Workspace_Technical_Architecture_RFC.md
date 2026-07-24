# Evidence-First Citizenship Workspace

## Technical Architecture and Stack RFC

### Status

Accepted for initial implementation  
Version: 0.1  
Project: Evidence-First Citizenship Workspace  
Initial route: UK naturalisation under Section 6(1) for adults who already hold ILR, indefinite leave to enter, or EU settled status

---

## 1. Decision Summary

The product will use:

> **Next.js product workspace + FastAPI modular monolith + asynchronous Python worker + PostgreSQL + private object storage**

The architecture is intentionally designed as a modular monolith rather than a microservice platform.

The system must support:

- deterministic citizenship rules;
- AI-assisted document understanding;
- human confirmation of extracted claims;
- evidence provenance;
- temporal reasoning;
- immutable assessment history;
- strong observability;
- production-quality deployment;
- a polished, accessible frontend.

The initial implementation will not use:

- microservices;
- Kubernetes;
- LangChain;
- LangGraph;
- a vector database;
- a graph database;
- full event sourcing;
- a custom authentication system.

---

## 2. Architectural Goals

The architecture should demonstrate strong product-engineering judgement rather than infrastructure complexity for its own sake.

The system must:

1. Keep deterministic rules separate from AI behaviour.
2. Prevent unconfirmed AI output from becoming trusted case facts.
3. Preserve the provenance behind every assessment.
4. Recalculate affected requirements when facts change.
5. Process uploaded documents asynchronously.
6. expose meaningful processing states to the frontend.
7. support synthetic evaluations and regression testing.
8. treat personal data and uploaded documents carefully.
9. remain small enough to build and polish within the programme.
10. provide a credible path toward production without pretending to operate at enterprise scale.

---

## 3. Core Architectural Principle

> AI output is always a proposal until a user confirms or corrects it.

The data flow is:

```text
Document uploaded
      ↓
File validated
      ↓
Text and visual content extracted
      ↓
AI proposes structured claims
      ↓
Deterministic validation runs
      ↓
User confirms or corrects claims
      ↓
Trusted case facts are created
      ↓
Dependent requirements are reassessed
      ↓
A new immutable assessment result is stored
```

This separation is central to the product's trust model.

---

## 4. High-Level System Architecture

```text
┌──────────────────────────────────────────────────────────────┐
│                         Web Browser                          │
│                                                              │
│  Case workspace · Timeline · Evidence review · Explanations │
└──────────────────────────────┬───────────────────────────────┘
                               │ HTTPS / REST / SSE
                               ▼
┌──────────────────────────────────────────────────────────────┐
│                    Next.js Web Application                  │
│                                                              │
│  App Router · Authentication · Workspace shell              │
│  Server rendering · Client interactions · API client        │
└──────────────────────────────┬───────────────────────────────┘
                               │ Authenticated API requests
                               ▼
┌──────────────────────────────────────────────────────────────┐
│                    FastAPI Modular Monolith                 │
│                                                              │
│  Cases             Residence          Evidence              │
│  Requirements      Assessments        Guidance              │
│  Issues            Audit              AI orchestration      │
└───────────────┬────────────────────┬─────────────────────────┘
                │                    │
                ▼                    ▼
┌───────────────────────┐   ┌──────────────────────────────────┐
│      PostgreSQL       │   │       Private Object Storage     │
│                       │   │                                  │
│ Cases · facts         │   │ PDFs · images · derived previews │
│ evidence metadata     │   │ encrypted · temporary access     │
│ assessments · audit   │   │                                  │
└───────────────────────┘   └──────────────────────────────────┘
                │
                ▼
┌──────────────────────────────────────────────────────────────┐
│                    Redis + Celery Worker                    │
│                                                              │
│ Validation · Text extraction · AI extraction                │
│ Conflict detection · Preview generation · Retry handling    │
└──────────────────────────────┬───────────────────────────────┘
                               │
                               ▼
┌──────────────────────────────────────────────────────────────┐
│                      AI Provider Layer                      │
│                                                              │
│ Classification · Structured extraction · Explanation        │
│ Provider adapters · Prompt versions · Model-run records      │
└──────────────────────────────────────────────────────────────┘
```

---

## 5. Recommended Technology Stack

### 5.1 Frontend

| Responsibility | Technology |
|---|---|
| Framework | Next.js App Router |
| Language | TypeScript |
| UI runtime | React |
| Styling | Tailwind CSS |
| Accessible primitives | Radix UI |
| Component foundation | shadcn/ui, customised and owned |
| Server state | TanStack Query |
| Form state | React Hook Form |
| Client validation | Zod |
| Timeline scales | D3 utilities |
| Timeline rendering | React + SVG |
| PDF rendering | PDF.js |
| Motion | Motion / Framer Motion |
| Unit tests | Vitest |
| Component tests | Testing Library |
| End-to-end tests | Playwright |

### 5.2 Backend

| Responsibility | Technology |
|---|---|
| Language | Python |
| API framework | FastAPI |
| Runtime schemas | Pydantic |
| ORM | SQLAlchemy 2 |
| Database migrations | Alembic |
| Background jobs | Celery |
| Queue and cache | Redis |
| HTTP client | HTTPX |
| Dependency management | uv |
| Linting and formatting | Ruff |
| Static typing | mypy |
| Unit and integration tests | pytest |
| Property-based tests | Hypothesis |

### 5.3 Data and Storage

| Responsibility | Technology |
|---|---|
| Primary database | PostgreSQL |
| Flexible provider metadata | JSONB |
| Guidance search | PostgreSQL full-text search |
| Document storage | Amazon S3 or compatible private storage |
| Local object storage | MinIO |
| Cache and queue | Redis |
| Evidence graph | Relational tables and joins |
| Vector retrieval | Not included initially |

### 5.4 AI Layer

| Responsibility | Technology |
|---|---|
| Initial provider | OpenAI API |
| Integration | Direct provider SDK behind internal adapter |
| Structured results | Pydantic / JSON Schema |
| Native PDF text extraction | PyMuPDF |
| Scan fallback | Multimodal model input |
| Prompt registry | Version-controlled prompts |
| Evaluations | Custom pytest-based evaluation harness |
| Retrieval | Curated guidance lookup |
| Agent framework | None initially |

### 5.5 Authentication and Security

| Responsibility | Technology |
|---|---|
| Authentication | Clerk |
| API authentication | Short-lived JWT verification |
| Authorisation | Application checks plus PostgreSQL RLS |
| Upload and download access | Short-lived presigned URLs |
| Storage encryption | Provider-side server encryption |
| Secret management | Deployment-provider secret store |
| Portfolio demo data | Synthetic only |

### 5.6 Observability

| Responsibility | Technology |
|---|---|
| Distributed tracing | OpenTelemetry |
| Error reporting | Sentry |
| Structured logs | structlog |
| Product analytics | Privacy-safe custom events |
| AI cost and latency | First-party model-run records |
| Service health | API and worker health endpoints |

---

## 6. Why Python Owns the Backend

Python is the preferred backend language because the project contains:

- document parsing;
- structured model outputs;
- multimodal document processing;
- date and temporal reasoning;
- AI evaluation;
- synthetic case generation;
- background processing;
- data analysis.

Using Python allows the same language to own:

- API schemas;
- document-processing logic;
- AI output contracts;
- deterministic rules;
- evaluation fixtures;
- offline analysis scripts.

This also expands the creator's portfolio beyond an already-strong React and TypeScript profile.

### Why Go is not selected

Go would be a credible backend language, but it would create unnecessary friction around document processing and AI tooling.

Go is better reserved for the later Evaluation-Driven Model Routing Studio, where concurrency, streaming, routing, and gateway performance are more central.

For this product:

> Python produces more product value per unit of implementation effort.

---

## 7. Why a Modular Monolith

The backend will be one deployable application with explicit internal modules.

This is preferable to microservices because:

- the product has one core domain;
- requirements, facts, evidence, and assessments are tightly connected;
- provenance is easier to preserve within one transactional boundary;
- deployment and observability remain manageable;
- the project can focus on product quality rather than service orchestration.

The architecture should preserve strong module boundaries without splitting deployment prematurely.

---

## 8. Backend Module Structure

```text
services/platform/
├── app/
│   ├── cases/
│   ├── applicants/
│   ├── residence/
│   ├── evidence/
│   ├── facts/
│   ├── requirements/
│   ├── assessments/
│   ├── issues/
│   ├── guidance/
│   ├── ai/
│   ├── audit/
│   ├── auth/
│   └── shared/
├── worker/
├── migrations/
├── tests/
└── evals/
```

Each domain module should contain:

```text
module/
├── domain.py
├── schemas.py
├── repository.py
├── service.py
├── routes.py
└── tests/
```

### Responsibilities

#### `cases`

Owns:

- application case creation;
- case lifecycle;
- case membership;
- current case phase;
- case deletion.

#### `applicants`

Owns:

- applicant profile;
- route facts;
- immigration status facts;
- personal details relevant to assessment.

#### `residence`

Owns:

- travel records;
- absence periods;
- application-date simulation;
- qualifying-period calculations;
- temporal validation.

#### `evidence`

Owns:

- evidence metadata;
- uploaded files;
- processing state;
- extracted claims;
- claim confirmation.

#### `facts`

Owns:

- confirmed facts;
- fact versions;
- fact provenance;
- stale-state propagation.

#### `requirements`

Owns:

- supported requirements;
- rule versions;
- rule metadata;
- route-specific applicability.

#### `assessments`

Owns:

- deterministic evaluation;
- assessment runs;
- assessment results;
- limitations;
- next actions.

#### `issues`

Owns:

- generated issues;
- issue state;
- resolutions;
- user-facing action queue.

#### `guidance`

Owns:

- official source registry;
- source versions;
- source sections;
- requirement-to-guidance mapping.

#### `ai`

Owns:

- provider adapters;
- capability contracts;
- prompt registry;
- model-run records;
- output validation.

#### `audit`

Owns:

- append-only audit entries;
- domain event recording;
- change history.

---

## 9. Repository Structure

Use a single repository.

```text
citizenship-workspace/
├── apps/
│   └── web/
│       ├── app/
│       ├── components/
│       ├── features/
│       ├── lib/
│       └── tests/
│
├── services/
│   └── platform/
│       ├── app/
│       ├── worker/
│       ├── evals/
│       ├── migrations/
│       └── tests/
│
├── packages/
│   ├── api-client/
│   ├── design-system/
│   └── test-fixtures/
│
├── docs/
│   ├── product/
│   ├── architecture/
│   ├── decisions/
│   └── evaluations/
│
├── infra/
│   ├── docker/
│   └── deployment/
│
├── docker-compose.yml
├── justfile
└── README.md
```

### Tooling

- `pnpm` for TypeScript workspaces;
- `uv` for Python dependencies;
- `justfile` or Makefile for cross-language commands;
- Docker Compose for local infrastructure;
- GitHub Actions for CI/CD.

Do not add Nx or Turborepo initially.

---

## 10. Frontend Architecture

### 10.1 Rendering Strategy

Use React Server Components for:

- workspace shell;
- authentication gates;
- route-level data loading;
- initial case state;
- static guidance content.

Use Client Components for:

- residence timeline;
- application-date simulator;
- document review;
- issue resolution;
- interactive requirement panels;
- uploads;
- optimistic mutations.

The objective is not to maximise Server Components. It is to place interactive state in the correct layer.

---

### 10.2 Feature Structure

```text
features/
├── case-overview/
├── onboarding/
├── timeline/
├── requirements/
├── evidence/
├── issues/
├── preparation/
└── assistant/
```

Each feature should own:

- components;
- hooks;
- API calls;
- view models;
- validation;
- tests.

---

### 10.3 State Management

#### Remote state

Use TanStack Query for:

- cases;
- travel records;
- evidence;
- processing state;
- requirements;
- assessments;
- issues.

#### Form state

Use React Hook Form for:

- onboarding;
- applicant details;
- trip creation and editing;
- extracted-claim corrections;
- referee details.

#### Temporary interaction state

Use local component state or a small Zustand store where necessary for:

- timeline zoom;
- unsaved application-date simulation;
- comparison mode;
- panel state.

Do not introduce Redux by default.

---

### 10.4 Design System

Use shadcn/ui and Radix primitives as accessible implementation foundations.

The product must not visually resemble a default shadcn dashboard.

Create domain-specific components such as:

- `RequirementStatus`;
- `EvidenceState`;
- `ProvenanceBadge`;
- `AssessmentSummary`;
- `ExplanationStack`;
- `IssueCard`;
- `TimelineEvent`;
- `CalculationBreakdown`;
- `SourceReference`;
- `ExtractedFieldReview`;
- `BeforeAfterValue`;
- `StaleAssessmentNotice`.

The design system should encode domain states, not only visual styling.

---

## 11. API Architecture

Use a versioned REST API.

```text
/api/v1/cases
/api/v1/cases/{case_id}
/api/v1/cases/{case_id}/travel-records
/api/v1/cases/{case_id}/evidence
/api/v1/cases/{case_id}/requirements
/api/v1/cases/{case_id}/assessments
/api/v1/cases/{case_id}/issues
/api/v1/cases/{case_id}/application-dates/simulate
```

### Why REST

The system has:

- clear resource boundaries;
- predictable mutations;
- one first-party frontend;
- asynchronous processing;
- no highly dynamic third-party query requirements.

GraphQL would add complexity without solving a meaningful first-version problem.

---

### 11.1 OpenAPI Contract Generation

FastAPI will generate the OpenAPI schema.

CI will:

1. Generate a TypeScript API client.
2. Publish or commit it under `packages/api-client`.
3. Detect schema drift.
4. Fail when generated client output is stale.
5. Require the frontend to use the generated client.

This gives the project:

- one API contract source;
- strongly typed frontend calls;
- visible schema evolution;
- reduced TypeScript/Python contract drift.

---

## 12. Core Domain Model

The primary domain object is an `ApplicationCase`.

```text
ApplicationCase
├── ApplicantProfile
├── NaturalisationRoute
├── ProposedApplicationDate
├── QualifyingPeriod
├── ImmigrationStatus
├── ResidenceTimeline
├── TravelRecords
├── EvidenceItems
├── ExtractedClaims
├── ConfirmedFacts
├── Requirements
├── AssessmentRuns
├── AssessmentResults
├── Issues
├── GuidanceSources
└── AuditHistory
```

---

## 13. Core Database Tables

```text
users
cases
case_members

applicant_profiles
immigration_statuses
proposed_application_dates

travel_records
travel_record_versions

evidence_items
evidence_files
evidence_processing_runs
extraction_runs
extracted_claims

confirmed_facts
fact_versions
fact_evidence_links

requirements
rule_versions
guidance_sources
guidance_sections

assessment_runs
assessment_results
assessment_fact_links
assessment_evidence_links

issues
issue_resolutions

model_runs
domain_events
audit_entries
```

The data model must make provenance explicit.

---

## 14. Claims Versus Facts

This distinction must exist in both data and UI.

### Extracted claim

```text
The system proposes:
return_date = 2026-05-10
```

An extracted claim is untrusted.

It contains:

- extraction run;
- document source;
- source region;
- model version;
- confidence;
- raw proposed value;
- validation result;
- review status.

### Confirmed fact

```text
The user confirmed:
return_date = 2026-05-10
```

A confirmed fact may influence deterministic assessments.

It contains:

- canonical value;
- source claim;
- confirming user;
- confirmation time;
- evidence links;
- fact version.

An extracted claim must never directly affect a trusted readiness assessment.

---

## 15. Evidence Graph Without a Graph Database

The product concept includes an evidence graph, but it will be represented relationally.

```text
assessment_results
    ↓
assessment_fact_links
    ↓
fact_versions
    ↓
fact_evidence_links
    ↓
evidence_items
```

This structure supports questions such as:

- Which facts produced this assessment?
- Which evidence supports this fact?
- Which assessments depend on a changed fact?
- Which requirements lack evidence?
- Which evidence is no longer used?
- Which assessment version used which fact version?

PostgreSQL is sufficient.

---

## 16. Deterministic Rules Engine

Rules must be implemented in Python, not hidden inside prompts.

Example interface:

```python
class RequirementEvaluator(Protocol):
    requirement_key: str
    rule_version: str

    def evaluate(
        self,
        case: CaseSnapshot,
        context: RuleContext,
    ) -> AssessmentResult:
        ...
```

Example output:

```python
class AssessmentResult(BaseModel):
    requirement_key: str
    status: AssessmentStatus
    summary: str
    fact_ids: list[UUID]
    evidence_ids: list[UUID]
    rule_version_id: UUID
    limitations: list[Limitation]
    next_actions: list[NextAction]
```

### Initial deterministic rules

- route applicability;
- status holding period;
- qualifying-period calculation;
- physical presence on the qualifying-period start date;
- total qualifying-period absences;
- final-year absence count;
- Life in the UK completion;
- language evidence presence;
- referee count and completion state.

### Rule properties to test

```text
Unconfirmed AI claims must not affect assessments.

Adding a confirmed absence day must not reduce the absence total.

Changing the proposed application date must recalculate the qualifying period.

Changing an unrelated fact must not alter an absence assessment.

A stale assessment must never appear as current.

Every assessment must reference a rule version.
```

Use Hypothesis for boundary and property-based testing.

---

## 17. Guidance Architecture

Official guidance should be curated and versioned rather than scraped live during each user session.

```text
GuidanceSource
├── URL
├── Title
├── Route
├── RetrievedDate
├── EffectivePeriod
├── ContentHash
└── GuidanceSections
```

Each rule version should link to:

- one or more guidance sections;
- the applicable route;
- the implementation version;
- the date retrieved.

### Retrieval flow

1. Identify the requirement deterministically.
2. Retrieve guidance assigned to the requirement.
3. Filter by supported route and rule version.
4. Optionally rank sections using PostgreSQL full-text search.
5. Supply only those sections to the language model.
6. Require source identifiers in the output.
7. Render citations from stored source records.

This is constrained retrieval rather than general-purpose RAG.

### Why no vector database

The initial guidance corpus is small, curated, and strongly structured.

Route and requirement metadata are more important than broad semantic search.

Embeddings should only be added if evaluation proves a meaningful benefit.

---

## 18. Document Processing Pipeline

Document processing must be asynchronous.

```text
1. Request presigned upload URL
2. Upload file directly to private object storage
3. Create evidence record
4. Queue processing task
5. Validate file type, size, and checksum
6. Extract native PDF text and page metadata
7. Determine whether visual extraction is required
8. Classify the document
9. Run schema-constrained extraction
10. Validate extracted values
11. Create proposed claims
12. Detect duplicates and conflicts
13. Save processing output
14. Notify the frontend
15. Wait for user confirmation
```

### Domain processing states

```text
Uploaded
Validating
Extracting text
Analysing document
Awaiting confirmation
Completed
Partially completed
Failed
Unsupported
```

Do not expose raw Celery task states to the user.

### Retry policy

Retry:

- temporary provider failures;
- rate limits;
- timeouts;
- transient network problems;
- temporary object-storage failures.

Do not automatically retry indefinitely for:

- unsupported file types;
- corrupted files;
- password-protected documents;
- repeatedly invalid structured output;
- documents above size limits.

Every task must be idempotent.

---

## 19. AI Capability Architecture

Do not create one universal AI function.

Create narrow capabilities:

```text
DocumentClassifier
DocumentClaimExtractor
TravelRecordExtractor
ConflictCandidateDetector
GuidanceExplainer
IssueSummariser
```

Each capability defines:

- input schema;
- output schema;
- permitted context;
- provider and model configuration;
- prompt version;
- schema version;
- retry policy;
- evaluation dataset;
- fallback behaviour.

Example provider interface:

```python
class AIProvider(Protocol):
    async def generate_structured(
        self,
        *,
        capability: str,
        messages: list[Message],
        output_schema: type[BaseModel],
        attachments: list[Attachment],
        config: ModelConfig,
    ) -> ModelResult:
        ...
```

The provider abstraction exists to preserve control and testability, not to build a multi-model platform.

---

## 20. Model-Run Records

Every model invocation should create a `model_run` record.

```text
model_runs
├── capability
├── provider
├── model
├── prompt_version
├── schema_version
├── latency_ms
├── input_tokens
├── output_tokens
├── estimated_cost
├── status
├── retry_count
├── trace_id
└── output_hash
```

Do not store sensitive document content in telemetry.

Raw document text should be retained only when necessary and under explicit retention rules.

---

## 21. Assessment Snapshots and Stale State

The system should not use full event sourcing.

Use:

- mutable current records;
- immutable fact versions;
- immutable assessment runs;
- append-only domain events;
- audit history.

When a confirmed fact changes:

```text
Fact changes
      ↓
New fact version is stored
      ↓
Dependent assessments are marked stale
      ↓
Affected deterministic rules rerun
      ↓
A new assessment run is stored
      ↓
The previous result remains inspectable
```

Example UI state:

```text
Final-year absences
Supported

Stale
A travel return date changed after this assessment.

[ Recalculate ]
```

This is a key trust and explainability feature.

---

## 22. Real-Time Processing Updates

Use Server-Sent Events for document-processing progress.

Example events:

```text
Evidence uploaded
File validated
Text extracted
Document classified
Claims ready for review
```

SSE is preferred because the first version requires one-way server-to-client updates.

WebSockets are not required unless future collaboration features need bidirectional real-time state.

Polling should remain available as a fallback.

---

## 23. Security Architecture

Although the project is private and non-commercial, it should be engineered responsibly.

### 23.1 Public portfolio environment

The public demonstration must use:

- synthetic applicants;
- generated travel records;
- fictional document identifiers;
- synthetic or fully redacted evidence.

Real personal documents must never appear in screenshots, demo videos, fixtures, or public environments.

### 23.2 Private testing

Private friend testing should use:

- a separate environment;
- private object storage;
- complete case deletion;
- no session replay;
- no raw document logging;
- restricted user access.

### 23.3 Required controls

- managed authentication;
- server-side case ownership checks;
- PostgreSQL row-level security;
- private storage buckets;
- short-lived presigned URLs;
- file type and size validation;
- content checksums;
- strict CORS;
- extraction endpoint rate limits;
- model timeout and spending limits;
- PII filtering in logs;
- explicit case and document deletion;
- secrets stored only in server environments.

### 23.4 Threat model

The architecture documentation should explicitly cover:

- broken object-level authorisation;
- guessed evidence identifiers;
- cross-case evidence access;
- malicious PDF uploads;
- prompt injection inside documents;
- excessive model spending;
- PII leakage through logs;
- stale presigned URLs;
- unsupported or malformed files;
- model output containing invented references.

### Prompt-injection rule

> Uploaded documents are untrusted data, never instructions.

Document content must not be allowed to:

- alter system instructions;
- invoke tools;
- change output schemas;
- request additional data;
- bypass validation.

---

## 24. Observability Architecture

A single trace should cover:

```text
Browser action
  → API request
  → database operation
  → Celery task
  → document extraction
  → model request
  → claim persistence
  → assessment recalculation
```

Useful telemetry fields:

```text
trace_id
case_id_hash
evidence_id
capability
model
prompt_version
schema_version
processing_stage
latency_ms
token_count
retry_count
assessment_count
```

Do not record:

- document text;
- names;
- passport numbers;
- unredacted model prompts;
- personal travel details linked to identity.

### Product and engineering metrics

- time to create a readiness case;
- evidence-processing success rate;
- claim confirmation rate;
- claim correction rate;
- conflict-detection rate;
- requirements with complete provenance;
- stale-assessment frequency;
- issue-resolution completion rate;
- cost per processed document;
- P50 and P95 processing latency.

---

## 25. Testing Strategy

### 25.1 Frontend Tests

Test:

- component behaviour;
- keyboard navigation;
- timeline calculations;
- accessible status labels;
- document-review state changes;
- error and retry flows;
- responsive layouts;
- optimistic issue resolution;
- reduced-motion behaviour.

### 25.2 Backend Tests

Test:

- deterministic rules;
- API contracts;
- repository logic against PostgreSQL;
- authorisation;
- row-level isolation;
- migrations;
- queue-task idempotency;
- storage permissions;
- stale-state propagation.

### 25.3 AI Contract Tests

Validate that model output:

- conforms to the required schema;
- includes only permitted fields;
- references known source identifiers;
- never invents evidence identifiers;
- never becomes a confirmed fact automatically;
- handles malformed or unsupported documents safely.

---

## 26. AI Evaluation Suite

Create a synthetic evaluation dataset covering:

- clear status document;
- poor-quality scan;
- conflicting return date;
- multiple dates on one page;
- incorrect applicant name;
- duplicate evidence;
- unsupported document;
- overlapping trips;
- missing return date;
- prompt injection inside uploaded content;
- misleading filename;
- model refusal;
- partial extraction;
- inconsistent evidence sources;
- stale assessment after fact change.

### Evaluation metrics

- document-classification accuracy;
- field-extraction precision and recall;
- date-extraction accuracy;
- conflict-detection precision and recall;
- citation validity;
- unsupported-case detection;
- false-reassurance rate;
- cost per document;
- P50 and P95 latency.

The most important safety metric is:

> **False reassurance rate**

The product must prefer visible uncertainty over an unsupported positive conclusion.

---

## 27. CI/CD Architecture

### Pull Request Pipeline

```text
Frontend lint
Frontend typecheck
Frontend unit tests
Python lint
Python typecheck
Python unit tests
Database migration validation
Generated API client drift check
Docker build
Dependency security scan
Small deterministic evaluation suite
```

### Main Branch Pipeline

```text
All pull request checks
Integration tests
Playwright smoke tests
Deployment
Database migration
Post-deployment health checks
```

### Scheduled or Manual Evaluation Pipeline

```text
Full AI evaluation suite
Cost report
Latency comparison
Prompt regression report
Extraction failure report
```

Do not run expensive live-model evaluations on every commit.

---

## 28. Deployment Architecture

### Initial deployment

| Component | Platform |
|---|---|
| Next.js web | Vercel |
| FastAPI API | Railway or Fly.io |
| Celery worker | Same platform as API |
| PostgreSQL | Managed PostgreSQL |
| Redis | Managed Redis |
| Documents | AWS S3 or compatible private storage |
| Error reporting | Sentry |
| Traces | OpenTelemetry-compatible backend |

### Local development

Use Docker Compose for:

- PostgreSQL;
- Redis;
- FastAPI;
- Celery worker;
- MinIO.

Run the Next.js application through `pnpm`.

---

## 29. Explicitly Rejected Alternatives

### 29.1 Next.js-only Backend

Rejected because:

- long-running document processing is awkward;
- Python provides stronger document and AI tooling;
- the portfolio should demonstrate backend depth beyond route handlers.

### 29.2 Microservices

Rejected because:

- the product has one tightly connected domain;
- service boundaries would add operational overhead;
- provenance and consistency are simpler inside one transactional application;
- microservices would weaken implementation focus.

### 29.3 LangChain or LangGraph

Rejected because:

- most workflows are deterministic;
- there is no meaningful autonomous agent loop;
- direct provider calls are easier to inspect, test, and evaluate.

### 29.4 Vector Database

Rejected because:

- the guidance corpus is small and curated;
- route and requirement metadata provide stronger retrieval constraints;
- PostgreSQL full-text search is enough initially.

### 29.5 Graph Database

Rejected because:

- the evidence graph has known relationships;
- relational joins provide sufficient traversal;
- another database would add operational complexity.

### 29.6 Full Event Sourcing

Rejected because:

- immutable fact versions and assessment runs provide the required history;
- full event sourcing would substantially increase complexity.

### 29.7 Custom Authentication

Rejected because:

- authentication is not a differentiating capability;
- managed authentication reduces security risk and implementation time.

### 29.8 Kubernetes

Rejected because:

- the product has only a web app, API, and worker;
- container deployment with health checks is sufficient;
- Kubernetes would add complexity without improving the portfolio signal.

---

## 30. Key Architecture Risks

### Risk 1 — Excessive data-model complexity

Mitigation:

- implement only the entities needed for the first supported route;
- keep provider-specific metadata in JSONB;
- avoid abstracting for future visa routes too early.

### Risk 2 — AI extraction scope expands

Mitigation:

- begin with two or three document categories;
- define strict schemas;
- create evaluation fixtures before adding new categories.

### Risk 3 — Timeline UI and backend calculations diverge

Mitigation:

- keep calculations server-side;
- return full calculation breakdowns;
- test shared fixture scenarios across frontend and backend.

### Risk 4 — Prompt logic replaces domain logic

Mitigation:

- enforce narrow AI capabilities;
- keep route and requirement rules in Python;
- require structured outputs and validation.

### Risk 5 — Real user data leaks into portfolio artefacts

Mitigation:

- maintain synthetic public fixtures;
- separate private testing environments;
- automate data deletion;
- review every screenshot and demo asset.

### Risk 6 — Over-engineering reduces product polish

Mitigation:

- keep one backend deployment;
- avoid optional infrastructure;
- prioritise the requirement detail, timeline, and evidence review experiences.

---

## 31. Implementation Order

> **Canonical build order lives in `docs/IMPLEMENTATION_ROADMAP.md` (M0–M12).**
> The phases below are a coarser architectural grouping; where they disagree on
> sequence, the Roadmap wins.

### Phase 1 — Platform foundation

- repository setup;
- local Docker environment;
- authentication;
- case creation;
- PostgreSQL schema;
- generated API client;
- baseline observability.

### Phase 2 — Deterministic case engine

- applicant profile;
- proposed application date;
- travel records;
- qualifying-period calculations;
- absence rules;
- requirement assessments;
- assessment snapshots.

### Phase 3 — Core workspace UI

- case overview;
- requirement details;
- timeline;
- issue queue;
- stale assessment handling.

### Phase 4 — Evidence pipeline

- object storage;
- upload flow;
- Celery worker;
- PDF extraction;
- document classification;
- structured claim extraction;
- review and confirmation.

### Phase 5 — Explainability and guidance

- guidance registry;
- versioned sources;
- assessment provenance;
- contextual explanation;
- source references.

### Phase 6 — Evaluation and hardening

- synthetic fixtures;
- AI evaluation suite;
- security review;
- accessibility testing;
- performance testing;
- observability dashboards;
- demo flow.

---

## 32. Portfolio Architecture Story

The final portfolio case study should explain:

> The product uses a modular Python backend with a separate asynchronous document worker. AI outputs are stored as untrusted claims and cannot influence citizenship assessments until the user confirms them. Deterministic rules generate immutable assessment results that reference versioned facts, supporting evidence, and official guidance. When a fact changes, dependent assessments become stale and are recalculated. The full path from document upload to requirement assessment is observable, testable, and inspectable.

This narrative demonstrates:

- AI product judgement;
- backend architecture;
- temporal reasoning;
- data provenance;
- human-in-the-loop systems;
- production quality;
- frontend and backend ownership.

---

## 33. Final Stack

```text
Frontend
Next.js
React
TypeScript
Tailwind CSS
Radix UI
shadcn/ui
TanStack Query
React Hook Form
Zod
D3
SVG
PDF.js
Playwright

Backend
Python
FastAPI
Pydantic
SQLAlchemy
Alembic
Celery
Redis
pytest
Hypothesis

Data
PostgreSQL
S3-compatible object storage
MinIO for local development
Relational provenance graph
Versioned guidance registry

AI
Direct provider SDK
Structured outputs
PyMuPDF
Multimodal fallback
Human-confirmed claims
Custom evaluation harness

Platform
Clerk
Docker
GitHub Actions
OpenTelemetry
Sentry
Vercel
Railway or Fly.io
```

---

## 34. Next Technical Documents

The next architecture documents should be created in this order:

1. Domain Model RFC
2. Deterministic Rules Engine RFC
3. Evidence and Claim Lifecycle RFC
4. Document Processing Pipeline RFC
5. Guidance and Source Versioning RFC
6. AI Capability and Evaluation RFC
7. Security and Privacy Threat Model
8. API Contract RFC
9. Frontend Architecture RFC
10. Implementation Roadmap
