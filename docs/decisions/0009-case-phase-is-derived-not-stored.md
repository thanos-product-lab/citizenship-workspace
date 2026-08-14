# ADR-0009: The case phase is derived, not stored

**Status:** Accepted
**Date:** 2026-08-14
**Milestone:** M4 (slice 1)

## Context

`cases.current_phase` is a column, written once by `ApplicationCase.create` as
`SETTING_UP` and never advanced by anything. Nothing in M1–M3B updated it, and
`CaseResponse` returned it verbatim, so `WorkspaceShell` rendered a phase pill
reading "Setting up" on a case with nine assessed requirements — including a
`NOT_CURRENTLY_SATISFIED` conclusion the user needs to act on.

Domain Model RFC §7.5 already says what the phase is: "The phase is derived from
case state, assessments, and issues." The column contradicted the model rather
than implementing it. M4 puts the phase on screen as part of the case overview,
which turns a dormant inconsistency into a visible false statement about how far
along a case is — the class of defect the product exists to prevent
(CLAUDE.md §2.7).

There is no stated derivation rule anywhere. §7.5 names the five enum values and
stops, so implementing the projection means choosing the ladder.

## Decision

The phase is computed at read time by `app.cases.phase.derive_phase`, a pure
function of the case lifecycle plus its current requirement states. No projection
reads `cases.current_phase`; the column stays only because removing it is a schema
change, and it carries a comment saying it is not the phase.

The ladder, in order — the first match wins:

1. lifecycle is not `ACTIVE` → `SETTING_UP`
2. no requirement has a displayed result → `SETTING_UP`
3. any result is `STALE`, or any conclusion is at or above `REQUIRES_JUDGEMENT`
   in the §7.13 severity order → `RESOLVING_ISSUES`
4. any catalogued requirement still has no real conclusion → `BUILDING_CASE`
5. otherwise → `NEARLY_PREPARED`

Three details that carry the weight:

- **Currency alone is sufficient for step 3.** A `SUPPORTED` result whose inputs
  have since changed still needs the user, and a phase that ignored currency would
  report a clean case on the strength of arithmetic that is out of date — ADR-0001
  applied to an aggregate.
- **`NEAR_THRESHOLD` does not move the phase.** It is a caution, not a task. It is
  rendered distinctly on the requirement itself; making it move the whole case to
  "resolving issues" would overstate it.
- **A stored `NOT_YET_ASSESSED` result does not count as concluded** in step 4. It
  is a placeholder, not a decision, and counting it would let a case read as
  prepared on the strength of requirements nothing decided.

`FINAL_REVIEW` is never produced. It depends on evidence and issue state that does
not exist until M6/M7, and `NEARLY_PREPARED` is unreachable in a real M4 case
because six of the fifteen catalogued requirements have no evaluator yet. Both
branches are unit-tested over synthetic states; a test asserts `FINAL_REVIEW`
cannot be reached at all.

The gathering lives in `app.assessments.service.derive_phases`, which already reads
both the case aggregate and the requirements catalogue. The case list derives in one
batched query rather than one per case.

## Alternatives rejected

- **Maintain the stored column on the write path**, updating it whenever an
  assessment run completes or an input restales results. Reads stay cheap, but it
  makes the phase a cached projection with a new invalidation obligation on every
  future write path — and every path that forgets produces exactly the silent lie
  this ADR is fixing. Domain §44 permits caching a projection but requires event
  invalidation; that is more machinery than a read-time derivation over data we
  already load.
- **Drop `current_phase` in this milestone.** Correct eventually, but M4 is a
  read-side milestone with no migrations by design. A column nothing reads is inert;
  a migration here would be scope drift.
- **Put the derivation in `app/cases/service.py`.** Natural home by name, but it
  would make the cases module import the assessment repository, pointing a
  dependency from `cases` into `assessments` when `assessments` already depends on
  `cases`. The rule lives in `cases.phase` as a pure function; only the gathering
  sits in `assessments`.
- **Compute the phase in the frontend from the requirements list.** The client
  already fetches conclusions, so it could count them. Rejected: it would put a
  domain rule in the browser, duplicate the severity ordering, and drift from the
  server's answer — CLAUDE.md §8 keeps derivations server-side and authoritative.

## Consequences

- `CaseResponse.from_domain` now takes a required `phase` keyword. A new call site
  cannot inherit the old bug by omission; it has to derive the value.
- `GET /api/v1/cases` costs one extra query for the whole list, and zero when the
  user has no active cases.
- The phase ladder is now a documented rule with a test table, so changing it is a
  visible decision rather than an accident.
- M6 and M7 must revisit steps 3–5 when issues and evidence exist, and make
  `FINAL_REVIEW` reachable. The unreachability test will fail at that point, which
  is the intended prompt to come back here.

## Invariants touched

**CLAUDE.md §2.6 (no readiness score).** The phase remains one of five named
qualitative states, derived, never a number and never ordered as a percentage. This
ADR strengthens §2.6: the phase now reflects real state instead of being frozen at
the first value, so it cannot imply progress that has not happened.

**CLAUDE.md §2.4 (conclusion and currency are separate).** The derivation reads both
axes independently — `is_stale` and `needs_attention` are separate tests, and a
stale result reaches `RESOLVING_ISSUES` through currency alone without its
conclusion being altered or discarded.
