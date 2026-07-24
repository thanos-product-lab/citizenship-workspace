# Synthetic Demo Case

### Status

**NOT YET WRITTEN — blocks Milestone 3A**

This file is a placeholder so that references to it resolve. Do not treat its
absence as optional: `IMPLEMENTATION_ROADMAP.md` §2.1 gates M3A on it.

---

## What this document must contain

One canonical synthetic applicant, used for seed data, unit tests, integration
tests, Playwright flows, AI evaluation fixtures, screenshots, and the demo video.
One fixture, every purpose — divergence between them is a defect.

Per `MVP_SCOPE_AND_ACCEPTANCE_CRITERIA.md` §13, the fixture must contain:

- adult Section 6(1) applicant, EU settled status
- status held long enough for the proposed date
- five-year travel history
- total absences near but within the standard threshold
- final-year absences clearly within the standard threshold
- one conflicting return date
- one travel record without supporting evidence
- Life in the UK evidence, B1 language evidence
- one completed referee, one missing referee
- a proposed application date that initially fails the physical-presence check
- an alternative date that resolves it

And must produce: supported requirements, one near-threshold state, one
inconsistent state, one incomplete state, one stale assessment after a fact
change, and a final resolved preparation state.

## Acceptance criteria

- Every requirement in `DETERMINISTIC_RULES_SPEC.md` §7 has an **expected
  conclusion and expected numeric output**, derived by hand from the spec — not
  from running the implementation.
- The physical-presence failure and its resolving date are both stated.
- Expected absence totals are shown with their working, so a failing test can be
  diagnosed against the arithmetic rather than against the code.
- All names, document identifiers, and references are fictional.

The worked example in `DETERMINISTIC_RULES_SPEC.md` §9 is the starting point: it
already produces the physical-presence failure and demonstrates boundary
clipping.
