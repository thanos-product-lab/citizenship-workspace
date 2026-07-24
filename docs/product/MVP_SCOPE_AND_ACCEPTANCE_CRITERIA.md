# Evidence-First Citizenship Workspace

## MVP Scope and Acceptance Criteria

### Status

Proposed for implementation  
Version: 0.1  
Project: Evidence-First Citizenship Workspace  
Initial route: UK naturalisation under Section 6(1), standard five-year route

---

## 1. Purpose of This Document

This document defines the first complete version of Evidence-First Citizenship Workspace.

It converts the product thesis, UX direction, and technical architecture into a precise implementation boundary.

The MVP must be:

- coherent;
- end to end;
- production-quality in execution;
- narrow enough to complete;
- strong enough to demonstrate senior product-engineering judgement;
- inspectable and explainable;
- suitable for a polished portfolio demonstration.

The MVP is not intended to prove every possible citizenship workflow.

It is intended to prove that a trustworthy AI-native product can:

1. construct a structured naturalisation case;
2. calculate residence-related requirements deterministically;
3. connect evidence to applicant facts;
4. expose uncertainty and contradictions;
5. keep AI output separate from confirmed truth;
6. explain every assessment clearly;
7. recover safely when information changes.

---

## 2. MVP Objective

> Enable a user with ILR, indefinite leave to enter, or EU settled status to construct and inspect a readiness case for the standard Section 6(1) five-year UK naturalisation route.

By the end of the MVP journey, the user should be able to understand:

- whether the supported route appears relevant;
- what application date is being assessed;
- what qualifying period applies;
- how many absence days have been recorded;
- whether the physical-presence date appears supported;
- which requirements are currently supported;
- which requirements remain incomplete;
- which facts and evidence produced each assessment;
- what contradictions or uncertainties remain;
- what action to take next.

The product must not guarantee eligibility or approval.

---

## 3. Portfolio Objective

The MVP should demonstrate that its creator can:

- turn a complex real-world process into a clear product model;
- design a calm and trustworthy high-stakes interface;
- separate deterministic logic from AI behaviour;
- build human-in-the-loop document workflows;
- model provenance and immutable assessment history;
- implement asynchronous processing;
- create accessible, production-quality frontend interactions;
- evaluate AI extraction and failure modes;
- design for security, privacy, and observability;
- own the product from discovery through deployment.

The intended hiring signal is:

> This engineer can design and build a trustworthy AI-native product end to end and can be trusted with complex product and technical decisions.

---

## 4. Supported User

### 4.1 Primary Supported User

The MVP supports an adult who:

- is at least 18 years old;
- intends to apply through the standard Section 6(1) five-year naturalisation route;
- already holds:
  - ILR;
  - indefinite leave to enter; or
  - EU settled status;
- is not applying through the British spouse or civil-partner route;
- has a broadly straightforward immigration history;
- can provide or reconstruct their travel history;
- can confirm or correct extracted facts;
- understands that the product is a preparation workspace rather than legal advice.

### 4.2 Unsupported User at MVP

The MVP must stop or clearly redirect users who indicate:

- they may already be British;
- they are applying through a British spouse or civil partner;
- they are under 18;
- they only hold pre-settled status;
- they do not yet hold ILR, ILE, or settled status;
- they are applying for registration rather than naturalisation;
- their circumstances involve unsupported complexity;
- they want the system to predict approval.

Unsupported users must not be allowed to continue through a misleading standard-route workflow.

---

## 5. Supported Requirements

The MVP supports structured readiness assessments for the following requirements.

### 5.1 Route and Status

- Adult applicant.
- Supported Section 6(1) route.
- Supported immigration status type.
- Status grant date recorded.
- Standard twelve-month status-holding period.

### 5.2 Residence

- Proposed application date.
- Five-year qualifying-period calculation.
- Physical presence in the UK on the corresponding qualifying-period start date.
- Total recorded absences during the qualifying period.
- Recorded absences during the final twelve months.
- Travel-record completeness and consistency.

### 5.3 Knowledge and Language

- Life in the UK test completion recorded.
- English-language evidence recorded.
- Evidence presence and confirmation.

The MVP confirms preparation state and evidence presence. It does not independently determine every legal validity condition for all possible certificates or exemptions.

### 5.4 Referees

- First referee recorded.
- Second referee recorded.
- Basic completion state.
- Missing referee information surfaced as an issue.

The MVP does not implement a full legal referee-eligibility engine.

### 5.5 Character and Declarations

The MVP may collect a minimal confirmation that the user has reviewed this area.

It must not:

- determine good character;
- assess criminality;
- interpret complex immigration breaches;
- provide conclusions about discretionary decisions.

Any disclosed complexity should result in:

- `Requires judgement`; or
- `Professional review recommended`.

### 5.6 Preparation

- Requirement overview.
- Evidence overview.
- Open issue queue.
- Preparation checklist.
- Case summary.

---

## 6. Requirement States

Each supported requirement has a **conclusion** (one of):

- **Supported**
- **Incomplete**
- **Inconsistent**
- **Near threshold**
- **Requires judgement**
- **Professional review recommended**
- **Not currently satisfied**
- **Not yet assessed**

…and a **currency**, tracked separately:

- **Current**
- **Stale**
- **Superseded**
- **Provisional**

A result carries both. `Supported` + `Stale` is valid and means: this was
supported under the previous inputs, which have since changed; recalculate.
Conclusion and currency are orthogonal axes and must never be collapsed into one
(Domain Model §3.5, CLAUDE.md §2.4; see ADR-0001).

The interface must not collapse these states into:

- pass/fail;
- eligible/not eligible;
- a readiness percentage.

Every state must include:

- label;
- icon or non-colour indicator;
- plain-language explanation;
- facts used;
- rule version;
- limitations;
- next action.

---

## 7. MVP Core User Journey

The MVP must support one complete journey.

### Step 1 — Start a Case

The user:

- signs in;
- creates a new citizenship case;
- sees the supported route and product boundaries;
- confirms that they understand the prototype's purpose.

### Step 2 — Confirm Route Scope

The user provides:

- age;
- current status type;
- status grant date;
- whether they are married to or in a civil partnership with a British citizen;
- whether they may already be British.

The system:

- determines whether the MVP route is supported;
- stops unsupported cases;
- creates the supported route configuration.

### Step 3 — Select a Proposed Application Date

The user:

- enters a proposed application date;
- sees the calculated qualifying period;
- sees whether the status-holding period appears satisfied.

The system:

- stores the proposed date;
- calculates the five-year qualifying window;
- creates initial residence assessments.

### Step 4 — Build Residence History

The user can:

- add trips manually;
- edit trips;
- delete trips;
- import a structured CSV travel history;
- mark dates as confirmed or uncertain.

The system:

- validates date order;
- prevents impossible ranges;
- detects overlaps;
- calculates absence days;
- identifies trips that intersect important boundaries;
- highlights the physical-presence date;
- generates or updates residence assessments.

### Step 5 — Inspect the Timeline

The user can:

- view the five-year qualifying period;
- see travel records visually;
- switch to an accessible table view;
- filter uncertain or unsupported trips;
- inspect evidence coverage;
- compare application dates.

### Step 6 — Add Core Evidence

The user can upload a limited set of supported evidence categories:

1. Immigration-status evidence.
2. English-language test evidence.
3. Life in the UK test evidence.
4. Travel-support evidence.

The system:

- validates the file;
- processes it asynchronously;
- classifies the document;
- proposes structured claims;
- shows extraction state;
- asks the user to confirm or correct claims.

### Step 7 — Confirm or Correct Claims

The user can:

- view the original document;
- inspect extracted values;
- confirm a value;
- correct a value;
- reject an irrelevant value.

The system:

- preserves the original AI proposal;
- creates a confirmed fact only after user action;
- links facts to evidence;
- recalculates dependent assessments;
- records audit history.

### Step 8 — Review Requirements

The user can open any supported requirement and inspect:

- assessment;
- facts used;
- evidence used;
- rule used;
- guidance source;
- limitations;
- next action.

### Step 9 — Resolve Issues

The system creates issues for:

- missing facts;
- missing evidence;
- overlapping trips;
- conflicting dates;
- uncertain dates;
- near-threshold absence totals;
- unsupported complexity;
- stale assessments.

The user can:

- correct data;
- confirm a source;
- add evidence;
- dismiss only non-critical informational issues;
- mark an issue for later;
- see when an issue is resolved automatically.

### Step 10 — Review Preparation Summary

The user sees:

- supported requirements;
- incomplete requirements;
- unresolved issues;
- confirmed evidence;
- travel-history summary;
- proposed application date;
- final preparation checklist.

The product must clearly state that this is a preparation summary, not an approval prediction.

---

## 8. MVP Functional Scope

### 8.1 Authentication and Cases

Included:

- sign in;
- sign out;
- create one or more cases;
- view case list;
- open case;
- delete case;
- server-side ownership checks.

Acceptance criteria:

- A signed-out user cannot access case data.
- A user cannot access another user's case by changing identifiers.
- Deleting a case removes associated database records and queued storage deletion.
- The public demo can operate with a synthetic seeded case.

---

### 8.2 Route-Scope Onboarding

Included:

- focused question flow;
- route eligibility for MVP support;
- unsupported-route stopping states;
- save and resume;
- clear scope explanation.

Acceptance criteria:

- A supported Section 6(1) user can create a case.
- A British-spouse-route user is stopped before standard-route assessments are created.
- A user without supported status is stopped.
- Each onboarding answer is persisted.
- Returning users resume from their last meaningful step.
- The flow is keyboard accessible.

---

### 8.3 Proposed Application Date

Included:

- date input;
- five-year qualifying-period calculation;
- twelve-month status-period calculation;
- date comparison;
- changed-date preview.

Acceptance criteria:

- The system derives the correct qualifying-period start date from the proposed application date.
- Invalid or impossible dates are rejected.
- Changing the application date recalculates all dependent residence assessments.
- A preview shows before-and-after effects before saving.
- The user can cancel without changing the case.
- Date calculations are tested across leap years and month boundaries.

---

### 8.4 Travel Records

Included:

- manual create;
- edit;
- delete;
- CSV import;
- confirmed or uncertain dates;
- overlap detection;
- date conflict state;
- accessible chronological table.

Required fields:

- destination;
- departure date;
- return date;
- date confidence;
- source;
- optional notes.

Acceptance criteria:

- Departure must not be after return.
- Duplicate and overlapping trips are flagged.
- Import errors identify the exact affected rows.
- A user can correct import errors before committing.
- Unconfirmed travel records remain visibly distinct.
- Travel changes create new versions rather than silently replacing history.
- Absence totals use confirmed records only for trusted assessments.
- Uncertain records are included only in provisional calculations and are clearly labelled.

---

### 8.5 Absence Calculations

Included:

- total qualifying-period absence days;
- final-twelve-month absence days;
- physical-presence date check;
- calculation breakdown;
- affected-trip list;
- stale-result handling.

Acceptance criteria:

- Calculations are server-side and deterministic.
- Every total lists the exact trips and dates used.
- The physical-presence assessment identifies the corresponding date.
- Adding a confirmed absence day cannot reduce the total.
- Changing an unrelated fact cannot alter an absence assessment.
- Old assessment results remain inspectable.
- Current and stale results cannot be confused visually or through the API.

---

### 8.6 Requirements Engine

Included:

- versioned rule definitions;
- route applicability;
- deterministic evaluators;
- immutable assessment runs;
- limitations;
- next actions;
- stale dependency handling.

Acceptance criteria:

- Every assessment result references:
  - requirement;
  - rule version;
  - exact fact versions;
  - evidence where available;
  - limitations;
  - generation time.
- An unconfirmed claim cannot affect an assessment.
- Changing a dependent fact marks the result stale.
- Recalculation creates a new assessment run.
- An unrelated requirement is not recalculated unnecessarily.
- Unsupported complexity produces an explicit non-conclusive state.

---

### 8.7 Case Overview

Included:

- case phase;
- proposed application date;
- readiness narrative;
- requirement-group summaries;
- top three priority actions;
- open issue count;
- evidence coverage summary.

Acceptance criteria:

- No readiness percentage is displayed.
- The narrative is derived from structured case state.
- The page shows no more than three priority actions.
- Every summary links to the relevant detail.
- Empty, partial, stale, and completed states are designed.
- The page remains understandable at mobile and desktop widths.

---

### 8.8 Requirement Detail

Included:

- assessment status;
- plain-language summary;
- calculation breakdown;
- facts used;
- evidence used;
- rule and guidance source;
- limitations;
- next action;
- assessment history.

Acceptance criteria:

- A user can trace an assessment from result to fact to evidence.
- AI-generated explanatory text cannot invent facts or source IDs.
- The UI distinguishes confirmed, calculated, and proposed information.
- Source links display source version and retrieval date.
- Stale results are labelled and cannot appear as current.
- The detail is keyboard and screen-reader accessible.

---

### 8.9 Evidence Upload

Included:

- direct upload to private object storage;
- PDF and common image formats;
- file-size limits;
- upload progress;
- processing progress;
- retry;
- deletion;
- supported category selection.

Acceptance criteria:

- Documents are not publicly accessible.
- Upload URLs expire.
- Unsupported file types are rejected before processing.
- The UI shows domain-specific states:
  - Uploaded;
  - Validating;
  - Extracting text;
  - Analysing;
  - Awaiting confirmation;
  - Completed;
  - Partially completed;
  - Failed;
  - Unsupported.
- Transient failures can be retried.
- Deleting evidence marks linked facts and assessments appropriately.
- Raw Celery states are never shown to users.

---

### 8.10 Document Classification and Extraction

Initial supported document types:

1. Settled-status or ILR evidence.
2. English-language test result.
3. Life in the UK test evidence.
4. Travel itinerary or booking evidence.

Included capabilities:

- document classification;
- structured field extraction;
- source-page or region reference where available;
- schema validation;
- confidence metadata;
- partial extraction;
- duplicate candidate detection.

Acceptance criteria:

- Output conforms to a versioned schema.
- Unknown fields are not accepted.
- The system preserves the original model output hash.
- Invalid structured output is retried within a fixed limit.
- Partial extraction is displayed honestly.
- Unsupported documents do not create trusted facts.
- Prompt injection content inside documents does not alter extraction behaviour.
- Every model run records cost, latency, model, prompt version, and schema version.

---

### 8.11 Claim Review

Included:

- split-view document and extracted fields;
- confirm;
- correct;
- reject;
- conflict state;
- confirmation history.

Acceptance criteria:

- AI-proposed values are visibly distinct.
- Confirming a value creates a trusted fact.
- Correcting a value preserves the original proposal.
- Rejecting a value prevents it from becoming a fact.
- Conflicting claims remain unresolved until the user chooses or provides another source.
- The system records who confirmed or corrected a value and when.
- No bulk “confirm all” action is available for high-risk date fields.

---

### 8.12 Issues

Included issue types:

- missing required fact;
- missing evidence;
- uncertain travel date;
- overlapping travel;
- conflicting claim;
- near-threshold absence total;
- stale assessment;
- unsupported complexity;
- processing failure.

Acceptance criteria:

- Every issue has:
  - type;
  - status;
  - reason;
  - affected object;
  - why it matters;
  - next action.
- Resolving the underlying cause automatically resolves the issue where appropriate.
- Critical issues cannot be dismissed without replacement action.
- Resolved issues remain available in history.
- Issue language is calm, specific, and non-alarmist.

---

### 8.13 Guidance Sources

Included:

- curated official source registry;
- requirement mapping;
- source title;
- source URL;
- retrieved date;
- content hash;
- source version;
- relevant excerpt or summary;
- unavailable-source state.

Acceptance criteria:

- Every implemented rule references at least one guidance source.
- Guidance is not scraped live during every user request.
- Source versions remain attached to historical assessments.
- A guidance update does not silently rewrite old assessments.
- The UI exposes source metadata without overwhelming the user.

---

### 8.14 Preparation Summary

Included:

- route summary;
- proposed application date;
- requirement states;
- open issues;
- evidence coverage;
- travel summary;
- final checklist;
- clear limitation statement.

Acceptance criteria:

- The summary does not state or imply guaranteed eligibility.
- Unresolved issues remain visible.
- Stale assessments cannot be included as current.
- The user can return to the affected section from each issue.
- A printable layout is supported.
- PDF export is optional for MVP completion and should not block release.

---

## 9. AI Capabilities Included in MVP

The MVP includes these narrow capabilities:

- `DocumentClassifier`
- `DocumentClaimExtractor`
- `TravelRecordExtractor`
- `ConflictCandidateDetector`

### Optional AI capabilities (not in the plan of record)

`GuidanceExplainer` and `IssueSummariser` are deferred to M9 and are the first
features cut under time pressure. The MVP's guidance value comes from the
deterministic guidance registry and rule-to-source provenance, which remain in
scope. Deterministic templates cover all core explanation needs.

### AI acceptance criteria

Every capability must have:

- typed input schema;
- typed output schema;
- model configuration;
- prompt version;
- schema version;
- retry limit;
- failure state;
- evaluation fixture;
- latency and cost recording.

AI output must never:

- create a trusted fact automatically;
- create a deterministic rule;
- make an approval prediction;
- conceal uncertainty;
- cite an unknown source;
- follow instructions embedded in uploaded evidence.

---

## 10. Explicitly Out of Scope

The MVP does not include:

- Section 6(2) British spouse route;
- children's registration;
- registration routes;
- pre-settled-status applications;
- application submission;
- integration with the official application form;
- Home Office status tracking;
- biometrics booking;
- ceremony booking;
- passport application;
- Life in the UK learning content;
- English-language coaching;
- complete referee-eligibility assessment;
- detailed good-character assessment;
- criminal-record analysis;
- discretion-heavy absence decisions;
- legal-adviser marketplace;
- solicitor collaboration;
- payments;
- public community features;
- general immigration chat;
- email or calendar integrations;
- automatic inbox scanning;
- live travel-booking imports;
- autonomous agent behaviour;
- mobile-native applications;
- multilingual support;
- multi-tenant adviser organisations;
- collaborative real-time editing;
- vector search;
- graph database;
- broad government-guidance search.

Any addition requires an explicit scope decision.

---

## 11. Non-Functional Acceptance Criteria

### 11.1 Accessibility

The MVP must:

- meet WCAG 2.2 AA for core flows;
- support keyboard navigation;
- provide visible focus states;
- avoid colour-only status communication;
- support reduced motion;
- provide an accessible table alternative to the timeline;
- associate errors with fields;
- maintain usable layouts at 200% browser zoom;
- support screen-reader descriptions for calculations.

### 11.2 Performance

Targets for the synthetic demo environment:

- Initial workspace shell: usable within 2.5 seconds on a typical broadband connection.
- Case overview API: P95 under 500 ms excluding cold starts.
- Deterministic recalculation: P95 under 300 ms.
- Timeline interaction: maintain responsive 60 fps for the canonical five-year demo case.
- Upload progress begins within 1 second.
- Document processing provides visible progress even when completion takes longer.
- No blocking model request in the primary page-render path.

These are target budgets, not legal guarantees.

### 11.3 Reliability

The MVP must:

- use idempotent background tasks;
- recover from transient provider failures;
- preserve uploaded documents when extraction fails;
- prevent duplicate processing from creating duplicate claims;
- display stale state after relevant fact changes;
- support retry from the UI;
- provide health endpoints for API and worker.

### 11.4 Security and Privacy

The MVP must:

- use synthetic data in public demos;
- keep storage private;
- use short-lived presigned URLs;
- enforce server-side ownership checks;
- use row-level security as defence in depth;
- exclude PII from logs;
- support case deletion;
- limit upload type and size;
- apply rate limits;
- keep secrets server-side;
- avoid session replay on evidence screens;
- document prompt-injection protections.

### 11.5 Observability

The MVP must record:

- request traces;
- worker traces;
- model-run traces;
- processing stage;
- latency;
- retries;
- token usage;
- estimated model cost;
- assessment recalculation;
- errors.

Telemetry must not contain raw document text or sensitive personal values.

### 11.6 Maintainability

The MVP must:

- use migrations for schema changes;
- keep domain rules outside route handlers;
- use generated frontend API contracts;
- keep prompts versioned;
- keep AI capabilities narrow;
- document significant decisions;
- avoid hidden cross-module dependencies;
- maintain strict TypeScript and Python type checks.

---

## 12. Testing Acceptance Criteria

### 12.1 Frontend

Required coverage:

- onboarding route decisions;
- case overview states;
- timeline interaction;
- application-date simulation;
- requirement detail;
- claim confirmation and correction;
- issue resolution;
- error and retry states;
- accessible keyboard journeys.

### 12.2 Backend

Required coverage:

- route scope;
- status waiting period;
- qualifying-period boundaries;
- leap years;
- absence totals;
- final-year totals;
- physical-presence date;
- stale assessment propagation;
- authorisation;
- migration safety;
- idempotent processing;
- evidence deletion effects.

### 12.3 Property-Based Rule Tests

At minimum:

```text
Unconfirmed claims never affect trusted assessments.

Adding a confirmed absence day never reduces the absence total.

Changing the proposed application date changes the qualifying period deterministically.

Changing an unrelated fact does not change an absence assessment.

A stale assessment cannot be returned as current.

Every current assessment references the latest relevant fact versions.
```

### 12.4 AI Evaluations

The MVP must include synthetic fixtures for:

- clear supported document;
- poor-quality scan;
- unsupported document;
- misleading filename;
- duplicate evidence;
- conflicting date;
- multiple dates on one page;
- incorrect applicant name;
- partial extraction;
- prompt injection text;
- model refusal;
- malformed structured output.

Required metrics:

- document classification accuracy;
- field extraction precision;
- field extraction recall;
- date extraction accuracy;
- conflict-detection precision;
- conflict-detection recall;
- citation validity;
- unsupported-document detection;
- false reassurance rate;
- cost per document;
- P50 and P95 latency.

---

## 13. Canonical Synthetic Demo Case

The MVP must include one complete synthetic applicant fixture.

The fixture should contain:

- adult Section 6(1) applicant;
- EU settled status;
- status held long enough for the proposed date;
- five-year travel history;
- total absences near but within the standard threshold;
- final-year absences clearly within the standard threshold;
- one conflicting return date;
- one travel record without supporting evidence;
- Life in the UK evidence;
- B1 language evidence;
- one completed referee;
- one missing referee;
- a proposed application date that initially fails the physical-presence check;
- an alternative date that resolves the physical-presence issue.

The fixture should produce:

- supported requirements;
- one near-threshold state;
- one inconsistent state;
- one incomplete state;
- one stale assessment after a fact change;
- a final resolved preparation state.

The same fixture should be used for:

- local seed data;
- unit tests;
- integration tests;
- Playwright tests;
- AI evaluations;
- screenshots;
- portfolio demo video.

---

## 14. Portfolio Demo Acceptance Criteria

The final demo must show this sequence:

1. Open the synthetic case.
2. Review the initial case overview.
3. Import or inspect travel history.
4. Identify a conflicting return date.
5. Upload or open supporting travel evidence.
6. Review AI-extracted date.
7. Correct or confirm the proposed value.
8. Show the old assessment becoming stale.
9. Show deterministic recalculation.
10. Inspect the updated final-year absence requirement.
11. Open facts, evidence, rule, limitations, and next action.
12. Change the proposed application date.
13. Show physical-presence assessment changing.
14. Resolve the final open issue.
15. Review the preparation summary.

The demo should make the architecture visible through the user experience without requiring viewers to understand implementation details.

---

## 15. MVP Quality Gates

The MVP cannot be considered complete until all gates pass.

### Product Gate

- The full supported journey works.
- The product does not rely on a chatbot.
- The explainability model is visible.
- Unsupported routes stop safely.
- The final preparation summary is coherent.

### UX Gate

- The overview is calm and understandable.
- The requirement detail is portfolio-quality.
- The timeline is usable and accessible.
- AI proposals and confirmed facts are visually distinct.
- Error and recovery states are implemented.
- The product does not resemble a default shadcn dashboard.

### Engineering Gate

- Deterministic rules are fully tested.
- Claims and facts are separate.
- Assessment history is immutable.
- Stale propagation works.
- OpenAPI client generation works.
- Background tasks are idempotent.
- CI passes.

### AI Gate

- Structured outputs are validated.
- Evaluation fixtures exist.
- False reassurance is measured.
- Prompt injection fixtures pass.
- Costs and latency are recorded.
- AI output cannot bypass user confirmation.

### Security Gate

- Public demo contains no real personal data.
- Ownership checks pass.
- Storage is private.
- Presigned URLs expire.
- Logs do not contain sensitive payloads.
- Complete case deletion is tested.

### Portfolio Gate

- The application is deployed.
- README is complete.
- Architecture diagram is published.
- Evaluation results are documented.
- Demo video is recorded.
- Product case study explains key decisions and rejected alternatives.
- The synthetic case can be reset and replayed reliably.

---

## 16. Definition of MVP Done

The MVP is done when:

1. A supported synthetic user can complete the full journey.
2. A supported real tester can use the private environment without developer intervention.
3. Deterministic calculations are correct across the test suite.
4. Every current assessment is traceable to exact facts, evidence, and a rule version.
5. AI-proposed values require explicit confirmation.
6. Fact changes create stale assessments and new immutable results.
7. At least four document categories can be processed or safely rejected.
8. Core screens meet the accessibility and responsive-design standard.
9. The full demo flow works reliably in the deployed environment.
10. CI, observability, security controls, and evaluation reporting are operational.
11. All explicit quality gates pass.
12. No out-of-scope feature is required to tell the product story.

---

## 17. Recommended Implementation Order

> **Canonical build order lives in `docs/IMPLEMENTATION_ROADMAP.md` (M0–M12).**
> The milestones below are an alternative framing of the same work, not the build
> sequence; where they disagree on order, the Roadmap wins.

### Milestone 1 — Foundation

- repository;
- local infrastructure;
- authentication;
- case creation;
- database migrations;
- generated API client;
- baseline design tokens;
- baseline observability.

### Milestone 2 — Deterministic Residence Slice

- proposed application date;
- travel records;
- qualifying-period calculations;
- absence calculations;
- requirement assessment;
- immutable assessment run;
- case overview;
- requirement detail;
- stale recalculation.

### Milestone 3 — Timeline and Issues

- visual timeline;
- accessible table;
- application-date simulation;
- overlap detection;
- conflict issues;
- near-threshold issue;
- issue resolution.

### Milestone 4 — Evidence Foundation

- private uploads;
- evidence metadata;
- worker pipeline;
- PDF and image processing;
- progress states;
- deletion and retry.

### Milestone 5 — Human-in-the-Loop AI

- document classification;
- structured extraction;
- claim review;
- confirm, correct, reject;
- evidence-to-fact provenance;
- conflict candidates.

### Milestone 6 — Guidance and Preparation

- guidance registry;
- source versioning;
- contextual explanation;
- preparation summary;
- printable state.

### Milestone 7 — Hardening and Portfolio

- accessibility;
- full AI evaluations;
- threat model;
- performance;
- observability;
- demo seed;
- case study;
- demo video;
- deployment polish.

---

## 18. Scope Change Rule

Any feature not explicitly included in this document must be treated as out of scope until reviewed.

A scope addition must answer:

1. Which core user problem does it solve?
2. Why is it necessary for the MVP story?
3. Which existing milestone does it affect?
4. What will be removed or delayed to make room?
5. Does it strengthen the portfolio signal enough to justify the cost?

The default answer to scope expansion is no.

---

## 19. Final MVP Statement

> The MVP is a complete, inspectable naturalisation readiness workspace for one supported route. It combines deterministic residence assessment, evidence-backed facts, human-confirmed AI extraction, visible uncertainty, and a calm high-quality interface. It does not attempt to become a general immigration platform.
