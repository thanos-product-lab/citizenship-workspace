# ADR-0032: An application date that has passed

**Status:** **Accepted**, 22 September 2026. Both parts implemented. Part 2 was **redesigned
before building** — the shape this ADR originally proposed, and which entry 11 had recorded,
turned out to be the wrong one; the argument is under "Decision, part 2".
**Closes:** `KNOWN_LIMITATIONS.md` entry 11, in full
**Found by:** the September 2026 manual walkthrough (scenario 11). The walkthrough notes
were retired once every finding was closed; the fixes are commits `0c18a65` and `a8e5313`.

## Context

The proposed application date anchors everything in residence: the five-year qualifying
period is measured back from it, the final twelve months are measured back from it, and the
presence anchor is its first day. A date in the past therefore measures a window that has
already closed.

Entry 11 recorded what that produces, and the walkthrough reproduced it exactly. Selecting
15 January 2020 on the scenario-1 case moved the window to 2015–2020, where the case has no
travel at all. `status.holding_period` correctly went `NOT_CURRENTLY_SATISFIED`, because ILR
was granted after that date. **Every other requirement came back SUPPORTED**, including
`residence.total_absences` at zero days.

The result is coherent, deterministic and wrong in the way that matters: a case reading eight
supported requirements and one failure, computed over a window nobody intended. §2.7 names
false reassurance the most important thing to get right.

**There are two defects here and they have different shapes.**

1. A date that was *already past when it was chosen*. Entry 11 claims this is closed — "the
   date field now refuses a past date, so a *new* bad selection cannot be made". It was not.
   The `min` attribute on the date input is the whole enforcement; `POST
   /application-dates/select` accepted 15 January 2020 with a 200. A control that lives only
   in a React component is not a control, and the project knows this: the upload size limit
   is written into the signed policy precisely because the client check "only buys the user
   an early 'no'".

2. A date that was future when chosen and has since *drifted* into the past. This happens to
   every case eventually, including the seeded demo case when April 2027 arrives. Nothing
   re-examines a stored date, so the case keeps reporting conclusions drawn over a closed
   window.

## Decision, part 1: refuse a selection that is already past (implemented)

`residence.service._require_not_already_past` raises `ApplicationDateInPast` (422,
`APPLICATION_DATE_IN_PAST`, carrying `today`) when the date being selected is before today.

**On the command, not the schema.** Entry 11 rejects a `ge=today` constraint on the value,
and that rejection is correct: a type-level rule would refuse to *read back* a case nobody
touched, purely because a calendar boundary went by. Selecting is different — it only ever
happens because somebody chose a date just now, and refusing a choice that is already stale
on arrival costs an untouched case nothing.

**The clock is read in the service.** No evaluator reads a clock, which is what makes a result
reproducible from its recorded input versions. Pushing "is it past?" into `requirements/`
would break that, and is not needed here.

Today is allowed. Applying today is a real intention and the window it measures closes today.

### What this cost, which is worth recording

Three existing tests selected dates that had since aged into the past and began failing. Two
were incidental and were reshaped to move *forward* into a window rather than backward into
one, which also makes them durable.

The third could not be reshaped. `test_a_date_move_that_flips_an_upstream_conclusion_stales_
the_composite` proves the composition closure by flipping `route.adult_applicant` with a date
move, which requires moving the date backwards across the applicant's 18th birthday — and the
applicant must already be 18 for the case to activate at all. So the second date is
necessarily in the past.

That test now pins the clock, with a docstring saying why. The honest reading is that **the
guard makes its scenario unreachable**: after activation, the only input to
`route.standard_section_6_1` that a date can move is the adult check, and only backwards. The
closure is still worth proving; its trigger is no longer a path anybody can walk. If a later
slice gives the composite an input a forward date move can flip, that test should be rewritten
around it and the pin dropped.

## Decision, part 2: a derived case-level condition, read at display time

`CaseOverview` and `RequirementDetail` carry `application_date_has_passed`, derived in
`assessments.service._application_date_has_passed` from the case's current date and today.
A notice on both screens names the date and offers the one action that helps.

**This is not what entry 11 proposed, or what this ADR first drafted**, and the difference
is the whole decision. Both said: a derived `Limitation` on every date-anchored residence
rule, computed at assessment time, with a rule version bump and a migration.

**A `Limitation` is the wrong type for this.** It is defined as a structured condition
reducing confidence in a *result* (Domain §33). No result's confidence changes when a date
goes by. "451 days across 16 April 2022 to 15 April 2027" is true of that window
permanently, and stays exactly as certain as it was. What changes is whether that window is
still the one the applicant means — a fact about the case today, not about the run that
produced the figure.

**And that mis-typing is what created the hard problem.** Attaching today's facts to an
immutable past result forces the question "how does the result learn that today moved?",
which has only expensive answers. Staleness here is event-driven: a result goes stale when a
declared input version changes, in the same transaction. Time passing is not an input version
change. So a limitation computed at assessment time would never reach a case nobody
recalculates — precisely the case it exists to protect — and closing that gap needs one of:

- **`as_of` as a declared input.** Truthful and unusable: every case restales every day and
  the issue queue fills with rechecks nobody asked for.
- **A scheduled sweep** that stales cases whose date has passed. Consistent with the
  event-driven model, at the cost of the first scheduled job in the system.
- **Compute it at read time.** Rejected in the first draft on the grounds that it breaks
  "a displayed result is exactly what the run produced".

The third objection dissolves once the condition stops pretending to be part of the result.
Nothing is added to a result; a fact about the case is computed when the case is read. That
is already how `current_phase` works, under ADR-0009, on the same response.

So: no rule change, no summary code, no migration, no scheduled job, and nothing fabricated
on an immutable record. The rules spec gains §4.0 stating that the rules do not constrain
the date and that its passing is a read-model condition rather than a rule outcome.

**What this does not do.** The conclusions themselves are unchanged — `residence.total_absences`
on a drifted case still reads SUPPORTED at 0 days, because that is what the window contains.
The notice is what stops that being read as an answer about the application the user is
preparing. If a future slice wants the conclusion itself to move, that is a rules change and
needs its own spec entry; this one deliberately does not make the product disagree with its
own arithmetic.

## Consequences

Entry 11 stops overstating what is closed. A newly chosen past date is refused by the product
rather than by the browser, and the API is no longer a way around a rule the UI appears to
enforce.

A drifted date is still believed, and is now the *only* remaining half, recorded as such in
entry 11 and asserted by
`test_a_date_that_drifted_into_the_past_is_still_read_back` so that nobody mistakes the guard
for a full fix.

**`just seed` acquires an expiry date.** `DEMO_APPLICATION_DATE` is `2027-04-15`, and on
16 April 2027 seeding will raise `ApplicationDateInPast` instead of quietly producing a demo
case whose window has closed. Failing loudly is the better of the two, and it is the same
calendar-boundary cost entry 11 warned about, now paid somewhere visible. Worth making the
seed date relative — `today + 18 months`, say — before that date rather than after it.
