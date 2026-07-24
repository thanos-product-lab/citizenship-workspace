# Evidence-First Citizenship Workspace

## Product Thesis

### Status

Discovery phase  
Version: 0.1  
Initial route: UK naturalisation under Section 6(1) for adults who already hold ILR, indefinite leave to enter, or EU settled status

---

## 1. Purpose

Evidence-First Citizenship Workspace is a private, non-commercial AI product prototype created as part of AI Product Studio.

Its purpose is to demonstrate production-quality product engineering in a high-stakes, evidence-heavy workflow.

The product is intended for:

- portfolio demonstrations;
- synthetic applicant scenarios;
- the creator's own completed citizenship journey;
- limited usability testing with friends.

It is not intended to operate as a public immigration service, replace regulated legal advice, predict Home Office decisions, or submit applications on behalf of users.

---

## 2. Product Thesis

> Evidence-First Citizenship Workspace helps adults with ILR or settled status turn fragmented residence history, documents, personal facts, and official guidance into a clear and inspectable UK naturalisation readiness case.

The product does not ask users to trust an opaque AI conclusion.

It shows how every assessment was produced:

> Requirement → Applicant facts → Evidence → Rule → Assessment → Uncertainty → Next action

The central product idea is that confidence must come from traceable evidence, deterministic calculations, and visible uncertainty—not from an AI-generated eligibility score.

---

## 3. The Problem

Preparing a UK naturalisation application is difficult even for applicants with relatively straightforward circumstances.

Relevant information is distributed across:

- government guidance;
- caseworker guidance;
- immigration status records;
- passports;
- travel bookings;
- test results;
- referee information;
- personal records;
- the online application process.

Applicants must reconstruct several years of personal history and determine:

- which naturalisation route applies;
- when they may be ready to apply;
- whether their residence history fits the standard requirements;
- whether they were physically present in the UK on the relevant date;
- which documents support each requirement;
- whether records contain gaps or contradictions;
- which circumstances require further review.

The information is available, but the applicant must transform it into a coherent case.

Existing checklists and calculators usually treat these tasks separately. General-purpose AI assistants can explain guidance, but they do not provide a durable, verifiable case model.

---

## 4. Target User

### Primary user

An adult who:

- lives in the UK;
- already holds ILR, indefinite leave to enter, or EU settled status;
- is considering naturalisation under the standard five-year route;
- expects their case to be broadly straightforward;
- wants to prepare carefully before using the official application service;
- has travel, identity, status, test, and referee information spread across different sources;
- feels uncertain about dates, evidence, or overlooked requirements.

### Core user statement

> I believe I may qualify for British citizenship, but I want to understand exactly what supports my case, what is still missing, and whether anything needs further review before I apply.

---

## 5. Product Promise

The product helps the user construct a Citizenship Readiness Case containing:

- the supported naturalisation route;
- a proposed application date;
- the relevant qualifying period;
- a structured residence and absence timeline;
- confirmed applicant facts;
- an evidence inventory;
- requirement-by-requirement assessments;
- contradictions and missing information;
- official-source references;
- unresolved questions;
- a preparation checklist.

The product should leave the user with a better-organised and better-understood case.

It should not guarantee approval.

---

## 6. Core Product Model

The primary domain object is an **Application Case**.

```text
Application Case
├── Applicant
├── Naturalisation Route
├── Proposed Application Date
├── Qualifying Period
├── Immigration Status
├── Residence Timeline
├── Absence Records
├── Knowledge Requirements
├── Referees
├── Evidence Items
├── Extracted Claims
├── Requirement Assessments
├── Issues
├── Guidance Sources
└── Preparation Milestones
```

The key relationship is:

```text
Requirement
    evaluated against
Applicant facts
    supported by
Evidence
    interpreted using
Versioned official guidance
    producing
Assessment + explanation + uncertainty
```

The product is a structured case workspace, not a chat transcript.

---

## 7. Core User Experience

The initial experience should guide the user through six connected stages.

### 1. Route and scope confirmation

Collect the minimum facts required to determine whether the supported Section 6(1) route appears relevant.

The system should stop early when the user may require:

- a different nationality route;
- the British spouse route;
- registration rather than naturalisation;
- professional review;
- functionality not supported by the prototype.

### 2. Application-date planning

Calculate and explain possible application dates using:

- immigration status grant date;
- the required status-holding period;
- qualifying-period boundaries;
- physical presence on the corresponding start date;
- absence history;
- incomplete requirements.

The product should explain why a date may be invalid, possible, or better supported.

### 3. Residence and absence reconstruction

Allow users to:

- enter travel manually;
- import structured travel history;
- upload supporting records;
- mark dates as confirmed or uncertain;
- resolve overlaps and contradictions.

The timeline should make qualifying-period calculations understandable.

### 4. Requirement map

Present each relevant requirement as an inspectable assessment rather than a single eligibility score.

Each assessment should expose:

- current state;
- facts used;
- evidence used;
- applicable rule;
- unresolved questions;
- recommended next action.

### 5. Evidence workspace

Classify and organise documents, extract structured claims, and map evidence to the requirements it may support.

AI-extracted facts must remain untrusted until the user confirms them.

### 6. Issue resolution and preparation

Create a focused queue of:

- missing information;
- conflicting dates;
- unsupported claims;
- incomplete evidence;
- near-threshold conditions;
- circumstances outside the supported route.

The final output is a preparation pack for the user, not an application submission.

---

## 8. Readiness States

The product should avoid simplistic pass/fail language.

Each requirement may use one of the following states:

- **Supported** — confirmed facts and evidence appear to support the standard requirement.
- **Incomplete** — required information or evidence is missing.
- **Inconsistent** — available records conflict.
- **Near threshold** — the requirement appears within a standard threshold but with limited margin.
- **Requires judgement** — deterministic rules alone cannot provide a reliable conclusion.
- **Professional review recommended** — the circumstances fall outside the prototype's safe support boundary.
- **Not currently satisfied** — a clear deterministic condition is not currently met.
- **Not yet assessed** — the user has not supplied enough information.

These states are more honest and useful than an overall readiness percentage.

---

## 9. AI-Native Value

AI is used where language, documents, and ambiguity create genuine value.

### Appropriate AI responsibilities

- classify uploaded documents;
- extract names, dates, status information, and document references;
- transform free-text travel notes into structured records;
- propose links between evidence and requirements;
- identify potential contradictions;
- generate targeted follow-up questions;
- explain official guidance in accessible language;
- summarise unresolved case issues;
- detect when a scenario may fall outside supported patterns.

### Deterministic responsibilities

Traditional application logic should handle:

- date arithmetic;
- qualifying-period calculation;
- absence totals;
- threshold comparisons;
- status waiting periods;
- physical-presence checks;
- readiness-state transitions;
- evidence-completeness rules;
- guidance-version selection.

### Human responsibilities

The user must:

- confirm extracted facts;
- resolve uncertain dates;
- approve evidence mappings;
- provide disclosures;
- decide whether to apply;
- seek professional advice where appropriate.

The system must not silently turn model output into trusted case facts.

---

## 10. Trust and Explainability

Every meaningful assessment should expose five layers:

1. **Assessment**  
   What the system currently concludes.

2. **Facts used**  
   Which confirmed applicant facts influenced the assessment.

3. **Evidence used**  
   Which documents or records support those facts.

4. **Rule used**  
   Which versioned official source or deterministic rule was applied.

5. **Limitations**  
   Which uncertainties, assumptions, or unverified records remain.

Example:

```text
Assessment
Your recorded final-year absences are within the standard threshold.

Facts used
51 recorded absence days during the final twelve months.

Evidence used
12 travel records, of which 10 are supported by uploaded records.

Rule used
Section 6(1) final-year absence rule from the currently selected guidance version.

Limitations
Two dates were entered manually and have not been independently confirmed.
```

Inspectable reasoning is the central interaction and the primary differentiator.

---

## 11. Product Principles

1. **Evidence before confidence.**
2. **Rules before generation.**
3. **Uncertainty must be visible.**
4. **No conclusion without provenance.**
5. **AI-extracted facts require confirmation.**
6. **Never hide complexity behind a readiness score.**
7. **Stopping and escalating can be a successful outcome.**
8. **Official guidance must be versioned.**
9. **Collect only information required for the supported experience.**
10. **Design for anxious non-expert users without oversimplifying the truth.**
11. **The workspace organises and explains; it does not guarantee approval.**
12. **The primary interface is the case model, not a chatbot.**

---

## 12. Initial Scope

### Included in the first product version

- private user account and case workspace;
- Section 6(1) onboarding;
- route-scope validation;
- proposed application-date planner;
- qualifying-period calculation;
- residence and absence timeline;
- manual and structured travel-history import;
- requirement engine;
- evidence upload;
- document classification;
- structured claim extraction;
- user confirmation of extracted facts;
- evidence-to-requirement mapping;
- readiness assessments;
- issue-resolution queue;
- versioned official-source references;
- synthetic evaluation suite;
- preparation summary and checklist.

### Explicitly excluded

- public commercial usage;
- application submission;
- approval prediction;
- every nationality or visa route;
- British spouse route in the first version;
- children's registration;
- detailed good-character decisions;
- discretion-heavy case assessment;
- criminal or complex immigration-history assessment;
- Life in the UK course content;
- English-language coaching;
- ceremony booking;
- passport application support;
- solicitor marketplace;
- payments;
- community forums;
- Home Office application-status integration.

---

## 13. Differentiation

The product is not:

- a general immigration chatbot;
- a static document checklist;
- an absence calculator;
- a government-guidance search engine;
- an AI-generated eligibility percentage;
- a clone of the official application form.

Its distinctive product wedge is:

> An inspectable evidence graph and temporal case model that connects naturalisation requirements to confirmed applicant facts, supporting evidence, versioned guidance, and visible uncertainty.

The hard problem is not answering isolated citizenship questions.

The hard problem is constructing a coherent, reviewable case from incomplete and potentially conflicting information.

---

## 14. Portfolio Objective

The project should demonstrate that its creator can:

- identify and model a difficult real-world workflow;
- design for trust in a high-stakes AI experience;
- separate deterministic logic from probabilistic model behaviour;
- build structured document-processing pipelines;
- create durable domain models;
- handle temporal reasoning;
- design sophisticated frontend interactions;
- evaluate model performance and failure modes;
- implement privacy-conscious production architecture;
- take a product from discovery through deployment.

The intended portfolio signal is:

> This engineer can own an AI-native product end to end and can be trusted to make careful product and technical decisions when AI output affects real users.

---

## 15. Production-Quality Standard

Although the project is private and non-commercial, it should be engineered as a credible production system.

The finished project should include:

- authentication;
- secure document storage;
- explicit access controls;
- data deletion;
- background document processing;
- retry and recovery states;
- structured logging;
- monitoring and error tracking;
- model and prompt versioning;
- cost and latency tracking;
- automated tests;
- CI/CD;
- architecture documentation;
- threat modelling;
- synthetic case fixtures;
- AI evaluation results;
- a deployed demonstration;
- a polished product walkthrough;
- a technical case study.

Production quality refers to engineering discipline and product completeness, not commercial scale.

---

## 16. Success Criteria

The prototype is successful when:

- a user can construct a complete, understandable readiness case;
- every assessment can be traced to facts, evidence, and a rule;
- uncertain or conflicting records are surfaced rather than hidden;
- AI-extracted facts are never accepted without confirmation;
- deterministic calculations are accurate across the evaluation suite;
- unsupported cases are stopped or escalated appropriately;
- users understand what remains unresolved;
- the interface makes a complex process feel controlled and navigable;
- the project presents a compelling production-quality AI engineering case study.

Potential evaluation metrics include:

- document-classification accuracy;
- field-extraction accuracy;
- travel-record reconstruction accuracy;
- contradiction-detection precision and recall;
- requirement-state accuracy;
- false-reassurance rate;
- correct unsupported-case escalation rate;
- percentage of assessments with complete provenance;
- time required to construct a readiness case.

---

## 17. North-Star Experience

The product's defining moment should be when a user opens one naturalisation requirement and can immediately understand:

- what the requirement means;
- whether their current case appears to support it;
- which facts were used;
- where those facts came from;
- what remains uncertain;
- what they should do next.

The user should feel:

> I understand my case. I can see what the system knows, why it reached this assessment, and where I still need to take action.

---

## 18. One-Sentence Pitch

> Evidence-First Citizenship Workspace is a private AI product prototype that helps adults with ILR or settled status transform residence history, documents, and official guidance into a clear, evidence-backed, and inspectable UK naturalisation readiness case.

---

## 19. Next Phase

The next phase is UX and UI definition.

The immediate design work should focus on:

1. the end-to-end user journey;
2. the information architecture;
3. the case overview;
4. the application-date planner;
5. the residence timeline;
6. the requirement detail view;
7. the evidence workspace;
8. the issue-resolution experience;
9. the visual language for confidence, uncertainty, and provenance;
10. the role, if any, of conversational AI within the workspace.
