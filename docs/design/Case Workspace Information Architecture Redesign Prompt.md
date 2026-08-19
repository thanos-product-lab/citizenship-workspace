> **Review status.** The diagnosis in this brief is accepted: the case page renders the
> overview, all fifteen requirements, the travel table, CSV import and Delete case in one
> scroll, and that is too much. The proposed route structure is accepted. The blocks
> marked **Amendment** below are corrections where a prescription would break a prime
> directive or pull in work from a later milestone. They are annotations on the original,
> not replacements — the surrounding text is unchanged. Anything not marked is accepted
> as written.
>
> Two amendments are load-bearing and worth reading before the rest: **no fractions**
> (a `4 / 5` is a readiness score, CLAUDE.md §2.6) and **Evidence is M7** (there is no
> evidence module in the backend yet).
>
> This is a frontend and routing change. It needs no backend work: `/overview` already
> returns group summaries and `/requirements` already returns the list.

You are working on the **Evidence-First Citizenship Workspace**, an AI-native product that helps UK citizenship applicants understand whether they are ready to apply, what evidence supports their eligibility, what remains uncertain, and what actions they should take next.

We need to redesign the **Case workspace information architecture**.

The current implementation places almost everything on one long scrollable page:

- case status
- application metadata
- readiness summary
- issues requiring attention
- all citizenship requirements
- detailed requirement explanations
- residence data
- proposed application date
- travel history
- travel editing
- CSV import
- destructive case actions

This makes the experience feel overwhelming and forces users to move between several different mental modes on the same page.

The goal is to turn the case from a **single long page containing everything** into a focused, high-quality **workspace**.

---

# Product principles

Use these principles throughout the redesign:

- Outcome-oriented
- Readiness first
- Clarity over complexity
- Trust over engagement
- Guidance over pressure
- Accessibility by default
- Evidence before confidence
- Progressive disclosure
- Strong information hierarchy
- Responsive by design
- Calm, premium, professional UI

The experience should take inspiration from the clarity of **GOV.UK**, the workspace organisation and restraint of **Linear**, and the way **Stripe** handles complex status and requirements.

Do not copy any of those products directly.

This should still feel like its own product.

---

# Core problem

The existing Case Overview is not really an overview.

It currently combines several different product surfaces:

1. understanding the overall case state
2. reviewing eligibility requirements
3. inspecting detailed assessment reasoning
4. managing evidence
5. editing underlying case data
6. maintaining travel history
7. importing data
8. case administration

These responsibilities should not all exist in one continuous page.

The user should not need to scroll through the entire assessment before editing travel history or managing evidence.

Likewise, the overview should not contain every piece of underlying case data.

---

# Product direction

Treat the case as a **workspace**, not a dashboard.

The workspace should help users:

- understand their current readiness
- see what requires attention
- know what to do next
- inspect individual requirements
- understand supporting evidence
- correct or add underlying data

Do not optimise for showing the maximum amount of information at once.

Optimise for helping the user understand and act.

---

# Proposed workspace navigation

Introduce persistent local navigation for a case with four primary destinations:

**Overview | Requirements | Evidence | Case data**

> **Amendment — build three destinations, not four. Evidence is M7.**
>
> There is no `evidence` module in `services/platform/app/` at all. The roadmap
> (`docs/IMPLEMENTATION_ROADMAP.md` §build order) puts **Evidence Foundation at M7**,
> after M6 (issues) and M5 (timeline and date simulation). We are finishing M4.
>
> A primary navigation destination that leads to an empty room is a promise the product
> cannot keep, and CLAUDE.md §10 makes the default answer to scope expansion *no*. This
> brief also argues against itself here: §3 says "do not build speculative functionality
> that does not exist yet", then makes Evidence one of four top-level destinations.
>
> Ship:
>
> **Overview | Requirements | Case data**
>
> Build the navigation from a data-driven list of destinations so that M7 adds one entry
> and changes nothing else. The evidence-first thesis is carried today by the provenance
> already on the requirement detail page — the "Evidence used" layer that states plainly
> that no documents are linked and every figure rests on dates the user typed. That
> honest gap does more for the thesis than an empty tab would.

These should behave as **real navigational destinations/routes**, not client-side tab panels.

Example route structure:

```text
/cases/:caseId
/cases/:caseId/requirements
/cases/:caseId/evidence
/cases/:caseId/data
```

Use semantic navigation such as:

```html
<nav aria-label="Case navigation">
  ...
</nav>
```

Use links and `aria-current="page"` for the active destination.

Do **not** implement this using `role="tab"` / `tablist`.

These are separate destinations, not interchangeable tab panels.

The navigation should therefore support:

- browser history
- bookmarking
- deep linking
- open in new tab
- expected keyboard navigation
- screen-reader navigation
- graceful progressive enhancement

---

# Persistent case header

Keep the case identity visible and consistent across the workspace.

For example:

```text
← Your cases

Amara Okonkwo — demo                Needs attention

15 Apr 2027 · Standard five-year route

Overview   Requirements   Evidence   Case data
```

The header should remain compact.

Do not repeat the full readiness summary on every destination.

Only expose the minimum case context necessary to orient the user.

---

# 1. Overview

The Overview should become a **true summary**, not the entire product.

It should answer three questions quickly:

1. What is the state of my case?
2. What needs my attention?
3. What should I do next?

Target a page that is approximately one desktop viewport plus a small amount of scrolling for a typical case.

A conceptual structure:

```text
1 requirement needs your attention

1 near threshold · 7 supported · 6 not assessed

NEEDS YOUR ATTENTION

Presence on the first day                   Blocking

Consider applying from 25 April 2027

Review requirement →

ASSESSMENT

Identity & status                4 / 4 supported
Residence                        Needs attention
Knowledge & language             0 / 2 assessed
Referees                         0 / 2 assessed
Character & declarations         0 / 1 assessed

View all requirements →
```

> **Amendment — `4 / 4` and `0 / 2` are readiness scores. Remove every fraction.**
>
> **This breaks a prime directive.** CLAUDE.md §2.6 ("No overall readiness score /
> percentage — ever") and §10, MVP scope §8.7 ("No readiness percentage is displayed"),
> and UI/UX §3.6 all forbid it. A fraction is arguably worse than a percentage here
> because it does not look like a score — it reads as a fact.
>
> There is also a specific domain error in `Residence  4 / 5` (used in §2's mockup).
> The fifth requirement is `NOT_CURRENTLY_SATISFIED` — a reached, failed conclusion. A
> fraction renders it as *missing*, as though finding a fifth thing would complete the
> set. It silently converts a failure into an incomplete. `0 / 2 assessed` is the same
> defect pointed the other way: it invites the reader to perform the division.
>
> UI/UX §6.2 gives the sanctioned form — counts, no denominator:
>
> ```text
> 8 requirements are supported
> 2 need more information
> ```
>
> So a group row carries either a **state** or **bare counts**, never `n / m`:
>
> ```text
> ASSESSMENT
>
> Identity and status              All 4 supported
> Residence                        Needs attention
> Knowledge and language           Not assessed
> Referees                         Not assessed
> Character and declarations       Not assessed
>
> View all requirements →
> ```
>
> This applies everywhere in this brief: the `4 / 4` and `4 / 5` in §2's requirements
> mockup go too. The overview implemented in `CaseOverviewPanel.tsx` already follows the
> counts-without-denominators rule; do not regress it.

The Overview should **not** contain:

- every detailed requirement explanation
- full travel history
- evidence management
- CSV import
- editable residence data
- destructive case controls

The Overview should orchestrate the journey rather than contain the whole application.

---

# Desktop overview layout

At larger desktop widths, consider a restrained two-column layout.

For example:

**Main column**
- readiness
- blockers
- recommended actions

**Secondary column**
- assessment progress
- lightweight case summary

A rough balance of around 65/35 may work, but do not treat this as a fixed requirement.

Important:

The secondary column must never contain information that is required to understand content in the main column.

This ensures the content can safely collapse into a single logical sequence on smaller screens.

The DOM order should remain meaningful when linearised.

> **Amendment — skip the second column for now.**
>
> This brief hedges on it ("consider", "may work", "do not treat this as a fixed
> requirement"), and the hedge is right. After the overview redesign the page is already
> about one desktop viewport. Introducing a secondary column re-creates the
> dashboard feel that the visual-design section warns against three sections later, and
> it buys space we do not currently need.
>
> Revisit when the overview genuinely outgrows a viewport — most likely at M6, when open
> issues arrive and actually need somewhere to live.

---

# 2. Requirements

Move the complete eligibility/readiness model into its own destination.

This should be the primary assessment workspace.

Requirements should be grouped by domain, for example:

- Identity and status
- Residence
- Knowledge and language
- Referees
- Character and declarations
- Application preparation

Avoid rendering the full explanation for every requirement by default.

Prefer a compact, highly scannable list:

```text
Requirements

1 needs attention · 1 near threshold · 7 supported · 6 not assessed

All   Needs attention   Not assessed

IDENTITY & STATUS                              4 / 4

Adult applicant                            Supported
Settled status                             Supported
Standard five-year route                   Supported
Settled-status holding period              Supported

RESIDENCE                                     4 / 5

Presence on the first day        Needs attention   →
Total absences                   Near threshold    →
Final-year absences              Supported         →
Travel record consistency        Supported         →

KNOWLEDGE & LANGUAGE                           0 / 2

Life in the UK test                 Not assessed    →
English language                    Not assessed    →
```

Each row should clearly communicate:

- requirement name
- current assessment state
- whether further action is available

Do not show long explanations inside every row.

Use progressive disclosure.

> **Amendment — keep the one-line summary in each row.**
>
> The mockup above shows name + state only. That is a downgrade in trust terms. The
> sentence currently on each row is the deterministic message rendered from
> `app/requirements/messages.py` — "439 days outside the UK across your five-year
> qualifying period, from confirmed travel records, against a threshold of 450" — and it
> is the difference between a list of *statuses* and a list of *reasons*. Stripping it
> leaves a wall of badges, which is precisely the "excessive badges" this brief warns
> against under visual design.
>
> "Do not show long explanations inside every row" is accepted and already honoured: the
> row shows one sentence, not the explanation stack. The list gets short enough simply by
> no longer sharing a page with the travel table and CSV import.
>
> **Amendment — defer the filter chips.**
>
> `All | Needs attention | Not assessed` solves a problem we do not have at fifteen
> requirements across six groups, and it adds URL state (`?status=attention`) to design,
> test and keep in sync with the grouping. Ship the grouped list first. Add filters when
> the list is long enough to need them — and note that "Needs attention" would need a
> definition that matches `_NEEDS_ATTENTION_FROM` in `app/assessments/groups.py`, not a
> new frontend one.

---

# Requirement detail pages

Selecting a requirement should open a focused requirement detail experience.

Example:

```text
/cases/:caseId/requirements/:requirementId
```

This is where detailed information belongs:

- assessment conclusion
- rule being applied
- evidence used
- relevant facts
- calculations
- dates
- uncertainty
- source references
- reasoning
- recommendation
- actions the user can take

For example, **Presence on the first day** should have space to explain why it failed and how the recommended date was derived without forcing every Requirements user to read that reasoning.

The Requirements list should communicate state.

The requirement detail should explain why.

---

# 3. Evidence

Evidence should become a first-class destination.

Evidence is one of the core differentiators of this product and should not feel like an implementation detail underneath requirements.

The Evidence workspace should eventually help answer:

- What evidence have I provided?
- What requirements does each item support?
- What evidence is missing?
- What evidence requires review?
- What information has AI extracted?
- What extraction is uncertain?
- Has evidence become stale or contradictory?

Potential future structure:

```text
Evidence

12 evidence items

9 supporting requirements
2 need review
1 processing

Passport
Settled status
Travel records
Life in the UK certificate
English language evidence
Referee 1
Referee 2
...
```

Do not build speculative functionality that does not exist yet.

However, structure the destination so that these concepts can evolve naturally.

> **Amendment — keep this section as the M7 brief, and build none of it now.**
>
> Everything in this section is the right target and none of it is buildable: there is no
> evidence module, no `FactEvidenceLink`, and no extraction pipeline until M8. See the
> amendment under *Proposed workspace navigation* — ship three destinations and add this
> one at M7.
>
> The bidirectional navigation described here (requirement → evidence, evidence →
> requirement) is the part worth protecting architecturally. The requirement detail page
> already renders an "Evidence used" layer stating that nothing is linked; that layer is
> the future entry point, so leave it in place rather than removing it as dead weight.

There should eventually be bidirectional navigation:

**Requirement → supporting evidence**

and

**Evidence → supported requirements**

This relationship is fundamental to the evidence-first product model.

---

# 4. Case data

Move editable facts into a dedicated **Case data** destination.

This separates:

**What does my case mean?**

from:

**What facts does the system know about me?**

Potential structure:

```text
Case data

Application
  Proposed application date
  Route

Immigration status
  Status type
  Settled-status date

Travel history
  12 recorded trips                       Manage →

Personal details
  ...

Case settings
  ...
```

Use clear sections rather than one continuous form where possible.

> **Amendment — decide where the proposed application date lives before M5.**
>
> Case data owning the proposed application date is right for M4. But that date is also
> the input to **M5's date simulation**, which is a reasoning surface, not a data-entry
> one: the user moves the date to see what the qualifying period and absence totals would
> become. That is provisional output and must be labelled as such — it is never current
> (CLAUDE.md §7, "Trusted vs Provisional").
>
> So the date has two homes, and they are not the same job:
>
> - **editing** the committed date — Case data, now;
> - **simulating** an alternative date — a reasoning surface, M5.
>
> Do not build the simulator here. Just do not design Case data in a way that assumes it
> owns the only date control, or M5 will have to unpick it.

---

# Travel history

Travel history should no longer be displayed as a large table at the bottom of the Case Overview.

Give it a focused destination or sub-page such as:

```text
/cases/:caseId/data/travel
```

This page should own:

- recorded trips
- adding a trip
- editing a trip
- removing a trip
- importing travel records
- reviewing imported records

CSV import belongs here.

Do not place import controls on the main case overview.

For desktop, a table may remain appropriate.

For mobile, do not simply squeeze the desktop table horizontally.

Use a compact responsive record pattern if necessary:

```text
Spain

14 Apr 2022 → 26 Apr 2022

Edit
```

The experience must remain usable at narrow widths and with text zoom.

---

# Destructive actions

`Delete case` should not appear at the bottom of the main user journey.

Move destructive actions into an appropriate case settings / danger zone area.

Separate them visually and conceptually from readiness and assessment work.

Use clear confirmation patterns.

Do not allow a destructive action to be triggered accidentally.

---

# Navigation behaviour

Use horizontal local navigation initially:

**Overview | Requirements | Evidence | Case data**

Do not introduce a persistent left sidebar unless the workspace grows enough to justify it.

There are currently too few destinations to warrant sacrificing significant horizontal space.

The local navigation should remain visually connected to the current case.

---

# Responsive behaviour

The redesign must be responsive by architecture, not patched afterward.

## Desktop

Use available space to improve information hierarchy and reduce unnecessary vertical scrolling.

Two-column layouts may be used where they materially improve readability.

Do not create dashboard-style grids simply because space is available.

## Tablet

Allow layouts to collapse naturally.

Avoid awkward intermediate states where cards or tables become compressed.

## Mobile

The main workspace should become a clear single-column flow.

Do not hide important case navigation unnecessarily behind a hamburger.

For four navigation destinations, test options such as:

- compact horizontal navigation
- wrapping to two rows
- accessible horizontally scrollable navigation

Choose the option that gives the strongest usability after testing.

Avoid tiny controls.

Avoid horizontal tables where a record-list representation is more appropriate.

Ensure interactions remain usable at 200% zoom and with larger text settings.

---

# Accessibility

Maintain a very high accessibility standard.

Ensure:

- semantic landmarks
- correct heading hierarchy
- real links for navigation
- `aria-current="page"` for active workspace navigation
- keyboard accessibility
- visible focus indicators
- meaningful DOM order
- no status conveyed using colour alone
- sufficient contrast
- touch targets are appropriately sized
- layouts survive text zoom
- responsive reordering does not change semantic meaning
- screen-reader users can understand the current case, destination and requirement states

Do not use ARIA when native HTML semantics already provide the correct behaviour.

---

# Progressive disclosure

This is a core design principle for the redesign.

Use this hierarchy:

```text
Case
    ↓
Workspace domain
    ↓
Object
    ↓
Detail
```

For example:

```text
Amara's case
    ↓
Requirements
    ↓
Presence on the first day
    ↓
Assessment reasoning + evidence
```

Or:

```text
Amara's case
    ↓
Case data
    ↓
Travel history
    ↓
Individual trip
```

Avoid the current pattern:

```text
Case
    ↓
Everything
```

---

# Visual design principles

Do not turn the workspace into a conventional analytics dashboard.

Avoid:

- excessive cards
- card-inside-card layouts
- large grids of metrics
- decorative charts
- unnecessary icons
- excessive badges
- multiple competing status colours
- overly dense enterprise UI

Prefer:

- strong typography
- clear hierarchy
- simple separators
- restrained surfaces
- deliberate whitespace
- scannable rows
- concise labels
- calm status indicators
- progressive disclosure

The product should feel trustworthy, thoughtful and unusually easy to understand.

---

# State and URL preservation

Where useful, preserve navigation state in URLs.

Examples could include:

```text
/requirements?status=attention
/data/travel
```

Do not make essential navigation dependent solely on ephemeral client state.

Deep linking should be possible.

Back/forward browser behaviour should work naturally.

---

# Existing domain logic

Before changing the interface:

1. inspect the current case page
2. inspect its data-loading architecture
3. inspect how requirements and assessment states are represented
4. inspect the travel data model
5. inspect existing evidence-related models/components
6. identify which current components can be reused

Do not modify assessment/business logic merely to simplify the UI.

Do not duplicate assessment state across pages.

All destinations for the same case should derive from the same underlying case and assessment data.

---

# Implementation approach

Do not attempt to rewrite the entire product in one monolithic component.

Create clear layout primitives where appropriate, for example:

- `CaseWorkspaceLayout`
- `CaseHeader`
- `CaseNavigation`
- `AssessmentSummary`
- `RequirementGroup`
- `RequirementRow`

These names are examples, not mandatory API requirements.

Reuse the existing design system and components where they remain appropriate.

Avoid abstractions that only have one trivial use.

Keep routing, domain state and presentation responsibilities cleanly separated.

---

# Gaps this brief does not cover

> **Amendment — three unanswered questions, added during review.** Each one is a decision
> the split forces, and each has a wrong answer that would damage the trust model.

## Where does Recalculate live?

Recalculate currently sits in the requirements section of the single page. It is a
**case-level** action: it creates a new `AssessmentRun` and new results for every
requirement, not just the ones on screen. Once Requirements is its own route, leaving the
control there implies it recalculates only that destination.

Put it in the persistent case header, alongside the case identity. It affects every
destination, so it belongs to the case, not to a page.

## Does the stale banner follow the user across destinations?

**Yes, and this is the most important consequence of the split.**

Staleness is caused by editing an input — which, after this redesign, happens under
**Case data**. If the banner lives only on the Overview, the user edits a trip on one
destination and the notice that their conclusions are now stale appears on a different
one they may not return to. The split would then separate staleness from its own cause.

The case-level stale state must be visible on every destination — most importantly on
Case data, where the edit happens. Directive §2.4 (conclusion and currency never
collapsed) and §2.7 (visible uncertainty over false reassurance) both bear on this: a
destination that shows editable inputs while silently omitting that the conclusions
drawn from them are stale is presenting superseded state as current.

The header already carries case identity. It should carry currency too.

## What does the navigation do before the route is confirmed?

A case whose route profile is unconfirmed renders `RouteOnboarding` instead of the
workspace — there are no assessments, no requirements, and no travel history to manage.
Showing three destinations then would offer two empty rooms and undercut the single
question onboarding is asking.

Render no case navigation until the route is confirmed. The nav appears when the
workspace does.

---

# Acceptance criteria

The redesign is successful when:

- The Case Overview is genuinely an overview.
- Users no longer need to scroll through the full requirements list to reach case data.
- Full assessment details live under Requirements.
- Detailed requirement reasoning is progressively disclosed.
- Evidence has a first-class workspace destination.

> **Amendment — three criteria to change, matching the amendments above.**
>
> - **Remove** "Evidence has a first-class workspace destination" from the M4 criteria.
>   It is the M7 criterion. Replace with: *the navigation is built from a list of
>   destinations, so adding Evidence at M7 requires no structural change.*
> - **Add**: *no fraction, ratio, percentage or `n of m` framing appears on any
>   destination.* This is the criterion that protects §2.6 through the redesign, and it
>   should be checked by a test, not by eye.
> - **Add**: *the case-level stale state is visible from every destination, including
>   Case data.*
- Editable underlying facts are separated from assessment results.
- Travel history has a focused management experience.
- CSV import is moved with travel-history management.
- Destructive case actions are removed from the primary journey.
- Case navigation uses semantic links rather than ARIA tabs.
- Navigation is bookmarkable and works with browser history.
- The workspace works well on desktop, tablet and mobile.
- Keyboard and screen-reader navigation remain strong.
- Status does not rely on colour alone.
- The DOM remains logically ordered when layouts collapse.
- The experience remains calm rather than becoming dashboard-heavy.
- Existing assessment and domain logic continues to work.
- Deep links to important destinations are possible.
- The architecture can support future growth without returning to one giant case page.

---

# Before implementation

Before writing code, inspect the relevant files and provide a concise implementation plan covering:

1. the current page/component structure
2. existing routing
3. data dependencies
4. reusable components
5. components/pages that should be extracted
6. proposed route structure
7. proposed responsive behaviour
8. accessibility considerations
9. any domain assumptions or risks

Do not start by changing visual styling.

> **Amendment — the plan should also state the slice order and what stays green.**
>
> Per `.claude/skills/vertical-slice`, each step must leave `main` green and be shippable
> on its own. A safe order, given the routes already in place:
>
> 1. **Extract the layout.** `CaseWorkspaceLayout` + `CaseHeader` + `CaseNavigation`,
>    with the existing page rendered inside it unchanged. Nothing moves yet; the header
>    and nav appear. Green.
> 2. **`/requirements` becomes a real page.** Move `RequirementsList` there. The URL
>    hierarchy stops lying — `/cases/:id/requirements/:key` finally has a parent.
> 3. **`/data` becomes a real page.** Move `ResidencePanel` (application date, travel
>    table, CSV import) and `DeleteCaseControl` there.
> 4. **Overview becomes a summary.** Group rows linking to `/requirements`, per the
>    amended no-fraction form.
>
> Note that steps 2 and 3 make the Overview shorter without changing a single component's
> internals — the current page is already composed of four independent panels
> (`CaseOverviewPanel`, `RequirementsList`, `ResidencePanel`, `DeleteCaseControl`). Most
> of this redesign is moving mount points, which is why it needs no backend change.
>
> The existing Playwright walkthrough asserts a single-page journey and will need
> updating with the routes. It is currently `skip`ped for want of an authenticated
> storage state, so it will not fail loudly — check it by hand.

First restructure the experience around the new workspace information architecture.

Then implement the redesign incrementally, preserving existing functionality throughout.