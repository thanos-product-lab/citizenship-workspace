# ADR-0022: Activating a second rule version stales every result the first produced

**Status:** Accepted
**Date:** 2026-08-25
**Milestone:** M7 (Evidence Foundation), slice 4a

## Context

ADR-0014 chose selective dependency invalidation and recorded one gap it did not close:

> Dependencies resolve against the *currently active* rule version, not the version that
> produced the result being invalidated. If a rule's v2 drops a dependency its v1 declared,
> a change to that input misses a v1-produced result which stays CURRENT. Unreachable today
> (one rule version each, nothing emits `RULE_VERSION_CHANGED`); closing it means joining
> dependencies to `AssessmentResult.rule_version_id`, and belongs with the first rule-set
> migration at M9.

Slice 4a activates `residence.travel_consistency` v2.0.0 — the first second rule version in
the product. **The gap is now reachable**, exactly as the M7 plan predicted it would be.

The concrete hazard: a case assessed under v1 holds results produced by a rule version whose
declared dependencies differ from the active one's. Invalidation reads the *active* version's
dependencies, so any dependency v1 declared and v2 does not is a dependency whose input can
change while a v1-produced result stays CURRENT — a stale result returned as current, which
CLAUDE.md §9 lists as an invariant that must hold.

In this instance v2 only *adds* a dependency, so no v1 dependency is dropped and the specific
hazard does not fire. Relying on that would be relying on an accident of this one change.

## Decision

**The activation migration stales every current result the outgoing rule version produced.**

Migration `0022_travel_consistency_v2` sets `effective_to` on v1, inserts v2 with its
dependency rows, and marks every `AssessmentResult` whose `rule_version_id` is v1 and whose
currency is `CURRENT` as `STALE` with reason `RULE_VERSION_CHANGED`.

No v1-produced result survives as current, so there is no result for the active-version
dependency lookup to miss. The gap is **narrowed by construction rather than closed**: the
lookup is still wrong in principle, and it now has nothing to be wrong about.

This is the cheap answer of the two ADR-0014 named. The expensive one — joining dependencies
to `AssessmentResult.rule_version_id` so invalidation resolves against the version that
produced each result — remains assigned to M9, and this ADR does not discharge it.

## Consequences

- Every case with a travel-consistency result shows it as `STALE` immediately after
  deploy, until recalculated. That is honest: the rule that produced it no longer exists,
  and its conclusion did not consider evidence coverage at all.
- `RULE_VERSION_CHANGED` gets its first producer. It existed as an `AssessmentTriggerType`
  and unused; the matching **stale reason code** and its user-facing sentence are new, as is
  `EVIDENCE_SUPPORT_CHANGED`'s. Those two vocabularies are separate and easily confused — a
  trigger says why a run started, a stale reason says why a result stopped being current.
- Conclusion and currency stay separate (directive 4, ADR-0001): the swept results keep
  their conclusions and change only currency. Nothing is edited in place beyond the
  currency mark, and no assessment row is rewritten — directive 3 holds.
- The sweep is data-touching migration, so it is bounded and idempotent: it matches on
  `rule_version_id` and `currency = CURRENT`, so re-running changes nothing.
- **The issue queue does not follow the sweep, and there is a window where the two
  disagree.** `invalidate_for_input_change` reconciles the queue in the same unit of work
  precisely so "a stale result and the issue announcing it must never disagree" holds at
  every call site. A migration is not one of those call sites: it runs with no request, no
  actor and no `UnitOfWork`, and reaching into `issues_service` from Alembic would make a
  schema migration depend on application services that will have moved on by the time
  anyone replays it.

  So after this migration deploys, a case with a travel-consistency result reads `STALE`
  while its queue shows no `STALE_ASSESSMENT` item for it, until the next write that
  reconciles — any assessment recalculation, or any input change. The requirement itself is
  honest throughout: it carries `RULE_VERSION_CHANGED` and its own stale notice. What is
  missing for that window is the queue's copy of the same fact.

  Accepted rather than fixed, because the alternatives are worse: a migration that imports
  application services, or a boot-time sweep that would run on every deploy. Recorded here
  because it is a real divergence from an invariant this codebase otherwise holds
  absolutely, and whoever activates the next rule version inherits it.
- A test asserts a v1-produced result is `STALE` after migration. Mutation: skip the sweep,
  and it goes red — otherwise the sweep is invisible in a repository where every test
  fixture is created after the migration has already run.

## Alternatives rejected

**Do nothing, because v2 only adds a dependency.** True today and not a property of the
mechanism. The next rule version to *remove* a dependency would reintroduce the hazard
silently, with no test failing, and whoever wrote it would have no reason to read ADR-0014.

**Close the gap properly now — join dependencies to the producing rule version.** The
correct fix, and it changes the shape of the invalidation query that every rule depends on,
inside a slice already carrying two RFC changes, a new table, and the first evidence
dependency. Doing it here would mean the riskiest query in the system changing alongside the
riskiest new dependency, with one review covering both.

**Emit `RULE_VERSION_CHANGED` as a domain event and let the normal invalidation path
handle it.** The event-driven route is the eventual shape, but the invalidation path resolves
*requirements from input kinds*, and a rule-version change is not an input change. Bending it
to fit would have distorted the mechanism to save one migration.

## Invariants touched

- **CLAUDE.md §9: "A stale result is never returned as current."** This is the invariant the
  gap threatens, and the sweep is what keeps it true across a rule-version boundary.
- **Directive 3 (assessment history is immutable).** Preserved: the swept results are marked
  stale, not rewritten, and remain inspectable with their original rule version and inputs.
