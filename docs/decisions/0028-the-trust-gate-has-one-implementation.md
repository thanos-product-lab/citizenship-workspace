# ADR-0028: The §6.1 trust gate has one implementation, and read models consume it

**Status:** Accepted
**Date:** 2026-09-08
**Milestone:** M8 (Evidence and extraction), after slice 4

## Context

RULES_SPEC §6.1 decides whether a travel record enters a **trusted total**. Until M8 the
predicate was small and total — ACTIVE + CONFIRMED + EXACT — so `counts_toward_trusted_total`
could be called anywhere against a stored row and every caller agreed by construction. Two
callers did exactly that: `assessments.service._gather_trips` and `residence.timeline`.

M8 slice 4 added a second way to fail the gate. A confirmed `FactVersion` on a document the
user attached to a trip can disagree with that trip's dates, and the disputed trip is excluded
— **derived at assessment time, never stored** (EVIDENCE_AND_CLAIM_LIFECYCLE_RFC §42). The
overlay was applied in `_gather_trips` only. The stored row still reads CONFIRMED with EXACT
dates, so the timeline kept counting a trip the assessment was holding back:

```
assessment residence.total_absences: days=0  provisional=29
timeline   qualifying_period_days: 29, held back: 0
```

One question, two answers, and the reassuring one on the more prominent surface — the failure
directive 7 exists to prevent.

**ADR-0027 could not have prevented this, and neither could migration `0035`.** Both reason
about rules: which requirements declare which dependencies, so a changed input restales the
right results. A projection declares nothing and produces no results. It is a reader of the
gate that the rule catalog cannot see, so no amount of dependency completeness reaches it.

## Decision

**`gather_trips` is public, and it is the only place the §6.1 gate is decided.** Anything
needing to know whether a record counts consumes its `TripInput`s rather than re-deriving
trust from the row. `residence.timeline` now does.

**The client is no longer allowed to decide either.** `apps/web/features/timeline/
TravelHistory.tsx` computed `review_state === "CONFIRMED" && date_confidence === "EXACT"` in
TypeScript, from a response that serves the **stored** version — so on the Case data page a
disputed trip read as plain "Confirmed", on the page where the user had just attached the
document. `TravelRecordResponse` now carries `is_trusted` and `is_disputed_by_document`, and
`TravelRecordOutcome.of` computes them on every path that builds one, so a new response route
cannot publish the ingredients alone.

`date_confidence` and `review_state` are still published, deliberately: they are the values
the *user* entered, and the edit form offers them back. Overwriting `date_confidence` with the
derived `CONFLICTING` would put a state in that form which nobody chose. The stored fields
stay honest about the past; the two new fields answer the question.

`counts_toward_trusted_total` stays where it is and keeps its name — it is the *predicate*,
and `gather_trips` is the only correct way to apply it, because only `gather_trips` also
carries the conflict overlay.

Two consequences follow for the API, and both are corrections rather than additions:

- `unconfirmed_trip_count` → `held_back_trip_count` + `conflicted_trip_count`, and
  `*_including_unconfirmed` → `*_including_all_records`. A disputed record is *confirmed*, so
  every one of those names described half of what its figure contained.
- `presence_anchor_is_absent_including_all_records` joins the existing flag. The view turns
  the boolean into "you were in the UK on this day" — a claim about where the user was — and
  one flag would let it make that claim on the strength of a record being held back. The
  presence rule already has three answers here; the projection needed two flags to reach them.

This also closes an RFC divergence. Domain §44.3 lists `conflicts` among `TimelineProjection`'s
elements; the slice-4 plan recorded "the timeline will not show a conflict" as an accepted gap.
Under CLAUDE.md §12 the RFC wins, so the gap is closed rather than documented.

## Alternatives considered

**Have the timeline call `detect_case_conflicts` and apply the overlay itself.** Rejected: it
reuses the *detection* while keeping two implementations of the *gate*, which is the thing
that diverged. The second copy would be correct on the day it was written and free to drift
after.

**Move trip-gathering into `residence`, so the module owning travel records owns the gate.**
Rejected: conflict detection reads facts and evidence links, so `residence` would grow
dependencies on both. `assessments` already joins those three contexts and is where
`conflicts.py` lives.

**Drop the trusted total from the timeline and point at the assessment for it.** Rejected:
the timeline's value is the live picture after an edit, which is exactly when it differs from
the last assessment. Removing the figure would remove the reason the surface exists.

## Consequences

- `residence.timeline` imports `assessments.service`. `timeline.py` already imported
  `assessments.repository`, so the direction is not new; `assessments.service` imports
  `residence.domain`/`residence.repository` and never `residence.timeline`, so there is no cycle.
- `get_timeline` now runs conflict detection — two extra queries on a read path — rather than
  reading travel records alone. Accepted: correctness on the figure the surface exists to show.
- `tests/residence/test_timeline_matches_assessment.py` asserts the two surfaces against
  **each other**. `test_timeline.py`'s hand-transcribed oracle values from
  `SYNTHETIC_DEMO_CASE.md` stay, and stay right, but a hand-transcribed number cannot notice
  that a different surface disagrees with it — which is why the divergence shipped green.

## The general shape

Three times the same defect: a value that used to be derivable from a stored row stopped being
derivable, and a reader that still derived it kept answering with yesterday's rule. Slice 4
found it in three rules; this found it in a projection; the review of this change found it in
a React component. When a predicate acquires a second input, **every place that computes it
must be enumerated** — and the rule catalog is not that list, because not every reader is a
rule, and not every reader is even in the same language.

The pattern each time was a caller reading the *ingredients* (`review_state`,
`date_confidence`) instead of the *decision*. The lasting fix is not vigilance, it is to stop
publishing ingredients where a decision will do — which is why the fix here is a field on the
response and a factory that fills it, rather than a corrected expression in one component.
Three readers were found by three different means: a mutation table, a browser walkthrough,
and a reviewer. None was found by the type system, because every one of them type-checked.
