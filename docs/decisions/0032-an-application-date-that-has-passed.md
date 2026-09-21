# ADR-0032: An application date that has passed

**Status:** **Proposed.** The selection guard described under "Decision, part 1" is
implemented. Part 2 amends `DETERMINISTIC_RULES_SPEC.md` and is not built, because the spec
has to say what the rule is before code can implement it (`new-rule` skill, step 1).
**Closes:** `KNOWN_LIMITATIONS.md` entry 11, half now and half on approval
**Found by:** scenario 11 of the walkthrough, recorded as finding 12 in `SCENARIO_FINDINGS.md`

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

## Decision, part 2: a derived limitation for a date that has drifted (proposed)

Entry 11 already names the shape: "a derived limitation and issue computed at assessment time
like every other conflict, which is a rules change with a version bump, a migration, and an
amendment to the rules spec, since the spec currently says nothing about whether a proposed
date may be in the past."

**Proposed spec entry**, for `DETERMINISTIC_RULES_SPEC.md`:

> **The proposed application date and the present day.** A proposed application date is a
> planning intention and may be any date the applicant chooses that has not already passed
> when they choose it. The rules do not otherwise constrain it.
>
> A date that has passed since it was selected does not invalidate the arithmetic: the window
> it defines is still computed the same way, and the conclusions drawn are still correct
> *about that window*. What changes is that the window has closed, so the conclusions no
> longer describe an application the applicant can still make.
>
> Every residence requirement whose window is anchored on the proposed application date
> therefore carries `APPLICATION_DATE_HAS_PASSED` (severity `REVIEW_REQUIRED`) when
> `application_date < as_of`, with parameters `application_date` and `as_of`. The conclusion
> itself is unchanged: the figure is what it is, and overstating it would be its own kind of
> false reassurance. What the limitation says is that the question has moved.

### The part entry 11 does not mention, and which needs deciding

"Computed at assessment time" is not sufficient on its own. Staleness in this product is
**event-driven**: a result goes stale when a declared input version changes, in the same
transaction. Time passing is not an input version change, so a case assessed today as
supported will still read supported tomorrow when its date passes. Nobody recalculates a case
they think is finished — which is precisely the case this is meant to protect.

Three ways to close that, and the choice belongs to whoever approves this:

- **`as_of` as a declared input.** Truthful and expensive: every case restales every day, and
  the issue queue fills with rechecks nobody asked for.
- **Compute the limitation at read time**, from the stored result plus today's date. Cheap,
  always correct, and it breaks the rule that a displayed result is exactly what the run
  produced — the limitation would appear on a result that never recorded it.
- **A scheduled sweep** that stales cases whose date has passed. Keeps the event-driven model
  honest by making the passage of the date into a real event, at the cost of the first
  scheduled job in the system.

The second is the smallest and the third is the most consistent with everything else here.
Neither should be chosen in a commit message.

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
