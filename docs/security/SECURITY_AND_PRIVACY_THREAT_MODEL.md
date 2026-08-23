# Evidence-First Citizenship Workspace

## Security and Privacy Threat Model

**Status:** Proposed for implementation\
**Version:** 0.1\
**Scope:** MVP --- UK naturalisation, Section 6(1) standard route

## 1. Purpose

This document defines the security and privacy model for the
Evidence-First Citizenship Workspace MVP.

The product may process sensitive personal material including
immigration status, travel history, identity-related evidence,
language-test evidence, Life in the UK evidence, and limited referee
information. Security, privacy, provenance, access control, deletion,
and safe AI processing are therefore core product requirements.

The goal is not to claim enterprise certification for a portfolio
project. It is to demonstrate production-quality security judgement
appropriate to a high-trust AI product.

> A user should be able to understand what information the system holds,
> why it is needed, how it is used, what AI inferred from it, and how to
> remove it.

## 2. Security Objectives

The MVP must protect:

-   **Confidentiality:** case data and evidence are accessible only to
    the authorised owner and authorised backend processes.
-   **Integrity:** AI claims, confirmed facts, rules, evidence, and
    assessments cannot be silently confused or overwritten.
-   **Availability:** failures in storage, workers, or model providers
    do not corrupt the case.
-   **Explainability:** provenance survives throughout the lifecycle.
-   **Data minimisation:** collect only what the supported workflow
    requires.
-   **User control:** users can remove evidence and delete their case.

## 3. Data Classification

### Tier 0 --- Public

Product copy, synthetic demo data, design assets, architecture
documentation, and public guidance metadata.

### Tier 1 --- Operational

Opaque IDs, rule/prompt/schema versions, processing states, latency,
token usage, model cost, and trace IDs.

### Tier 2 --- Personal

Travel dates/destinations, proposed application date, immigration
status, status grant date, test state, and limited referee details.

Controls: authenticated access; no ordinary logging; deletion with the
case.

### Tier 3 --- Highly Sensitive Evidence

Uploaded documents, document text, extracted personal values, previews,
passport/reference numbers that may appear inside evidence.

Controls: private storage, short-lived authorised access, no public demo
use, no ordinary telemetry, strict deletion, and minimum necessary
transmission to AI providers.

## 4. Trust Boundaries

``` text
User Browser
    |
    | HTTPS
    v
Next.js
    |
    | authenticated API
    v
FastAPI
    |----------------------|
    |                      |
    v                      v
PostgreSQL             Private Object Storage
    |
    | outbox
    v
Redis / Celery
    |
    | constrained capability
    v
AI Provider
```

Every boundary treats incoming data as potentially malformed or hostile.

## 5. Threat Actors

-   unauthenticated attacker;
-   authenticated user attempting cross-case access;
-   malicious or malformed uploaded document;
-   compromised or unreliable AI model;
-   accidental user action;
-   developer/operational mistake;
-   compromised dependency or external provider.

## 6. P0 Threats

### 6.1 Broken Object-Level Authorisation

**Threat:** changing a resource UUID exposes another user's case or
evidence.

**Controls:** - every case-scoped request verifies authenticated
membership server-side; - nested resources are resolved through the case
boundary; - identifiers never imply permission; - row-level security is
defence in depth where practical; - presigned evidence URLs require
current case authorisation; - cross-user tests are mandatory.

**Invariant:** User A cannot read, mutate, preview, or delete any User B
resource even with a valid UUID.

### 6.2 Public Evidence Exposure

**Controls:** - private object-storage buckets; - random non-semantic
storage keys; - short-lived signed URLs; - authorisation before URL
creation; - deleted evidence becomes inaccessible; - storage
configuration is tested.

### 6.3 AI Claim Bypasses Human Confirmation

Claims and facts are separate domain entities.

``` text
Evidence
→ ExtractedClaim
→ Human review
→ FactVersion
→ Deterministic Assessment
```

Unconfirmed claims can never enter a trusted assessment. This is a
release-blocking invariant.

### 6.4 Sensitive Data in Logs or Traces

Never log: - document text; - extracted personal values; -
passport/reference numbers; - referee names; - full prompts containing
evidence; - signed URLs; - auth tokens; - storage credentials.

Prefer opaque IDs, capability, status, latency, retries, token counts,
cost, error codes, and trace IDs.

### 6.5 Prompt Injection Through Evidence

Uploaded documents are untrusted data. AI capabilities must: - have one
narrow purpose; - explicitly ignore instructions inside documents; - use
typed structured output; - reject unknown fields; - have no application
tools or autonomous permissions; - never change rules or assessments; -
never create trusted facts; - require human confirmation; - pass
prompt-injection evaluation fixtures.

### 6.6 Stale Assessment Presented as Current

Assessed inputs are immutable versions. Relevant changes mark affected
results stale transactionally. A failed recalculation leaves the
historical result visibly stale and cannot promote it to current.

### 6.7 Real Data in Public Demo

The public portfolio environment uses synthetic data only. Public demo
storage/database must be isolated from private testing. Screenshots,
fixtures, seed data, logs, and demo video must be reviewed for
accidental real PII.

### 6.8 Secrets Exposure

-   secrets remain server-side;
-   `.env*` is ignored except templates;
-   no provider secret uses `NEXT_PUBLIC_*`;
-   deployment environment injects credentials;
-   secret scanning is enabled where available;
-   exposed credentials are rotated immediately.

## 7. File Upload Threats

Controls: - allowlist supported MIME types; - validate file signatures
where practical; - enforce file-size and page-count limits; -
server-generated storage keys; - checksum files; - process outside the
web process; - parser time/memory limits; - never execute uploaded
content; - controlled preview rendering; - recoverable failure states.

If malware scanning is not implemented, document that limitation before
real friend testing.

## 8. AI Security Architecture

``` text
Evidence
   ↓
Controlled preprocessing
   ↓
Capability-specific prompt
   ↓
Schema-constrained model output
   ↓
Validation
   ↓
ExtractedClaim
   ↓
Human confirmation/correction
   ↓
Trusted Fact
   ↓
Deterministic Rule Engine
```

AI is not authorised to: - determine the active route; - modify rules; -
write trusted facts directly; - mark assessments current; - dismiss
blocking issues; - delete evidence; - access arbitrary cases; - execute
document instructions.

## 9. Model Output Validation

Model output must pass:

1.  structured-output parsing;
2.  Pydantic validation;
3.  enum validation;
4.  date parsing;
5.  semantic validation;
6.  source-ID validation;
7.  capability-specific sanity checks.

Failure produces retry, partial processing, or failure --- never silent
creation of trusted state.

## 10. Model Provider Privacy

Before real-data testing: - review provider retention and training
behaviour; - use settings preventing training on submitted content where
available; - send only capability-required information; - prefer
relevant extracted regions over whole documents where practical; - keep
API keys server-side; - avoid retaining raw model payloads; - document
provider/privacy assumptions.

**Gate:** real friend data must not be sent to a model provider until
this review is recorded.

## 11. Authentication and Authorisation

Authentication uses the selected managed provider. The API remains
authoritative for access control.

For nested resources:

``` text
authenticated user
→ case membership
→ resource belongs to case
→ action permitted
```

Frontend visibility is never an access-control mechanism.

Anonymous demo access, if added, must operate only against an isolated
synthetic case with restricted capabilities.

## 12. Object Storage

Required: - private bucket/container; - random keys; - server-authorised
signed URLs; - short expiration; - HTTPS; - checksum verification; -
content-type validation; - deletion; - separate public-demo storage
where practical.

Original filenames are metadata only and never determine storage paths.

## 13. Database, Redis, and Worker Security

Database: - least-privilege runtime credentials; - parameterised SQL; -
ownership checks; - RLS as defence in depth where practical; - no
private database copied into public demo.

Redis: - not publicly exposed; - authenticated where supported; - store
identifiers/job metadata rather than raw evidence.

Workers receive IDs, fetch resources server-side, use idempotency keys,
and have bounded retries.

## 14. XSS, CSRF, and Browser Security

-   keep React escaping enabled;
-   never render untrusted HTML directly;
-   treat AI output as text/structured data;
-   use a restrictive CSP;
-   avoid `dangerouslySetInnerHTML`;
-   escape filenames and user labels;
-   use secure session-cookie settings where applicable;
-   follow auth-provider CSRF protections;
-   require explicit confirmation for destructive actions.

## 15. Rate, Cost, and Resource Abuse

Protect: - case creation; - uploads; - document processing; - AI
extraction; - explanation endpoints; - retries.

Use: - per-user limits; - file-size/count limits; - bounded retries; -
concurrent-processing limits; - model budgets/provider spending caps; -
idempotency; - queue monitoring; - restricted anonymous-demo AI.

Cost exhaustion is treated as an availability/security risk.

## 16. Dependency and Supply-Chain Security

-   lock dependency versions;
-   minimise dependencies;
-   prefer maintained libraries;
-   review document/auth packages carefully;
-   use maintained base images;
-   vulnerability and secret scanning in CI where practical;
-   dependency update alerts.

## 17. Concurrency and Async Integrity

Use: - aggregate revisions; - optimistic concurrency; - immutable
assessed versions; - transactional outbox; - idempotency keys; -
uniqueness constraints.

Duplicate worker delivery must not create duplicate claims, facts, or
assessment results.

## 18. Evidence Deletion

``` text
User requests deletion
→ authorisation
→ DELETION_PENDING
→ block access/processing
→ delete object asynchronously
→ mark evidence links unavailable
→ invalidate dependent assessments
→ update issues
→ remove sensitive derived artefacts
→ DELETED
→ retain minimal tombstone
```

Deletion must be idempotent.

## 19. Case Deletion

``` text
User confirms deletion
→ case = DELETION_PENDING
→ block writes/new jobs
→ cancel safe jobs
→ delete evidence objects
→ delete claims and personal derived data
→ delete case-scoped personal records
→ remove retained model payloads
→ preserve minimal non-identifying deletion audit
→ case = DELETED
```

This workflow must be tested end to end.

## 20. Privacy UX

Users must be able to distinguish: - user-entered information; -
AI-proposed information; - confirmed facts; - deterministic
calculations; - evidence support; - uncertainty; - deleted/unavailable
evidence.

Evidence upload should explain what is processed, that AI may analyse
it, that extraction requires review, and that evidence can be deleted.

Avoid vague claims such as "100% secure", "AI verified", or "guaranteed
confidential".

## 21. Private Friend Testing Gate

Before processing real documents from friends:

-   authentication enabled;
-   private object storage;
-   ownership tests passing;
-   signed URLs expiring;
-   evidence deletion working;
-   case deletion working;
-   sensitive values excluded from telemetry;
-   AI provider privacy reviewed;
-   prompt-injection tests passing;
-   claim/fact boundary proven;
-   HTTPS enabled;
-   public and private environments separated;
-   known limitations communicated.

If a critical control is missing, use synthetic documents instead.

## 22. Public Portfolio Deployment Gate

Before public deployment:

-   all public data synthetic;
-   no private evidence in public storage;
-   model usage bounded;
-   secrets server-side;
-   debug disabled;
-   stack traces hidden;
-   CORS restricted;
-   CSP/security headers configured;
-   dependency scanning passing;
-   auth boundaries tested;
-   demo reset isolated;
-   screenshots and fixtures reviewed for PII.

## 23. Security Headers

Configure where compatible:

-   `Content-Security-Policy`;
-   `Strict-Transport-Security`;
-   `X-Content-Type-Options`;
-   `Referrer-Policy`;
-   `Permissions-Policy`;
-   frame restrictions through CSP.

Cookie sessions should use `Secure`, `HttpOnly`, and an appropriate
`SameSite` policy.

## 24. Security Testing

Automated tests should cover:

-   unauthenticated access;
-   cross-user access;
-   expired/deleted evidence URLs;
-   invalid and oversized uploads;
-   malformed model output;
-   prompt injection;
-   duplicate worker delivery;
-   stale-assessment invariant;
-   claim-to-fact boundary;
-   evidence deletion;
-   case deletion;
-   invalid model source IDs;
-   optimistic concurrency.

Manual release review: - browser storage; - network traffic; -
logs/traces; - object-storage policy; - auth configuration; - error
messages; - public seed data.

## 25. Threat Matrix

  Threat                                 Impact         Likelihood    Priority
  -------------------------------------- -------------- ------------- ----------
  Broken object-level authorisation      Critical       Medium        P0
  Public evidence exposure               Critical       Medium        P0
  AI claim bypasses confirmation         Critical       Medium        P0
  Sensitive data in telemetry            Critical       Medium        P0
  Secrets exposure                       Critical       Medium        P0
  Prompt injection                       High           High          P0
  Incorrect AI extraction                High           High          P0
  Stale assessment shown as current      High           Medium        P0
  Real data leaked through public demo   Critical       Medium        P0
  Provider privacy mismatch              High           Medium        P1
  Unsafe file processing                 High           Medium        P1
  Evidence deletion inconsistency        High           Medium        P1
  XSS through untrusted content          High           Medium        P1
  Resource/model abuse                   Medium--High   Medium        P1
  Duplicate async processing             Medium         High          P1
  Dependency compromise                  High           Low--Medium   P1
  Lost concurrent update                 Medium         Medium        P2

All P0 threats must be addressed before private real-data testing.

## 26. Security Invariants

``` text
A user cannot access a case they do not own.

A storage key never grants authorisation.

An unconfirmed AI claim never influences a trusted assessment.

A model can never create a trusted fact directly.

Uploaded document instructions cannot modify application behaviour.

A stale assessment can never be returned as current.

Deleting evidence removes its current support state.

Sensitive document content never appears in ordinary logs or traces.

Public demo fixtures never contain real personal data.

A failed AI request never changes a deterministic assessment.

Duplicate worker delivery cannot duplicate trusted domain state.

Case deletion is terminal and idempotent.
```

Violation of a P0 invariant blocks release.

## 27. Security Work by Milestone

### M1 --- Platform Foundation

Secrets conventions, secure auth shell, safe structured logging,
dependency/secret scanning.

### M2 --- Case Setup

Case ownership, nested authorisation, deletion foundation, cross-user
tests.

### M3--M6 --- Deterministic Workspace

Immutable versions, concurrency, stale-state integrity, safe audit
events.

### M7 --- Evidence Foundation

Private storage, signed URLs, validation, worker isolation, deletion,
access tests.

### M8 --- Document AI

Prompt-injection controls, structured validation, claim/fact boundary,
provider privacy review, model limits, security evaluation fixtures.

### M9 --- Guidance AI

Server-selected sources, citation validation, constrained retrieval, no
autonomous browsing.

### M11 --- Hardening

Threat-model review, privacy review, access testing, deletion
verification, telemetry inspection, failure injection.

### M12 --- Release

Public deployment gate; synthetic data only.

## 28. Deferred Enhancements

Not required for the MVP unless scope changes:

-   malware scanning service;
-   content disarm/reconstruction;
-   dedicated secrets manager;
-   field-level application encryption;
-   hardware-backed key management;
-   formal penetration test;
-   automated DAST;
-   collaborator permission model;
-   regional residency controls;
-   configurable retention;
-   formal DPIA;
-   SOC 2 / ISO 27001 controls.

## 29. Definition of Security Ready

The MVP is security-ready for its intended scope when:

1.  all P0 threats have controls;
2.  cross-user tests pass;
3.  evidence storage is private;
4.  signed URLs are short-lived and authorised;
5.  claims cannot bypass confirmation;
6.  prompt-injection fixtures pass;
7.  stale results cannot appear current;
8.  sensitive values are absent from telemetry;
9.  evidence deletion works end to end;
10. case deletion works end to end;
11. provider privacy behaviour is documented before real-data testing;
12. public deployment uses synthetic data only;
13. model/API abuse is bounded;
14. known limitations are documented honestly.

## 30. Final Security Principle

> The product should earn trust structurally rather than through
> reassuring copy: minimise collected data, isolate sensitive evidence,
> constrain AI authority, require human confirmation, preserve
> provenance, enforce ownership at every boundary, and make deletion
> real.
