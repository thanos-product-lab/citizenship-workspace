# ADR-0008: Stale invalidation is blunt at M3B; selective invalidation waits for M6

**Status:** Superseded by [ADR-0014](0014-selective-dependency-invalidation.md) (2026-08-19)
**Date:** 2026-08-13
**Milestone:** M3B (Deterministic Rules and Immutable Assessments)

## Context

Domain §41 requires that when an assessed input changes, the results that depend on it are
marked STALE **in the same transaction**, and that recalculation then supersedes them. §41.5
describes *selective* invalidation — using the dependency graph to stale exactly the affected
requirements — and the roadmap assigns that to M6. M3B still needs a working stale seam so the
conclusion-vs-currency separation (ADR-0001) and the demo's stale transition
(`SYNTHETIC_DEMO_CASE.md` §7) are real, but without the full dependency-driven precision.

## Decision

**Any residence input change marks all current residence-group results STALE, in the same
transaction as the change.** The residence group is the five `residence.*` requirements. The
triggers are the proposed application date (select or change) and any travel record write
(create, edit, remove, import). The marking runs on the input command's own unit of work
(`invalidate_residence_results`), so the STALE marks, the `AssessmentInvalidated` event, and the
input change commit atomically or not at all.

Reads show the **non-superseded** result — CURRENT, or STALE after a change — so a stale
conclusion stays visible and flagged (§41.4), never hidden. Recalculation supersedes that stale
result and writes a new CURRENT one; a failed recalculation rolls back and leaves it STALE,
promoting nothing.

This is deliberately imprecise in two directions:

- **Over-invalidation within residence.** Changing one travel record marks
  `residence.qualifying_period` stale even though that rule depends only on the application
  date. Harmless: recalculation reproduces the same conclusion.
- **Under-invalidation across groups.** An application-date change marks residence stale but
  **not** `status.holding_period` or the route rules, which also depend on the date (§8, and
  §41.5's selective set for the application date includes `status.holding_period`). So between
  an application-date change and the next recalculation, `status.holding_period` can read
  CURRENT while stale-in-fact.

Both are accepted at M3B because recalculation always re-evaluates the **full** in-scope set and
supersedes every prior result, and the product's flow recalculates after a change. M6 selective
invalidation (§41.5) closes both gaps by driving off the recorded dependency definitions.

## Alternatives rejected

- **Mark *all* current results stale on any residence change.** Safe against under-invalidation,
  but produces confusing UX — adding a trip would flag "settled status" as stale — for no
  correctness gain, since recalculation refreshes everything anyway. Rejected.
- **Implement selective (per-dependency) invalidation now.** Pulls the M6 dependency-graph
  traversal and its edge cases forward into M3B, against the roadmap's sequencing, for precision
  the demo does not need. Rejected.

## Consequences

- **Easier:** one blunt rule, trivially correct within residence; the stale seam is isolated and
  testable now; the demo's CURRENT → STALE → SUPERSEDED cycle works.
- **Harder / committed:** M6 must add the cross-group edges (application-date → status, per
  §41.5) and narrow the within-residence over-invalidation using the dependency definitions. The
  under-invalidation window above is the reason M6 is not optional.

## Invariants touched

- **§2.3 (assessment history immutable):** upheld — staling changes only currency; recalculation
  is a new run that supersedes, never an in-place edit.
- **§2.4 (conclusion and currency separate):** upheld — a STALE result keeps its conclusion and
  is shown as such.
- **"A stale result is never returned as current":** upheld — the projection reports the stale
  result *as STALE*, not as current.
- **"Changing an unrelated input does not invalidate an unrelated assessment":** partially — held
  across groups (a residence change never stales route/status), relaxed *within* residence by the
  blunt rule, restored fully at M6.
