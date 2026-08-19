> **Review status.** The diagnosis in this brief is accepted: the page has too many
> layers explaining one state. The blocks marked **Amendment** below are corrections
> where a prescription would contradict the domain model or an existing ADR. They are
> annotations on the original, not replacements — the surrounding text is unchanged.
> Anything not marked is accepted as written.
>
> Amendments carry a reason. Where one says "contradicts the engine", it means the
> proposed UI would state something the assessment code does not.

You are working on the **Evidence-First Citizenship Workspace**, an AI-native product that helps UK citizenship applicants understand whether they are ready to apply, what evidence supports their eligibility, and what still requires attention.

We need to redesign the **Case Overview** screen.

## Product principles

Use these principles throughout the redesign:

- Outcome-oriented
- Readiness first
- Clarity over complexity
- Trust over engagement
- Guidance over pressure
- Accessibility by default
- Evidence before confidence
- Progressive disclosure
- High information hierarchy
- Calm, premium, professional UI

The product should feel closer in quality and restraint to products such as **Linear, Stripe and GOV.UK's best transactional experiences**, rather than a conventional admin dashboard.

Do not blindly copy any of those products.

---

# Problem

The current Case Overview is visually clean but too text-heavy.

Before reaching the actual requirement assessment, the user currently encounters:

- case name
- case status
- proposed application date
- route
- last assessed date
- a readiness headline
- four assessment statistics
- an explanatory paragraph
- a "What to do next" section
- requirement name
- recommendation
- another warning explaining the same issue

The problem is not primarily typography or spacing.

The page contains **too many layers explaining the same state**.

The interface should allow a user to understand within a few seconds:

1. What is the state of my case?
2. What needs my attention?
3. What should I do next?

Everything else should be secondary.

---

# Design direction

Refactor the page hierarchy toward:

## 1. Case identity

Show:

**Amara Okonkwo**

with an appropriate case/readiness status.

Avoid having both a status badge and another large sentence that communicate essentially the same thing.

For example, reconsider the current combination of:

- `Resolving issues`
- `There's work to do on your case`

Prefer one clear state.

Potential language:

- `Needs attention`
- `Assessment incomplete`

Be careful with absolute statements such as `Not ready to apply` when several requirements have not yet been assessed.

The interface must accurately represent uncertainty.

> **Amendment — keep the domain's own state names.**
>
> "Prefer one clear state" is right, and the duplication is real. But the resolution is
> to **stop rendering the phase twice**, not to invent new labels for it.
>
> The phase is a derived domain value with five named states (`SETTING_UP`,
> `BUILDING_CASE`, `RESOLVING_ISSUES`, `NEARLY_PREPARED`, `FINAL_REVIEW`) — see
> ADR-0009, which also records that the ladder is a documented rule with a test table.
> `Needs attention` and `Assessment incomplete` are not among them. Introducing them
> means either the UI diverging from the enum, or renaming `CasePhase`, which is a
> Domain Model RFC change and needs its own argument.
>
> Concretely: keep the pill (labelled — it currently has no "Case phase:" prefix for
> screen readers), drop the prose heading that restates it, and let level 2 lead.
>
> The warning about `Not ready to apply` is exactly right and applies to any replacement
> label too, including the two proposed here.

---

## 2. Essential case metadata

Keep:

- Proposed application date
- Route
- Last assessed

Make this area concise and easy to scan.

It can remain horizontally arranged on desktop.

Do not give metadata equal visual prominence to readiness/action information.

Consider simplifying values where appropriate while preserving accuracy.

---

## 3. Readiness summary

The current screen gives equal prominence to:

- 1 not currently satisfied
- 1 near threshold
- 7 supported
- 6 not yet assessed

This requires the user to interpret the assessment model.

Instead, lead with the information that affects the user.

For example:

**2 requirements need attention**

Then show secondary context more quietly:

`1 blocker · 1 close to threshold · 7 supported · 6 not assessed`

or another concise variation.

The exact wording should come from the underlying domain states rather than hardcoded presentation assumptions.

Do not hide the fact that requirements remain unassessed.

> **Amendment — "2 requirements need attention" contradicts the engine.**
>
> This is the one prescription that must not ship as written.
>
> The example groups the blocker with the near-threshold requirement. The assessment code
> does not: `_NEEDS_ATTENTION_FROM = severity(REQUIRES_JUDGEMENT)` (severity 3), and
> `NEAR_THRESHOLD` is severity 2. For this exact case the API returns
> **`needs_attention: 1`**, not 2. The same boundary decides the case phase, so the
> headline would also disagree with the pill directly above it.
>
> Near-threshold is deliberately a caution rather than a task — 439 against a threshold
> of 450 is not something the user can act on, and calling it "needs attention" both
> overstates it and dilutes the one thing that genuinely blocks.
>
> Use the count the server already computes:
>
> **1 requirement needs your attention**
> `1 near threshold · 7 supported · 6 not assessed`
>
> If you want near-threshold promoted into the attention bucket, that is a change to
> `_NEEDS_ATTENTION_FROM` with consequences for the phase ladder and the group summaries
> — argue it as a domain change, not a presentation one.
>
> Two constraints on the secondary line: the counts must stay **ordered by severity**
> (the server emits them that way — ordering by magnitude would lead with the most
> reassuring state), and the sentence must never render as a fraction. "1 of 15" is a
> readiness score arrived at sideways, which CLAUDE.md §2.6 forbids and two tests
> currently assert against.

---

# 4. Immediate action

Replace the existing verbose **"WHAT TO DO NEXT"** card with a stronger actionable section.

Prefer a heading such as:

**Needs your attention**

rather than generic dashboard language.

For the current issue, the information hierarchy could resemble:

**Presence on the first day**  
`Blocking`

Your proposed application date doesn't meet this requirement.

**Consider applying from 25 April 2027**

`Review requirement →`

The exact copy may differ if existing domain terminology makes another formulation more accurate.

> **Amendment — three problems in this example, all fixable.**
>
> **1. `Blocking` is not a conclusion.** It is a property of a *next action*
> (`NextAction.blocking`). The status-semantics section below lists it alongside
> supported / near threshold / not assessed, which are conclusions. Rendering it where a
> conclusion badge sits invites reading it as a ninth conclusion state, and collapsing
> those two axes is the failure ADR-0001 exists to prevent, one axis over. Keep the
> conclusion badge (`Not currently satisfied`) and express blocking through position and
> weight, or a visibly different treatment.
>
> **2. "Your proposed application date doesn't meet this requirement" is new prose about
> an assessment.** Every such sentence today is server-rendered from a summary code in
> `app/requirements/messages.py` — that is the §2.2 determinism rule, not a style
> preference, and a source-scan test fails if a code ships without a template. It is also
> subtly wrong: the requirement fails because *confirmed travel records place the
> applicant outside the UK on the anchor date derived from* that date. The date is not
> itself the defect.
>
> **3. "Consider applying from 25 April 2027" overstates the rule.** The server says
> "Consider moving your proposed application date to 25 April 2027." Yours reads as advice
> about when to *apply*. The product does not tell people when to apply, and that date
> only clears **confirmed** absence — an unconfirmed trip could still cover it, which is
> why the wording hedges.
>
> The redundancy point stands: drop the blocking sentence and let hierarchy carry it.
> Achieve that by removing a line, not by writing new ones.

Important:

The current card effectively communicates the same idea multiple times:

- consider moving the application date
- the requirement is not satisfied
- the requirement cannot be satisfied until resolved

Remove redundant explanation.

Use hierarchy, status and typography instead of additional prose.

---

# 5. Full requirement assessment

After the immediate action area, transition quickly into the actual requirements.

For example:

## Requirements

Then the relevant requirement groups such as:

- Residence
- English language
- Life in the UK
- Good character
- etc.

The overview should not delay the user reaching the substantive assessment.

> **Amendment — name the actual cause.**
>
> The overview's length is the smaller half of this problem. The page order is:
>
> ```
> CaseOverviewPanel  →  ResidencePanel  →  RequirementsList
> ```
>
> `ResidencePanel` is the proposed-application-date form plus a twelve-row travel-record
> table. An **input-editing surface sits between the summary and the assessment**. Even a
> perfectly tight overview leaves the requirements below a data-entry table.
>
> Moving `RequirementsList` above `ResidencePanel` in `CaseWorkspace.tsx` does more for
> this acceptance criterion than every copy cut in this brief combined. Travel editing
> then reads as what it is — the inputs behind the assessment, available underneath it.

---

# Information architecture

Aim for this conceptual hierarchy:

### Level 1 — Case

Amara Okonkwo  
`Needs attention`

### Level 2 — Readiness

**2 requirements need attention**

Secondary assessment information

### Level 3 — Immediate action

**Presence on the first day** `Blocking`

Your proposed application date doesn't meet this requirement.

**Consider applying from 25 April 2027**

`Review requirement →`

### Level 4 — Assessment

Requirements and their evidence/readiness states.

> **Amendment — this section restates the amended examples.**
>
> The four levels are the right shape and are accepted. The *sample copy* inside them is
> the same text corrected above, so implementing from this section alone would reintroduce
> all of it. Apply, in order:
>
> | Level | Shown here | Use instead | Why |
> |---|---|---|---|
> | 1 | `Needs attention` | the domain phase, rendered once | not a `CasePhase` value — §1 amendment |
> | 2 | **2 requirements need attention** | **1 requirement needs your attention** | the API returns `needs_attention: 1` — §3 amendment |
> | 3 | `Blocking` beside the title | conclusion badge; blocking via hierarchy | conclusion ≠ action property — §4 amendment |
> | 3 | "Your proposed application date doesn't meet…" | the server's `summary.text` | assessment copy is server-rendered — §4 amendment |
> | 3 | **Consider applying from 25 April 2027** | the server's action `text` | "applying from" overstates the rule — §4 amendment |
>
> Level 4 also needs the ordering fix from §5: `RequirementsList` above `ResidencePanel`.

---

# Visual design

The current screen has an unusual combination of:

- lots of whitespace
- lots of text

Improve the density without making the interface feel crowded.

Consider:

- slightly wider main content container where appropriate
- stronger hierarchy
- shorter copy
- quieter metadata
- fewer explanatory paragraphs
- clear spacing between conceptual sections
- restrained use of borders
- restrained use of cards
- status indicators that are easy to distinguish
- high-quality typography
- strong desktop and responsive layouts

Do not solve the issue by simply reducing font sizes.

Do not turn the page into a collection of dashboard cards.

Avoid excessive badges, coloured panels, icons or decorative elements.

The interface should remain calm and serious because this is a high-stakes immigration workflow.

---

# Status semantics

Status is important in this product.

Clearly distinguish states such as:

- supported
- needs attention
- blocking
- near threshold
- not assessed
- unable to assess / insufficient evidence, if supported by the domain model

Do not rely on colour alone.

Status components should have accessible text labels.

Do not make non-interactive status badges look like buttons.

---

# Trust and evidence

This is an **evidence-first** product.

The interface must never communicate more certainty than the assessment engine actually possesses.

For example:

If 6 requirements are not assessed, do not confidently state that the applicant is categorically "not ready" unless the existing domain model genuinely supports that conclusion.

Prefer language that distinguishes:

- confirmed problems
- potential risks
- unknown/unassessed requirements
- supported requirements

The UI should make uncertainty understandable rather than hiding it.

> **Amendment — one sentence marked for cutting is load-bearing.**
>
> "Requirements that haven't been assessed yet aren't counted here" reads as the kind of
> explanatory prose this brief wants removed. It is not filler: a trust review found the
> attention line was a claim about the whole case computed only over *assessed*
> requirements with a severe conclusion, and that sentence is the bound on its scope.
>
> Cut it and the line silently widens back into an overstatement. If the redesign changes
> how attention is counted, the bound has to change with it — it cannot simply go.

---

# Interaction

Where an issue can be investigated, provide a clear path such as:

`Review requirement →`

The overview itself should remain a summary.

Detailed:

- reasoning
- evidence
- rule interpretation
- calculations
- source material

should live within the requirement detail experience rather than being duplicated in the overview.

Use progressive disclosure.

---

# States to design

> **Added in review.** The brief specifies one state — an assessed case with a blocker.
> The panel renders at least six. A redesign that only describes the happy path reliably
> produces a layout that breaks on the rest; UI/UX §16 exists because of this.
>
> Each of these is live today and must survive the redesign.

**Stale.** The product's signature moment. After a travel or date change, the case carries
*"5 conclusions have not been rechecked since your inputs changed"*, each group heading
gains *"N conclusions are stale"*, and the counts **do not move** — the conclusions are
preserved and only their currency changed (ADR-0001, extended to groups by ADR-0010).

This is the hardest state for the proposed hierarchy. A single headline of
*"1 requirement needs your attention"* has nowhere to say that five conclusions are
un-rechecked, and staleness is not attention — it is a different axis. Design where it
sits before collapsing the counts.

**Updating.** While a refetch is in flight after a write: *"Updating — these figures are
from before your last change."* Without it the summary presents superseded counts as
current for the duration.

**Nothing assessed yet.** A freshly activated case: 15 not yet assessed, no application
date, no actions, no last-assessed. The metadata row loses two of its three values. The
"needs attention" headline has nothing to count.

**No actions, but not clean.** A case with limitations and no next action. The action
section must not read as "nothing to do" — that is false reassurance.

**Summary unavailable.** When the overview fetch fails the panel is replaced by a line
saying so, because the priority actions exist nowhere else on the screen and their absence
must not read as "no actions". Group headings then fall back to a plain count rather than
asserting a stale marker from a payload that failed to refresh.

**Superseded / provisional.** `PROVISIONAL` results arrive with the M6 date simulator. The
group currency ordering already places them; their presentation is undesigned. Worth
leaving room rather than discovering it later.

---

# Accessibility

Maintain a high accessibility standard.

Ensure:

- semantic heading hierarchy
- keyboard-accessible interactions
- visible focus states
- sufficient colour contrast
- status does not depend on colour alone
- links/buttons have clear accessible names
- responsive layouts work with zoom and larger text
- information remains understandable to screen reader users

---

# Implementation expectations

First inspect the existing implementation and underlying domain/state model.

Reuse existing components where they are appropriate.

Do not change business logic merely to make the UI easier to implement.

Do not hardcode the demo values as presentation logic if the page is already driven from case data.

Refactor components if the current structure makes the hierarchy difficult to express.

Prefer small, composable components where useful, but avoid unnecessary abstraction.

Preserve the existing visual language and design system unless a component is actively hurting the UX.

---

# Acceptance criteria

The redesign should satisfy all of the following:

- The primary case state can be understood within a few seconds.
- The most important issue is immediately visible.
- The recommended next action is immediately understandable.
- Redundant explanatory text has been removed.
- Assessment counts no longer dominate the page.
- Supported and unassessed counts remain available.
- Unknown/unassessed requirements are not presented as confidently assessed.
- Users can navigate from an issue to its requirement detail.
- Metadata remains visible but secondary.
- The Requirements section appears materially sooner in the page hierarchy.
- Status is not communicated by colour alone.
- The design works responsively.
- Existing assessment/business logic continues to work.
- The result feels calm, deliberate and production-quality rather than dashboard-heavy.

> **Added in review — criteria that make the amendments checkable.**
>
> - Every count and label on the page agrees with the API payload that produced it. In
>   particular the attention count equals `needs_attention`; it is not recomputed or
>   re-bucketed in the client.
> - No sentence characterising an assessment is composed in the frontend. Assessment copy
>   comes from `messages.py` via `summary.text` / action `text`.
> - Conclusion and currency remain two signals wherever a result is shown, including in
>   any new action treatment.
> - No fraction, percentage or ratio appears in the rendered output. The existing regex
>   assertions in `CaseOverviewPanel.test.tsx` and `RequirementsList.test.tsx` still pass.
> - The stale, updating, nothing-assessed, no-actions and summary-unavailable states each
>   render correctly and are covered by a test.
> - `RequirementsList` precedes `ResidencePanel` in the page order.
> - The full suite stays green: `just lint`, `just typecheck`, `just test`, and the
>   Playwright suite.

Before implementing, inspect the relevant files and briefly explain:

1. the current component structure,
2. which components you intend to change,
3. the proposed information hierarchy,
4. any UX/domain assumptions you need to make.

Then implement the redesign.