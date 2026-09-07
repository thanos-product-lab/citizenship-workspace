# ADR-0027: A derived conflict widens the residence invalidation fan-out to four rules

**Status:** Accepted
**Date:** 2026-09-07
**Milestone:** M8 (Evidence and extraction), slice 4

## Context

ADR-0014 replaced blunt invalidation — every residence input change stales all five residence
results — with selective invalidation resolved from declared dependencies. Narrowing is where
the danger is, and `tests/assessments/test_selective_invalidation.py` was written differentially
to guard it.

M8 slice 4 made a confirmed document date able to dispute a trip the document is attached to.
The §6.1 half of that (RULES_SPEC: *"anything else — UNCERTAIN, ESTIMATED, CONFLICTING, DRAFT
— is excluded from trusted totals"*) is applied in `_gather_trips`, which builds the `trips`
tuple passed to `evaluate_residence_requirements`. **Four rules read `TripInput.is_trusted`**:
`travel_consistency`, `total_absences`, `final_year_absences`, `physical_presence_start_date`.

Migration `0034` declared the new `CASE_FACT` dependency on `travel_consistency` alone. Two
tests asserted that this was correct, on reasoning that does not hold:

> Confirming what a booking says does not change how many days the user was absent — what it
> can change is whether a trip is trusted, and that reaches the totals through the trip itself
> when the user resolves the conflict, not through the fact.

The second clause does not follow from the first. Whether a trip is trusted *is* what the
totals read, so a confirmed fact moves the figure at the very next evaluation with no trip
version ever changing. On the canonical demo case, confirming the amended booking's return
date left `residence.total_absences` standing **CURRENT at 439 days** until an unrelated
recalculation moved it to 434 — a current conclusion computed from a date the product was
simultaneously reporting as disputed, breaking *every current trusted assessment references
current relevant input versions* (CLAUDE.md §9).

The same argument applies to `EVIDENCE_SUPPORT`. Before slice 4 an evidence link reached only
`travel_consistency`'s unevidenced detection. Slice 4 made the link the thing that gives a
confirmed date the authority to dispute a trip — `conflicts.detect` returns nothing without one
— so attaching is now what can push a trip out of a trusted total, and detaching is what pulls
it back.

## Decision

**Migration `0035` declares `CASE_FACT` and `EVIDENCE_SUPPORT` on all three absence and presence
rules**, taking each from 1.0.0 to 1.1.0. `residence.qualifying_period` stays out: it reads the
application date and nothing else, so no fact or link can reach it, and it remains the rule that
proves this is still selective invalidation rather than the blunt residence sweep.

**The cost the old wording was protecting is real and accepted.** Confirming any of a booking's
six fields now restales the residence group, and so does every attach and detach. Over-firing
leaves a true statement on screen — *these conclusions have not been rechecked* — while
under-firing left a false one.

## Alternatives considered

**Narrow the match on `input_key`, so only `travel.departure_date` and `travel.return_date`
restale the totals.** This would cut the fan-out from six fields per booking to two.
`resolve_affected_requirements` documents why matching is on input *kind* only: narrowing on a
key is sound only for an input versioned *per key*, and a `RouteProfileVersion` is a whole-row
snapshot, so narrowing there would leave a CURRENT result linking a superseded version id.

A `CaseFact` **is** versioned per key, which is exactly the condition that docstring names for
revisiting the decision. It is deliberately not revisited here: the change would touch every
input kind's resolution path to buy noise reduction in one of them, and it belongs in its own
slice with its own tests rather than riding along with a correctness fix.

**Leave the declarations and rely on the user recalculating.** Rejected. The staleness marker is
the product's only way of saying a conclusion is out of date, and a figure that is quietly wrong
until an unrelated action refreshes it is the false reassurance directive 7 exists to prevent.

## Consequences

- Four residence results go `STALE` on any claim confirmation, attach, detach, or document
  deletion. `qualifying_period` does not.
- `residence.total_absences` and `residence.final_year_absences` now write `CASE_FACT_VERSION`
  and `EVIDENCE_LINK` input links, so a result whose figure a document moved says which document
  and which fact (directive 5). On a twelve-trip case that is twelve evidence links per result.
- The regression is pinned by `test_every_result_the_conflict_moves_was_staled_first`, written
  as *what changed must have been staled* rather than as a list of requirement keys — a list is
  what was one short.

## Note on how this was found

The suite was green, because two of its tests asserted the defect. It was found by driving the
canonical demo case in Chrome and reading the total-absences page, which was also printing four
false sentences about its own inputs — see `docs/demo-assets/README.md` §M8 slice 4.
