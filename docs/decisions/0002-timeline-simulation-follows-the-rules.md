# ADR-0002: Date-simulation mockups must follow the deterministic rules

**Status:** Accepted
**Date:** 2026-07-24
**Milestone:** M5 (application-date simulation), documentation reconciliation

## Context

The timeline mockup in the UI/UX doc (§8.3) showed moving the proposed
application date by one day (15 → 16 April 2027) flipping physical-presence from
"Not supported" to "Supported" and reducing the absence total by two days.

Both are inconsistent with DETERMINISTIC_RULES_SPEC.md:

1. The qualifying window is `[application_date − 5y + 1d, application_date]`
   (§3). Moving the application date forward moves the **whole window** forward.
   To clear an absent anchor date you must move past the entire trip that covers
   it — typically several days, not one.
2. Absence totals are the cardinality of a union of date sets intersected with
   the window (§5.2). Sliding the window drops early days and adds later ones;
   it does not subtract a fixed two. The magnitude and direction shown were
   arbitrary.

The risk is concrete: the mockup is the spec a developer builds the simulator
from. A wrong mockup becomes a wrong simulator, and the simulator is the
interaction the demo hinges on.

## Decision

Mockups that show calculated values must be internally consistent with the rules
spec, and must use the spec's own worked example (§9) where one exists. The
corrected mockup uses the Spain trip (14–20 April 2022) covering the anchor date,
resolving at 20 April 2027 — a multi-day move, as the rules require.

All calculated values in any mockup are illustrative of *behaviour*, never a
source of truth. The server computes; the client and the mockups render.

## Alternatives rejected

- **Just fix the numbers.** Bumping 424 to some other figure would still teach
  "one day is enough," which is the substantive error. The example structure had
  to change, not just its digits.
- **Remove the numbers from the mockup.** Loses the point of the interaction —
  before/after values are what make the simulator legible. Keep them, make them
  correct.

## Consequences

- The M5 simulator is built against a correct reference.
- A milestone-gate question at M5 asks the builder to explain why clearing an
  anchor date usually needs a multi-day move — closing the loop on this exact
  misconception.
- Reviewers should treat any calculated value in design assets as suspect until
  checked against the rules spec.

## Invariants touched

CLAUDE.md §2.2 (determinism in Python, never re-derived client-side) and §8
(calculations are server-side). This ADR applies them to design artefacts, which
were previously an unguarded surface.
