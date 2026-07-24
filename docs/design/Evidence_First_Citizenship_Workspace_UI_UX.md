# Evidence-First Citizenship Workspace

## UI/UX Direction

### Status

Discovery / Product Design  
Version: 0.1  
Product: Evidence-First Citizenship Workspace  
Initial route: UK naturalisation under Section 6(1) for adults who already hold ILR, indefinite leave to enter, or EU settled status

---

## 1. UX Thesis

> The product should help users move from uncertainty to understanding by progressively revealing what matters, explaining every assessment, and turning a fragmented naturalisation application into a clear sequence of resolvable decisions.

The interface should not resemble:

- a government portal;
- a legal case-management system;
- a generic AI chatbot;
- a static checklist;
- a dashboard full of scores.

It should feel like a calm, personal, structured workspace.

The user should always understand:

- where they are;
- what the system currently knows;
- what remains uncertain;
- why something has been assessed in a particular way;
- what they should do next.

The core UX principle is **visible control**.

---

## 2. Experience Goals

The interface should feel:

- calm;
- credible;
- precise;
- human;
- reassuring without being falsely optimistic;
- easy to navigate;
- inspectable;
- responsive;
- accessible;
- contemporary but restrained.

The product must make a complex process easier to understand without hiding important nuance.

---

## 3. Core UX Principles

### 3.1 Calm, not sterile

Calm should come from:

- strong hierarchy;
- generous spacing;
- predictable navigation;
- limited simultaneous decisions;
- readable typography;
- thoughtful defaults;
- plain language;
- visible progress.

Calm should not mean:

- hiding warnings;
- removing important detail;
- using weak contrast;
- oversimplifying legal concepts;
- turning every screen into an empty card layout.

### 3.2 Progressive disclosure

Every important assessment should be understandable at three levels.

#### Level 1 — Current state

```text
Final-year absences
Supported
```

#### Level 2 — Plain-language explanation

```text
You have recorded 51 days outside the UK during the final 12 months.
```

#### Level 3 — Full provenance

- trips included;
- dates used;
- evidence supporting each record;
- deterministic rule applied;
- guidance source;
- calculation version;
- remaining uncertainty.

The overview remains calm, while deeper reasoning is always available.

### 3.3 Action before information

Every screen should answer:

> What can the user do here?

Useful actions include:

- confirm a fact;
- correct a date;
- resolve a conflict;
- add evidence;
- review a requirement;
- mark an issue for later;
- understand why further review may be needed.

Avoid passive pages that only display information.

### 3.4 Evidence before assurance

The interface must visually distinguish:

- user-entered facts;
- AI-proposed facts;
- user-confirmed facts;
- system-calculated values;
- evidence-supported facts;
- conflicting information;
- unresolved assumptions;
- stale assessments.

The user must never mistake model confidence for verified truth.

### 3.5 One primary task per step

During onboarding and case construction, each screen should focus on one meaningful question or task.

Example:

```text
When were you granted settled status?

This helps us calculate whether you have held your status
for the required period before applying.

[ Date input ]

Where can I find this?
```

Avoid long government-form-style pages.

### 3.6 No opaque readiness score

The product should not show:

```text
You are 82% ready
```

Instead, use meaningful qualitative states:

- Building your case;
- Resolving issues;
- Nearly prepared;
- Ready for final review.

Requirement-level states should remain explicit and inspectable.

---

## 4. Information Architecture

The workspace should contain six primary areas.

```text
Case Overview
├── Readiness
├── Timeline
├── Requirements
├── Evidence
├── Issues
└── Preparation
```

### Recommended desktop navigation

```text
Citizenship Case

Overview
Timeline
Requirements
Evidence
Issues                 3
Preparation

Case settings
Data and privacy
```

At the top of the navigation:

- applicant name;
- supported route;
- proposed application date;
- current case phase.

### Mobile navigation

Use:

- a compact header;
- a case-section drawer;
- persistent access to the current issue count;
- bottom actions only where they are task-specific.

Do not replicate the desktop sidebar directly on mobile.

---

## 5. End-to-End User Journey

### Stage 1 — Welcome and scope check

The opening screen should explain:

- what the workspace does;
- which route it supports;
- what it does not do;
- that the user remains in control of extracted information.

Example:

```text
Prepare your citizenship case with clarity

Build your residence timeline, organise your evidence,
and understand how each requirement is assessed.

[ Start a case ]

Supports:
UK naturalisation for adults with ILR or settled status
under the standard five-year route.
```

The interface should lead with the user outcome, not with AI terminology.

#### Skills demonstrated

- product positioning;
- scope clarity;
- responsible expectation-setting;
- anxiety-aware onboarding.

### Stage 2 — Guided case setup

The onboarding should use a focused, adaptive card flow.

Each step should include:

- one question;
- a short explanation;
- a visible stage indicator;
- optional “Why we ask this” content;
- save-and-return behaviour;
- clear handling of unsupported routes.

Suggested stages:

```text
Your route
Your status
Your residence
Your knowledge requirements
Your case created
```

The flow should respond to facts rather than force every user through the same sequence.

Examples:

- married to a British citizen → explain that the current prototype supports a different route;
- status held for less than 12 months → show a future planning date;
- user selects a proposed application date → calculate the relevant qualifying period.

#### Skills demonstrated

- conditional form flows;
- progressive disclosure;
- product writing;
- error prevention;
- complex client state.

---

## 6. Case Overview

The case overview should be the strongest screen in the product.

It should feel like a personal readiness workspace, not an enterprise dashboard.

### 6.1 Header

```text
Your citizenship case

Proposed application date
15 April 2027

Standard five-year route
Last updated today
```

Primary actions:

- Continue preparing;
- Review open issues.

### 6.2 Readiness narrative

Use a structured summary rather than a percentage.

```text
Your case is taking shape

8 requirements are supported
2 need more information
1 needs careful review
```

Include a short structured narrative:

> Your residence history is broadly complete. The main outstanding work is confirming one return date and adding your second referee.

This narrative should be generated from trusted case state, not from unrestricted AI generation.

### 6.3 Requirement groups

Group requirements into understandable categories:

- Identity and status;
- Residence;
- Knowledge and language;
- Referees;
- Character and declarations;
- Application preparation.

Each group should show:

- current state;
- one-sentence explanation;
- outstanding item count;
- next relevant action.

### 6.4 Priority actions

Show no more than three high-priority actions.

```text
Confirm Italy return date
Travel records differ by one day.

Add second referee
You currently have one completed referee.

Review application date
You were outside the UK on the original qualifying date.
```

#### Skills demonstrated

- information hierarchy;
- decision-oriented dashboards;
- prioritisation;
- partial and completed states;
- product storytelling.

---

## 7. Signature Interaction: Requirement Explanation

The requirement detail experience should be the defining interaction of the product.

It may open in:

- a side panel;
- a focused detail page;
- a modal only for lightweight review.

A dedicated side panel or detail page is preferred for deep explainability.

### 7.1 Requirement header

```text
Final-year absences

Supported
51 recorded days outside the UK
Standard threshold: 90 days
```

Status must never rely on colour alone.

### 7.2 Explainability stack

#### Assessment

> Your confirmed travel records currently place you within the standard final-year absence threshold.

#### Why this assessment was made

```text
Final twelve-month period
16 April 2026 – 15 April 2027

Recorded absence days
51

Threshold used
90
```

#### Facts used

```text
Italy trip
4–10 May 2026
Confirmed by user
Supported by booking email

United States trip
16–29 May 2026
Extracted from itinerary
Confirmed by user
```

#### Rule used

Display:

- a plain-language explanation;
- official source;
- guidance version;
- retrieval date;
- action to open the source.

#### Limitations

```text
2 travel dates were entered manually.
1 trip has no supporting evidence.
```

#### Next action

> Add evidence for your Greece trip or confirm that the manually entered dates are correct.

### 7.3 Explainability principle

Explainability should not be implemented as a tooltip or AI-generated paragraph.

It must be represented in the domain model and reflected directly in the interface.

```text
Assessment
├── Facts used
├── Evidence used
├── Rule used
├── Limitations
└── Next action
```

#### Skills demonstrated

- trustworthy AI interaction design;
- data provenance;
- explainable system behaviour;
- complex detail hierarchy;
- interaction design for high-stakes decisions.

---

## 8. Residence Timeline

The residence timeline is the strongest opportunity to demonstrate frontend craftsmanship.

It should combine:

- visual chronology;
- travel records;
- qualifying-period boundaries;
- evidence coverage;
- date uncertainty;
- calculation results;
- issues.

### 8.1 Desktop timeline

```text
2022     2023     2024     2025     2026     2027
─────────────────────────────────────────────────
UK residence
      ├─ Spain
               ├─ Greece
                    ├──── United States
```

The view should also display:

- total absence days;
- final-year absence days;
- unconfirmed-date count;
- qualifying-period start;
- proposed application date.

### 8.2 Timeline interactions

Support:

- zooming from five years to individual months;
- hovering or focusing trips to see evidence;
- selecting a trip to open details;
- comparing conflicting dates;
- dragging uncertain boundaries with confirmation;
- highlighting the exact physical-presence date;
- previewing recalculations before saving;
- filtering by evidence status;
- switching to an accessible table view.

### 8.3 Application-date simulation

A memorable interaction should allow the user to compare potential application dates.

```text
Move proposed application date

15 April 2027
Qualifying start: 16 Apr 2022 · you were abroad (Spain, 14–20 Apr 2022)
Start-date presence: Not supported

20 April 2027
Qualifying start: 21 Apr 2022 · after your Spain trip
Start-date presence: Supported

Total absences recalculate as the whole 5-year window moves.
Preview before saving.
```

> The window moves as a whole. Clearing an absent start date means moving past
> the trip that covers it — often several days, not one. Exact totals come from
> the server; never compute them in the mockup or the client. (See ADR-0002 and
> `DETERMINISTIC_RULES_SPEC.md` §9.)

Use:

- a date scrubber;
- calendar comparison;
- direct date input;
- keyboard controls;
- clear before-and-after calculations.

#### Skills demonstrated

- complex temporal visualisation;
- data-intensive interaction design;
- accessible custom controls;
- recalculation previews;
- responsive frontend performance.

---

## 9. Evidence Workspace

The evidence area should not behave like a generic file manager.

It should expose how documents contribute to the case.

### 9.1 Evidence library

Each document should show:

- document type;
- processing state;
- extracted claims;
- requirements supported;
- confirmation state;
- detected issues;
- date added.

### 9.2 Requirement coverage

```text
English language
1 supporting document

Settled status
1 supporting document

Travel history
9 of 12 trips supported
```

This view should help the user understand evidence gaps.

### 9.3 Review queue

```text
Needs confirmation
3 extracted facts

Possible duplicate
2 documents

Unreadable page
1 document

Name mismatch
1 document
```

### 9.4 Document review split view

```text
Document preview              Extracted information

                               Name
                               Athanasios Kaloudis
                               [ Confirm ] [ Correct ]

                               Result
                               Pass
                               [ Confirm ] [ Correct ]

                               Test level
                               B1
                               [ Confirm ] [ Correct ]
```

When a field is selected:

- highlight the relevant document region;
- show extraction confidence;
- show the model and extraction version;
- allow correction;
- preserve the original proposal in history.

Every extracted field should use an explicit state:

- AI proposed;
- User confirmed;
- User corrected;
- Conflicts with another record;
- Unreadable;
- Not applicable.

#### Skills demonstrated

- document AI interface design;
- human-in-the-loop review;
- split-view interaction;
- field-level provenance;
- correction and audit patterns.

---

## 10. Issues Workspace

The issue experience should feel manageable rather than alarming.

Group issues by user action:

- Confirm information;
- Add missing evidence;
- Resolve a conflict;
- Review carefully;
- Outside supported scope.

### 10.1 Conflict issue

```text
Conflicting return date

Your travel spreadsheet says 10 May 2026.
Your booking document suggests 11 May 2026.

Why this matters
This changes your total absence calculation by one day.

[ Compare records ] [ Use 10 May ] [ Use 11 May ]
```

### 10.2 Unsupported issue

```text
This needs further review

Your immigration timeline contains a period that the
prototype cannot assess reliably.

We have paused this assessment rather than making
an uncertain conclusion.
```

Use calm, precise language.

Avoid:

- aggressive red banners;
- vague “Something went wrong” messages;
- false reassurance;
- legalistic or technical language.

#### Skills demonstrated

- error resolution;
- conflict comparison;
- high-stakes product writing;
- safe AI failure handling;
- prioritisation and recovery.

---

## 11. Preparation View

The preparation area should turn the case into a practical plan.

Suggested sections:

- Before applying;
- Application day;
- After submission;
- Biometrics;
- Decision and ceremony.

The initial prototype should keep later stages lightweight.

The primary preparation output should include:

- confirmed personal facts;
- travel-history summary;
- evidence index;
- requirement overview;
- unresolved issues;
- document checklist.

Export may later support:

- PDF;
- structured JSON;
- printable checklist.

Export should not become the main experience.

---

## 12. Role of Conversational AI

Conversational AI should be contextual and subordinate to the workspace.

Do not place a permanent large chat panel in the main interface.

Useful contextual actions include:

- Explain this requirement;
- Why is this date important?;
- What evidence supports this?;
- What should I resolve next?;
- Summarise this conflict;
- Explain how this total was calculated.

A contextual assistant panel should already know:

- the current requirement;
- confirmed case facts;
- associated evidence;
- relevant guidance;
- current limitations.

The response should reference structured case objects rather than generate unsupported general advice.

---

## 13. Visual Design Direction

### 13.1 Mood

The visual language should be:

- calm;
- trustworthy;
- contemporary;
- precise;
- non-governmental;
- non-clinical;
- human.

### 13.2 Colour

Use:

- a restrained neutral foundation;
- one confident primary accent;
- muted semantic colours.

Suggested semantic intent:

- Supported — subdued green;
- Incomplete — neutral blue or muted amber;
- Inconsistent — amber;
- Requires review — muted orange;
- Not satisfied — restrained red;
- Not assessed — grey.

Avoid:

- bright traffic-light dashboards;
- neon AI colours;
- gradients used without purpose;
- overuse of red;
- relying on colour alone.

### 13.3 Typography

Typography should support:

- strong hierarchy;
- long-form readability;
- high numeric clarity;
- clear date formatting;
- comfortable line lengths;
- accessible contrast.

Dates, thresholds, and calculations should receive deliberate typographic emphasis.

### 13.4 Surfaces

Prefer:

- soft borders;
- minimal shadows;
- spacious panels;
- clear selected states;
- consistent side panels;
- subtle section backgrounds;
- page-level structure.

Avoid an interface made entirely from floating cards.

### 13.5 Iconography

Use icons to support recognition for:

- Requirement;
- Evidence;
- Timeline;
- Issue;
- Source;
- Confirmation.

Do not use generic AI sparkle icons throughout the product.

---

## 14. Motion and Feedback

Motion should explain state changes.

Appropriate uses:

- expanding assessment provenance;
- connecting evidence to a requirement;
- recalculating the timeline after a date change;
- moving an issue into the resolved state;
- revealing extracted document fields;
- showing before-and-after values;
- indicating stale assessments after source facts change.

A signature animation may show:

```text
Document → Extracted fact → Confirmed fact → Requirement assessment
```

Avoid decorative motion that reduces credibility.

Support reduced-motion preferences.

---

## 15. Accessibility

Accessibility should be part of the portfolio story.

The product should include:

- keyboard-accessible navigation;
- keyboard-accessible timeline controls;
- non-colour status indicators;
- clear focus states;
- screen-reader descriptions for calculations;
- reduced-motion support;
- accessible document review;
- plain-language explanations;
- responsive layouts at realistic zoom levels;
- errors attached to their relevant fields;
- no critical information hidden only in tooltips;
- an accessible table alternative to the visual timeline.

The timeline should be designed as both:

- a rich visualisation;
- a semantically equivalent chronological table.

---

## 16. Production States to Design

The UI should intentionally support:

- empty case;
- incomplete onboarding;
- saved draft;
- document upload;
- document processing;
- extraction completed;
- extraction partially failed;
- unsupported document;
- duplicate evidence;
- conflicting facts;
- no travel recorded;
- near-threshold absence total;
- unsupported route;
- source unavailable;
- recalculation in progress;
- stale assessment;
- offline or network failure;
- completed case;
- deleted evidence;
- restored or retried processing.

A strong portfolio demonstration should show both success and recovery states.

---

## 17. Design System Requirements

The design system should include clear patterns for:

- case phases;
- requirement states;
- evidence states;
- issue severity;
- source provenance;
- AI proposal versus user confirmation;
- calculated versus entered values;
- stale data;
- missing data;
- contextual explanations;
- side panels;
- split-view review;
- timeline events;
- comparison states;
- inline validation;
- empty and error states.

Important reusable components may include:

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
- `ContextualAssistantTrigger`;
- `ConfidenceIndicator`;
- `StaleAssessmentNotice`.

The design system should represent domain meaning, not only visual styling.

---

## 18. Strong Skill Signals

### 18.1 Product thinking

The project should visibly demonstrate the decision to reject:

- a generic chatbot;
- an eligibility percentage;
- a static checklist;
- a government-form clone;
- automatic trust in model output.

The final case study should explain why the product is organised around:

- evidence;
- requirements;
- issues;
- provenance;
- user confirmation.

### 18.2 UX design

The interface should demonstrate:

- progressive disclosure;
- anxiety-aware language;
- adaptive onboarding;
- temporal reasoning;
- conflict resolution;
- evidence review;
- explainability;
- safe escalation;
- accessible complex interactions.

### 18.3 Frontend engineering

The strongest technical UI components should be:

- interactive multi-year timeline;
- application-date simulator;
- requirement provenance panel;
- document-review split view;
- evidence-to-requirement visualisation;
- optimistic issue resolution with undo;
- responsive information-dense layouts;
- keyboard and screen-reader alternatives.

### 18.4 AI product engineering

The interface should show:

- AI proposals separated from confirmed facts;
- field-level extraction confidence;
- structured extraction;
- evidence mapping;
- contradiction detection;
- contextual explanation;
- model failure and retry states;
- prompt or model versioning where relevant;
- evaluation-aware design.

### 18.5 Systems thinking

Every visible UI state should map to a real domain state.

```text
AI proposed
User confirmed
User corrected
System calculated
Evidence supported
Conflicting
Incomplete
Stale
Unsupported
```

The interface should not collapse these into generic loading, success, and error states.

---

## 19. Recommended Portfolio Demo Flow

Use one realistic synthetic applicant case.

### Demo sequence

1. Create a standard five-year naturalisation case.
2. Enter settled-status information.
3. Import a travel-history spreadsheet.
4. Show the system constructing the residence timeline.
5. Reveal one conflicting return date.
6. Upload a supporting booking document.
7. Show AI extracting the return date.
8. Require user confirmation.
9. Recalculate the absence total.
10. Open the final-year absence requirement.
11. Inspect facts, evidence, rule, and limitations.
12. Move the proposed application date.
13. Show the physical-presence result changing.
14. Resolve the final open issue.
15. Present the preparation summary.

This demonstrates:

- product narrative;
- frontend craft;
- AI extraction;
- deterministic reasoning;
- explainability;
- conflict resolution;
- recovery;
- end-to-end ownership.

---

## 20. Recommended Design Sequence

Design the product in this order:

1. Case overview;
2. Requirement detail and explainability model;
3. Residence timeline;
4. Issue-resolution flow;
5. Evidence review;
6. Application-date planner;
7. Onboarding;
8. Preparation summary;
9. Contextual AI;
10. Settings and secondary screens.

Do not begin with:

- landing page;
- login;
- pricing;
- generic design-system components.

First prove that the core workspace and explainability interaction are exceptional.

---

## 21. UX North Star

The finished product should make the user feel:

> This is complicated, but I understand my position. I can see what is known, what is uncertain, and what I need to do next.

It should make a founder or hiring manager think:

> This engineer understands how to design and build trustworthy AI products, not just attractive interfaces.

---

## 22. Next Phase

The next phase is technical architecture and technology selection.

The stack should be chosen to support:

- a rich React-based workspace;
- accessible temporal visualisation;
- deterministic rule execution;
- document ingestion and extraction;
- background processing;
- secure file storage;
- structured AI outputs;
- model and prompt versioning;
- observability;
- synthetic evaluations;
- explainable provenance;
- reliable deployment.
