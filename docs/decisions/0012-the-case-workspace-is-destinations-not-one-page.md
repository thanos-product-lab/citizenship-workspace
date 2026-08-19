# ADR-0012: The case workspace is separate destinations, not one page

**Status:** Accepted
**Date:** 2026-08-19
**Milestone:** M4 (information-architecture follow-on)

## Context

Through M3A and M4 the case rendered as one route, `/cases/{caseId}`, stacking four
independent panels: the readiness summary, all fifteen requirements with a sentence each,
the proposed application date, a twelve-row travel table with CSV import, and the delete
control. The page asked the reader to move between several unrelated mental modes —
reading an assessment, then editing the data behind it, then administering the case —
without ever changing context, and it put a data-entry table between the reader and the
requirements they had come for.

Two structural problems followed from it:

- `/cases/{id}/requirements/{key}` existed as a detail page while its parent segment
  `/cases/{id}/requirements` was not a page at all. The URL hierarchy claimed a structure
  the app did not have.
- Nothing was linkable below the case. A user could not send, bookmark or return to "the
  residence requirements" or "my travel history".

UI/UX §4 specifies the eventual information architecture: six areas — Overview, Timeline,
Requirements, Evidence, Issues, Preparation — in a persistent left sidebar. Four of those
six do not exist. Timeline is M5, Issues M6, Evidence M7, Preparation later still.

## Decision

The case is a **workspace of destinations**, each a real route with its own URL, document
title and history entry:

```
/cases/{caseId}              Overview      — readiness, blockers, groups
/cases/{caseId}/requirements Requirements  — the full assessment model
/cases/{caseId}/data         Case data     — the editable facts, and deletion
```

Mounted from a Next route **layout**, so the case header and navigation persist across a
move rather than remounting — a remount resets scroll and drops keyboard focus to `<body>`
on every navigation.

**Three destinations now, six later.** The navigation is built from a list
(`features/case-workspace/destinations.ts`), so each of UI/UX §4's remaining areas is one
entry when its milestone lands. This is a deliberate, temporary divergence from §4 on two
points, both revisited when the areas exist:

- **Horizontal local navigation, not a sidebar.** Three destinations do not justify
  surrendering the horizontal space a sidebar costs. Reassess at M7, when Evidence and
  Issues make it five or six.
- **Evidence is not a destination yet.** There is no `evidence` module in
  `services/platform/app/`. A primary destination leading to an empty room is a promise
  the product cannot keep, and CLAUDE.md §10 makes the default answer to scope expansion
  *no*. Until M7 the evidence-first claim is carried where it is true: the "Evidence used"
  layer on a requirement detail, which states plainly that no documents are linked and
  every figure rests on dates the user typed.

**Navigation is links, never ARIA tabs.** `role="tab"` / `tablist` promises interchangeable
panels within one document and suppresses the link semantics that make bookmarking,
open-in-new-tab and back/forward work. A `<nav>` of links with `aria-current="page"` is the
correct native construct, and it is what makes the destinations genuinely deep-linkable.

**Sub-pages mark their parent current.** A requirement detail is within Requirements, so
the navigation marks Requirements current while it is open — a nav highlighting nothing
would tell a screen-reader user they had left the workspace.

**Deletion leaves the primary journey.** It sits at the foot of Case data, behind an
in-page confirm. The exception is a `DRAFT` case, which has no destinations at all: during
route onboarding, abandoning the case is the only case-level action available, so the
control stays beside the onboarding form.

## Consequences

- Editing moved to Case data, which is what makes ADR-0013 necessary: the destination
  where staleness is *caused* is no longer the destination that was reporting it.
- Each destination is a separate render, so any state shared between them belongs in the
  query cache rather than a common parent — there no longer is one. `useCaseOverview`
  exists for that reason: three readers on three routes, one query key, one request.
- The Playwright walkthrough asserts a single-page journey and had to be rewritten. It is
  `skip`ped for want of test credentials, so it did not fail loudly; the auth-boundary
  tests were extended to cover both new routes because a new route tree is a new chance to
  fall outside the middleware matcher.
- UI/UX §4 now carries an amendment recording this divergence and its expiry.

## Alternatives rejected

- **Client-side tab panels.** Cheapest to build, and it forfeits every property that made
  the split worth doing: no URLs, no history, no bookmarking, no deep links, and a lie
  told to assistive technology about what the controls are.
- **Keeping one page and collapsing sections.** Progressive disclosure inside one route
  still leaves everything in one document, one scroll position and one URL. It reduces
  visible height without reducing the number of mental modes the reader is asked to hold.
- **Building all six areas as empty destinations now.** Honest about the target, dishonest
  about the product: four of six would be placeholders, and a workspace of placeholders
  reads as a product that is broken rather than one that is unfinished.
