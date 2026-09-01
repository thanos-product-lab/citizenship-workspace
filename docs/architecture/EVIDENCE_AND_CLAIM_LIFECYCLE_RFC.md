# Evidence-First Citizenship Workspace

## Evidence and Claim Lifecycle RFC

**Status:** Proposed for implementation\
**Version:** 0.1\
**Initial route:** UK naturalisation --- Section 6(1), standard
five-year route

## 1. Purpose

This RFC defines how documentary evidence enters the Citizenship
Workspace, how AI may analyse it, how extracted information is reviewed,
and how information becomes trusted case state.

> How does untrusted information from a document become trusted
> information that is allowed to influence the case?

``` text
Uploaded Evidence
       ↓
Evidence Processing
       ↓
Extraction Run
       ↓
Extracted Claim
       ↓
Human Review
   ↙      ↓       ↘
Reject  Correct  Confirm
           ↓
      Confirmed Fact
           ↓
 Deterministic Assessment
```

The core distinction is:

> **Evidence ≠ Claim ≠ Fact ≠ Assessment**

No AI output is trusted merely because it is structured, plausible, or
high-confidence.

## 2. Goals

The lifecycle must ensure that:

-   uploaded evidence is immutable and traceable;
-   AI extraction produces proposals rather than authoritative state;
-   users can confirm, correct, or reject AI proposals;
-   original AI output survives review;
-   trusted facts are versioned rather than overwritten;
-   every AI-derived fact is traceable to evidence;
-   conflicting information becomes explicit product state;
-   reprocessing cannot silently alter confirmed facts;
-   evidence deletion has deterministic downstream consequences;
-   stale assessments propagate correctly;
-   asynchronous processing is idempotent;
-   review outcomes can later support AI evaluation.

## 3. Non-Goals

This RFC does not define deterministic naturalisation rules, exact
prompts, model selection, evaluation thresholds, guidance retrieval,
malware-scanning implementation, or general legal-advice behaviour.

## 4. Design Principles

### AI output is always a proposal

AI can propose information. It cannot create trusted case facts
directly.

### Human confirmation is a trust boundary

The transition from `ExtractedClaim` to trusted `FactVersion` requires
explicit review for AI-derived information.

### Preserve history

Corrections create new state; they never rewrite the model's original
proposal.

### Provenance is first-class

The system must be able to explain which evidence, file version,
extraction run, claim, review decision, and fact version contributed to
an assessment.

### Reprocessing is non-destructive

A newer extraction run may produce new claims. It cannot silently
replace confirmed facts.

### Uncertainty remains visible

Missing, ambiguous, conflicting, or partially extracted information is
represented explicitly rather than guessed.

## 5. Trust Model

### Level 0 --- Raw Evidence

A user-supplied document. Its contents are untrusted input.

### Level 1 --- AI-Proposed Claim

A structured interpretation of evidence. It remains untrusted.

### Level 2 --- Confirmed Fact

The user has confirmed or corrected the information. It may enter
trusted deterministic evaluation.

### Level 3 --- Assessment Result

A deterministic rule evaluates exact trusted input versions and produces
an immutable result.

## 6. Aggregate Boundaries

``` text
ApplicationCase

EvidenceItem
 ├── EvidenceFile
 └── EvidenceProcessingRun

ExtractionRun
 └── ExtractedClaim

CaseFact
 └── FactVersion

AssessmentRun
 └── AssessmentResult
```

`ClaimReviewDecision` records the explicit transition decision between a
claim and trusted fact state.

Cross-aggregate changes use domain services and transactional events
rather than hidden ORM side effects.

## 7. Evidence Lifecycle

### EvidenceItem

Represents logical evidence supplied to a case.

Suggested fields:

``` text
id
case_id
category
display_name
status
created_at
created_by
deleted_at
revision
```

Initial categories:

``` text
IMMIGRATION_STATUS
LIFE_IN_UK
ENGLISH_LANGUAGE
TRAVEL
OTHER
```

### EvidenceFile

Represents an immutable physical upload/version.

``` text
id
evidence_item_id
storage_key
original_filename
media_type
size_bytes
checksum
version_number
created_at
availability_status
```

Storage keys are random. Original filenames are display metadata only.
Replacement creates another `EvidenceFile`.

### Evidence Status

``` text
UPLOAD_PENDING
→ UPLOADED
→ VALIDATING
→ PROCESSING
→ AWAITING_REVIEW
→ COMPLETED
```

Alternative states:

``` text
PARTIALLY_COMPLETED
FAILED
UNSUPPORTED
DELETION_PENDING
DELETED
```

Evidence status is a workflow projection, not a substitute for claim or
fact state.

### EvidenceProcessingRun

Every processing attempt is independently identifiable:

``` text
id
evidence_file_id
processing_version
status
started_at
completed_at
error_code
retry_number
trace_id
```

A run may perform validation, native text extraction, visual fallback,
classification, structured extraction, and conflict detection.

## 8. ExtractionRun

An `ExtractionRun` records one AI capability invocation against one
immutable evidence file.

``` text
id
case_id
evidence_file_id
processing_run_id
capability
provider
model
prompt_version
schema_version
input_hash
status
started_at
completed_at
latency_ms
input_tokens
output_tokens
estimated_cost
retry_number
trace_id
output_hash
```

Initial capabilities:

``` text
DocumentClassifier
DocumentClaimExtractor
TravelRecordExtractor
ConflictCandidateDetector
```

Capabilities receive only necessary context and cannot mutate cases,
create facts, recalculate assessments, dismiss issues, or access
unrelated evidence.

## 9. ExtractedClaim

An `ExtractedClaim` is an immutable machine-proposed interpretation of
information found in a specific evidence version.

``` text
id
case_id
evidence_item_id
evidence_file_id
extraction_run_id
claim_type
proposed_value
normalised_value
value_schema_version
source_locator
model_confidence
review_priority
status
created_at
superseded_by_claim_id
```

### Source Locator

Where possible:

``` text
page_number
text_span
bounding_box
section_label
source_text_hash
```

This allows source highlighting without unnecessarily duplicating
document content.

### Claim Status

``` text
PENDING_REVIEW
CONFIRMED
CORRECTED
REJECTED
SUPERSEDED
INVALIDATED
```

Status records review history. It does not turn the claim itself into a
fact.

### Immutability

If AI proposes `2021-09-14` and the user corrects it to `2020-09-14`:

``` text
ExtractedClaim
proposed_value = 2021-09-14

ClaimReviewDecision
decision = CORRECT
corrected_value = 2020-09-14

FactVersion
value = 2020-09-14
```

The original proposal remains unchanged.

## 10. Claim Review

`ClaimReviewDecision` is an immutable user action:

``` text
id
claim_id
case_id
decision
corrected_value
reviewed_by
reviewed_at
reason_code
revision
```

Final decisions:

``` text
CONFIRM
CORRECT
REJECT
```

`DEFER` may exist as non-final UI/workflow state.

### Confirm

Creates a new trusted `FactVersion`, or links to an equivalent current
fact only when explicit domain rules permit it.

### Correct

Preserves the original claim, records the correction, creates a fact
from the corrected value, and preserves provenance.

### Reject

Creates no trusted fact.

Possible reasons:

``` text
VALUE_NOT_PRESENT
WRONG_FIELD
WRONG_DOCUMENT
DUPLICATE
AMBIGUOUS
OTHER
```

### High-Risk Fields

Fields such as immigration-status grant dates and travel dates require
field-level review. The MVP must not offer bulk "Confirm all" for
high-risk fields.

## 11. CaseFact and FactVersion

`CaseFact` is the stable identity of a trusted concept:

``` text
id
case_id
fact_type
current_version_id
created_at
revision
```

`FactVersion` stores one immutable trusted value:

``` text
id
case_fact_id
version_number
value
value_schema_version
source_method
confirmation_status
created_at
created_by
supersedes_fact_version_id
```

Source methods:

``` text
USER_ENTERED
USER_CONFIRMED_AI_CLAIM
USER_CORRECTED_AI_CLAIM
DETERMINISTIC_DERIVATION
```

AI alone is never a trusted source method.

Changing a value creates another version; historical assessments retain
links to their original version.

## 12. FactEvidenceLink

A fact may be supported by zero, one, or several evidence items.

``` text
id
fact_version_id
evidence_item_id
evidence_file_id
claim_id
support_type
availability_status
created_at
```

Possible support types:

``` text
PRIMARY
SUPPORTING
CONFLICTING
USER_ASSERTED
```

This enables:

``` text
Assessment
→ FactVersion
→ FactEvidenceLink
→ Evidence
→ ExtractedClaim
→ ExtractionRun
```

## 13. User-Entered Facts

Not every trusted fact requires AI or evidence.

Users may deliberately enter facts directly. The UI distinguishes
user-entered, evidence-supported, AI-proposed, confirmed-from-AI, and
unsupported states where relevant.

Adding evidence later strengthens provenance without rewriting
historical origin.

## 14. Provenance

For AI-assisted information:

``` text
EvidenceItem
→ EvidenceFile
→ EvidenceProcessingRun
→ ExtractionRun
→ ExtractedClaim
→ ClaimReviewDecision
→ FactVersion
→ AssessmentInputLink
→ AssessmentResult
```

A simplified UI may render:

``` text
Assessment
→ Settled status granted: 14 Sep 2020
→ Confirmed by you
→ Supported by: Settled Status Evidence.pdf
→ Extracted from page 1
```

## 15. Conflict Detection

A `ConflictCandidate` represents potentially incompatible information:

``` text
id
case_id
fact_type
current_fact_version_id
candidate_claim_id
conflict_type
severity
status
created_at
resolved_at
```

Initial types:

``` text
VALUE_MISMATCH
DATE_MISMATCH
OVERLAPPING_TRAVEL
DUPLICATE_CLAIM
AMBIGUOUS_SOURCE
```

AI may identify a conflict. AI cannot choose the trusted value.

Resolution that changes trusted state creates a new `FactVersion`.

## 16. Duplicate Claims

### Duplicate extraction

Same evidence version and extraction identity. Prevent with idempotency
and uniqueness constraints.

### Corroborating claim

Different evidence proposes the same trusted value. Do not create a
duplicate fact; add provenance when appropriate.

### Conflicting claim

Different evidence proposes a different value. Create a conflict
candidate.

## 17. Reprocessing

Reprocessing may occur after model, prompt, schema, or pipeline changes,
or after explicit retry.

It creates:

``` text
new EvidenceProcessingRun
new ExtractionRun
new ExtractedClaims
```

Previous runs and claims remain unchanged.

If reprocessing disagrees with a confirmed fact:

``` text
new claim
→ conflict candidate
→ user review
```

It never silently updates the fact.

If it agrees, it may become corroborating provenance without creating a
new fact version.

## 18. Evidence Replacement

Replacement creates:

``` text
EvidenceItem
 ├── EvidenceFile v1
 └── EvidenceFile v2
```

The old file is not overwritten. New processing targets v2. The UI
communicates that the evidence changed.

## 19. Evidence Deletion

Deleting evidence does not silently delete a confirmed fact.

``` text
confirmed Fact
↓
supporting evidence deleted
↓
Fact remains
↓
evidence support = unavailable
↓
dependent evidence/readiness projections update
↓
affected assessments become stale when required
```

Deletion lifecycle:

``` text
DELETION_PENDING
→ block new access/processing
→ delete stored object
→ mark support links unavailable
→ invalidate relevant assessments
→ update issues
→ remove sensitive derived artefacts
→ DELETED
```

A minimal tombstone may remain for historical integrity.

## 20. Fact Correction and Withdrawal

Correction creates a new `FactVersion`.

Withdrawal does not destroy historical versions. It removes the fact
from current trusted state, invalidates dependent assessments, and may
create missing-information issues.

## 21. Assessment Invalidation

Potential invalidators:

-   trusted fact version change;
-   travel record version change;
-   proposed application date change;
-   evidence-support change where evidence matters to the requirement;
-   rule version change.

``` text
trusted input changes
→ determine dependent requirements
→ mark affected current results STALE
→ recalculate
→ create immutable new results
→ previous results SUPERSEDED
```

Unconfirmed claims do not invalidate trusted assessments merely by
existing. A conflict may instead create an issue.

## 22. Domain Events

Suggested events:

``` text
EvidenceUploaded
EvidenceValidationFailed
EvidenceProcessingStarted
EvidenceProcessingCompleted
EvidenceProcessingFailed
EvidenceDeletionRequested
EvidenceDeleted
ExtractionRunCompleted
ClaimExtracted
ClaimReviewConfirmed
ClaimReviewCorrected
ClaimReviewRejected
ClaimSuperseded
FactCreated
FactVersionCreated
FactWithdrawn
FactEvidenceSupportChanged
ConflictCandidateCreated
ConflictResolved
AssessmentInvalidationRequested
```

Events should contain identifiers rather than raw sensitive values where
possible.

## 23. Transaction Boundaries

### Claim confirmation/correction

Review decision, fact creation/versioning, provenance, assessment
invalidation where relevant, and outbox event must commit consistently.

### Evidence deletion request

`DELETION_PENDING`, access/processing block, and deletion event are
atomic. Physical object deletion is asynchronous.

### Fact version change

New version, current-version pointer, stale propagation, and outbox
event commit consistently.

## 24. Idempotency

Required:

-   unique processing identifiers;
-   extraction idempotency keys;
-   claim uniqueness where appropriate;
-   review-command idempotency;
-   transactional outbox;
-   retry-safe deletion;
-   retry-safe assessment invalidation.

> Duplicate worker delivery cannot duplicate trusted domain state.

## 25. Concurrency

Potential races:

-   claim review while reprocessing completes;
-   two tabs review one claim;
-   evidence deletion during processing;
-   fact change during recalculation.

Use aggregate revisions, optimistic concurrency, explicit
current-version constraints, and exact assessment inputs.

A stale browser receives a conflict response rather than silently
overwriting newer state.

## 26. Processing Failure Semantics

-   **Validation failure:** evidence remains visible; no extraction.
-   **Text extraction failure:** visual fallback only when supported and
    safe.
-   **Model timeout:** bounded retry; no incomplete claim.
-   **Invalid schema:** failed extraction; no claim.
-   **Partial extraction:** only independently valid claims may be
    created if contract permits it; mark partial.
-   **Unsupported document:** no trusted facts; show unsupported state.

## 27. Confidence and Uncertainty

Model confidence may support internal evaluation and review
prioritisation.

It must not be presented as factual certainty or grant additional
authority.

Avoid user-facing claims such as `96% accurate`.

Prefer:

``` text
AI proposed
Review required
```

Potential review priorities:

``` text
NORMAL_REVIEW
CAREFUL_REVIEW
MANUAL_ENTRY_RECOMMENDED
```

## 28. UI Requirements

### Evidence Library

Show category, display name, processing state, review state,
availability, and relevant relationships.

### Claim Review

Desktop should support document preview alongside extracted fields and
source highlighting. Mobile should stack the experience while preserving
source context.

### Provenance

Users should be able to move conceptually from:

``` text
Requirement → Fact → Evidence
```

without seeing database complexity.

### Before/After

Corrections should show the previous value, new value, and affected
requirements.

## 29. Security Requirements

This RFC inherits `SECURITY_AND_PRIVACY_THREAT_MODEL.md`.

Specific requirements:

-   private evidence;
-   authorised short-lived signed URLs;
-   document content treated as untrusted;
-   prompt injection cannot grant authority;
-   AI cannot create facts;
-   raw evidence excluded from ordinary logs;
-   provider payload retention minimised;
-   public demo uses synthetic evidence;
-   deleted evidence becomes inaccessible;
-   queues carry identifiers rather than raw documents where possible.

## 30. Evaluation Hooks

The lifecycle intentionally produces evaluation signals.

``` text
ExtractedClaim
proposed = 2025-06-17

ClaimReviewDecision
decision = CORRECT
corrected = 2025-06-18
```

Useful structured outcomes:

``` text
claim_confirmed_without_change
claim_corrected
claim_rejected
claim_deferred
unsupported_document_confirmed
conflict_created
```

Private user review data must not automatically enter an evaluation
dataset containing personal information. Future datasets should
anonymise or recreate examples synthetically.

## 31. Illustrative API Shape

``` text
POST   /api/v1/cases/{case_id}/evidence
GET    /api/v1/cases/{case_id}/evidence
GET    /api/v1/cases/{case_id}/evidence/{evidence_id}
POST   /api/v1/cases/{case_id}/evidence/{evidence_id}/upload-url
POST   /api/v1/cases/{case_id}/evidence/{evidence_id}/process
POST   /api/v1/cases/{case_id}/evidence/{evidence_id}/retry
DELETE /api/v1/cases/{case_id}/evidence/{evidence_id}

GET  /api/v1/cases/{case_id}/claims
POST /api/v1/cases/{case_id}/claims/{claim_id}/confirm
POST /api/v1/cases/{case_id}/claims/{claim_id}/correct
POST /api/v1/cases/{case_id}/claims/{claim_id}/reject

GET /api/v1/cases/{case_id}/facts
GET /api/v1/cases/{case_id}/facts/{fact_id}/history
```

The final API contract should settle after implementation proves the
domain behaviour.

## 32. Important Database Constraints

Where practical:

-   evidence belongs to one case;
-   evidence file belongs to one evidence item;
-   extraction targets one immutable evidence file;
-   claim references one extraction run;
-   review references one claim;
-   fact version belongs to one case fact;
-   fact versions are immutable;
-   only one current fact version exists per fact;
-   assessment input cannot reference a pending claim;
-   duplicate final review decisions are prevented;
-   deleted evidence cannot initiate processing.

## 33. Test Strategy

Domain tests cover confirmation, correction, rejection, versioning,
provenance, conflicts, deletion, withdrawal, invalidation, duplicate
processing, and concurrency.

Property-based invariants include:

``` text
For any pending claim:
trusted assessment inputs never contain claim.id

For any correction:
original claim value remains unchanged

For any fact update:
old FactVersion remains retrievable

For duplicate processing:
equivalent trusted facts do not multiply

For evidence deletion:
no new signed URL can be created after DELETION_PENDING
```

Integration flows include:

``` text
upload → process → extract → confirm → fact → assessment
```

``` text
upload → wrong extracted date → correct → fact → stale assessment → recalculate
```

``` text
confirmed fact → reprocess → conflicting claim → review → new fact version
```

## 34. Canonical Demo Flow

The synthetic case should visibly exercise the lifecycle:

1.  User has a manually entered travel record.
2.  User uploads synthetic travel evidence.
3.  AI extracts departure and return dates.
4.  One date matches.
5.  One conflicts by one day.
6.  User reviews the document and proposed values.
7.  User confirms/corrects the evidence-derived information.
8.  A new trusted version is created.
9.  The affected residence assessment becomes stale.
10. Recalculation creates a new immutable result.
11. Requirement detail traces the result back to evidence.
12. Historical assessment remains inspectable.

## 35. Deferred Capabilities

Not required for MVP:

-   automatic fact confirmation;
-   autonomous evidence reconciliation;
-   bulk high-risk confirmation;
-   cross-case evidence reuse;
-   adviser approval roles;
-   vector evidence search;
-   graph database;
-   generic document chat;
-   automatic legal judgement from evidence.

## 36. Architectural Invariants

``` text
Evidence is not a fact.

An extracted claim is not a fact.

AI can create claims, never trusted facts.

Human confirmation/correction is required before AI-derived information becomes trusted.

Unconfirmed claims never influence trusted assessments.

Original AI proposals are immutable.

Corrections create new trusted versions rather than rewriting history.

Every AI-derived fact is traceable to evidence and extraction.

Reprocessing cannot silently replace a confirmed fact.

Conflicting claims require deterministic or human resolution.

Evidence deletion never silently rewrites trusted facts.

Relevant trusted-state changes make dependent assessments stale.

Historical assessments retain their exact historical inputs.

Duplicate worker delivery cannot duplicate trusted domain state.

Model confidence never grants additional authority.
```

Violation of these invariants blocks release.

## 37. Implementation Order

### Phase 1 --- Evidence Foundation

Evidence item/file, private upload, processing state, deletion, preview,
processing runs. No live AI required.

### Phase 2 --- Extraction

Extraction runs, schema-constrained extraction, claims, source locators,
failure handling.

### Phase 3 --- Human Review

Confirm/correct/reject, review decisions, facts, fact versions,
provenance.

### Phase 4 --- Downstream Integration

Assessment invalidation, conflicts, evidence coverage, requirement
provenance, reprocessing.

### Phase 5 --- Evaluation Integration

Use structured review outcomes as signals for the AI evaluation harness
without exposing private user data.

## 38. Open Questions

Resolve during implementation rather than blocking this RFC:

1.  Whether bounding boxes are available for every supported document
    pipeline.
2.  Exact temporary raw provider-response retention, if any.
3.  Whether `DEFER` needs persistent state in MVP.
4.  Whether corroborating claims add evidence links automatically or
    require acknowledgement.
5.  Exact UI treatment when a trusted fact loses all supporting
    evidence.
6.  Whether visual extraction fallback is represented as separate
    preprocessing or within one processing run.

These do not change the central trust model.

## 39. Decision Summary

-   **Separate Evidence, Claims, Facts, Assessments --- Accepted.**
-   **AI cannot create trusted facts --- Accepted.**
-   **Human review is explicit --- Accepted.**
-   **Original AI proposals survive correction --- Accepted.**
-   **Facts are versioned --- Accepted.**
-   **Reprocessing is non-destructive --- Accepted.**
-   **Conflicts are explicit product state --- Accepted.**
-   **Evidence deletion does not automatically delete facts ---
    Accepted.**
-   **Confidence does not grant authority --- Accepted.**

## 40. Definition of Done

The lifecycle is implementation-ready when:

1.  evidence can be uploaded privately;
2.  processing is asynchronous and idempotent;
3.  extraction targets immutable evidence versions;
4.  AI output creates only claims;
5.  claims support confirm/correct/reject;
6.  review preserves original proposals;
7.  accepted information creates immutable fact versions;
8.  facts trace back to evidence and claims;
9.  conflicts are explicit;
10. reprocessing cannot silently change trusted state;
11. evidence deletion has defined downstream effects;
12. relevant changes invalidate assessments;
13. concurrency cannot silently overwrite review state;
14. the synthetic demo exercises the complete lifecycle;
15. tests enforce the architectural invariants.

## Final Principle

> **AI is allowed to read and propose. The user establishes trusted
> facts. Deterministic rules decide what those trusted facts mean for
> the case.**

That boundary is the foundation of the product's trust model.
