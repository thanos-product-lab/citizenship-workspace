# ADR-0007: In M3B the AssessmentResult is the single source of truth for requirement conclusions; guidance is cited by source-id until M5

**Status:** Accepted
**Date:** 2026-08-11
**Milestone:** M3B (Deterministic Rules and Immutable Assessments)

## Context

ADR-0004 deferred the requirements/assessment engine to M3B: in M2 the three route
rules were pure functions projected onto the case's `support_status`, with the decision
recorded only in the `RouteSupportEvaluated` event, and it flagged two things to settle
at M3B — *"risks a second source of truth for conclusions"* and *"the adult rule's caller
must switch from `today()` to [the application] date."* M3B slice 1 now persists route
results as `AssessmentResult` rows, so both must be settled. Separately, the `new-rule`
procedure requires every rule to cite a guidance source, but the `GuidanceSource` /
`GuidanceSection` tables and the `RuleGuidanceLink` FK are Migration 5, not yet built.

## Decision

**1. The persisted `AssessmentResult` is the single source of truth for a requirement's
conclusion.** The read projections (`GET /requirements`, `GET /requirements/{key}`) read
conclusions only from `AssessmentResult`. `route_rules` remains the single *evaluator*;
the assessments module is the single *result store*. Two things that are **not** a second
conclusion store:

- **`case.support_status`** is a coarser *case-lifecycle* signal (it gates `ACTIVE`), a
  projection of the composite conclusion — not a per-requirement conclusion. It is
  legitimately separate (ADR-0004) and is never read as a requirement conclusion.
- **`RouteSupportEvaluated`** is an audit / outbox signal carrying the decision for
  reproducibility. Nothing reads it to answer "what is this requirement's conclusion."

The confirm-time route evaluation (reference date `today()`, no application date selected
yet) answers only "may this case become active"; the trusted `AssessmentResult` is
evaluated at the **selected application date** (ADR-0004's promised switch) and is the
authoritative requirement conclusion. Before a trusted run exists, a route requirement
reads `NOT_YET_ASSESSED` — the confirm event does not populate the conclusion store, which
is the property the single-source guard test pins.

**2. Guidance is cited by stable source-id string until M5.** Each seeded `RuleVersion`
carries its citation in `configuration.guidance` as `{source, section}` entries
(e.g. `GUIDE_AN`). M5 adds the `GuidanceSource` / `GuidanceVersion` / `GuidanceSection`
tables and the `RuleGuidanceLink` FK, and **backfills the links from these strings**,
which are retained as provenance. No rule ships without a citation; only its physical
form changes at M5.

## Alternatives rejected

- **Have `GET /requirements` read route conclusions from the `RouteSupportEvaluated`
  event or `support_status`.** Recreates exactly the "second source of truth" ADR-0004
  warned against, and the event's conclusions are evaluated at `today()`, not the
  application date. Rejected.
- **Re-run and persist route results at confirm time.** At confirm no application date
  exists, so the adult/composite results could not carry a complete input link
  (`PROPOSED_APPLICATION_DATE`), violating strict provenance. Persisting at recalculation,
  once a date is selected, keeps every result fully linked. Rejected for slice 1.
- **Block the rules until the M5 guidance tables exist.** Would stall the deterministic
  core (the whole point of M3B) on a later milestone. Rejected: a source-id string is a
  faithful, forward-compatible citation.

## Consequences

- **Easier:** one place to read a conclusion; history and supersession are uniform across
  every requirement; the guidance citation is present from day one and needs no schema to
  be inspectable.
- **Harder / committed:** M5 must backfill `RuleGuidanceLink` from the config strings and
  keep them in step; the confirm-gate (`support_status`) and the trusted result can in
  principle differ at an 18th-birthday boundary (gate uses `today()`, result uses the
  application date) — this is intended, because they answer different questions, and only
  the result is a requirement conclusion.

## Invariants touched

- **§2.4 (conclusion and currency are separate):** upheld — results store both as distinct
  columns; the projections never merge them.
- **§2.5 (no conclusion without provenance):** upheld in full for persisted results — every
  trusted result writes an `AssessmentInputLink` per declared dependency and references a
  `RuleVersion`; guidance provenance is a source-id string until M5 makes it a FK.
- **§2.1 (AI output is a proposal):** untouched — no AI in this path.
