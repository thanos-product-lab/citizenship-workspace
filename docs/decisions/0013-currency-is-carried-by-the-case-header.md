# ADR-0013: Case-level currency is carried by the header, on every destination

**Status:** Accepted
**Date:** 2026-08-19
**Milestone:** M4 (information-architecture follow-on)

## Context

ADR-0001 established that conclusion and currency are independent axes and must never be
collapsed. ADR-0010 extended currency from a single result to a group. Both are about
*what* is rendered. This is about *where*.

While the case was one page, the question did not arise: the stale banner sat on the
overview panel, and the travel table that produced staleness was a few hundred pixels
below it. Editing a trip and seeing "5 conclusions have not been rechecked" were the same
screen.

ADR-0012 split them. Editing now happens under **Case data**; the readiness summary lives
on **Overview**. Left alone, the stale banner would have stayed with the summary — and the
result is a specific, quiet failure:

> A user opens Case data, corrects a return date, and is shown a page of editable inputs
> with no indication that the conclusions drawn from them are now stale. The notice is on
> a destination they have no reason to revisit.

That is superseded state presented as current, which is what directive §2.4 exists to
prevent, and it is a false reassurance in the sense of §2.7 — the user has just invalidated
their own assessment and the screen is silent about it. The split would have separated
staleness from its own cause.

## Decision

The persistent case header carries **case-level currency**, and the header is on every
destination:

- **Unrechecked conclusions.** "N conclusions have not been rechecked since your inputs
  changed. They are shown as they were reached, marked stale." The sentence never claims
  the conclusion still holds — that is precisely what a stale result cannot tell us.
- **A recalculation in flight.** "Updating — the figures and conclusions shown are from
  before your last change." Stated once, in the header, rather than repeated per
  destination.

**Recalculate lives in the header for the same reason.** It creates a new `AssessmentRun`
and new results for *every* requirement, not only the ones on the destination in view.
Inside the requirements list it read as recalculating that page.

Three supporting rules:

- **Per-destination currency does not disappear.** A requirement row still carries its own
  currency badge, and a group row still carries its stale count. The header says *how many*
  conclusions are unrechecked; the group row says *which part of the case* they are in;
  the requirement badge says *this one*. Three scopes, not three copies.
- **The Overview does not repeat it.** A test asserts `CaseOverviewPanel` renders no stale
  notice, so the claim has one home and cannot drift between two.
- **Case data states the consequence before the controls**, not only after the fact: "The
  facts your case is assessed against. Changing any of them marks the conclusions drawn
  from it stale until you recalculate." That is what makes the header's notice read as the
  result of the user's own edit rather than as a surprise.

## Consequences

- The header reads case state, so it fetches the overview projection. Three components on
  three routes now read one query key (`useCaseOverview`), which is one request and, more
  importantly, one definition of what "the overview" is.
- The recalculation control and its failure message must live together. They did not at
  first: the header owned the button while the requirements list rendered the error, and
  because separate `useMutation` instances do not share state, a failed recalculation
  showed a sighted user nothing at all. Both now sit in the header.
- Any destination added later inherits currency for free. That is the point of putting it
  in the shell rather than on a page — including for destinations nobody has thought of
  yet, which is the failure mode this project keeps rediscovering.

## Alternatives rejected

- **Duplicating the notice onto Case data.** Two renderings of one claim, free to drift,
  and it answers only the destination we happened to think of.
- **Blocking edits while results are stale.** Inverts the model. Editing is how a user
  fixes their case; staleness is the expected consequence, not an error state.
- **Recalculating automatically on edit.** Tempting, and it would remove the stale window
  entirely — but it hides the causal link the product exists to teach, spends compute on
  every keystroke-level change, and would make ADR-0008's blunt invalidation a
  user-visible latency rather than a background fact.
