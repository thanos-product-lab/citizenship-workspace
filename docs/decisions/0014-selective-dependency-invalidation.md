# ADR-0014: Selective invalidation, driven by declared dependencies and composition edges

**Status:** Accepted
**Date:** 2026-08-19
**Milestone:** M6 (Issue Detection and Stale-State Workflow), slice 1
**Supersedes:** ADR-0008 (blunt stale invalidation at M3B)

## Context

ADR-0008 accepted a blunt rule: any residence input change marks every current
`residence.*` result STALE. It shipped working, and it named its own two errors.

- **Over-firing inside residence.** A travel edit staled `residence.qualifying_period`,
  which reads only the application date. Noise; recalculation reproduced the same
  conclusion.
- **Under-firing across groups.** An application-date change staled residence but not
  `status.holding_period`, `route.adult_applicant`, or `route.standard_section_6_1`, all of
  which depend on that date. Between the change and the next recalculation those read
  CURRENT while stale in fact.

The two are not symmetric. Over-firing costs a recalculation. Under-firing shows a user a
confident conclusion whose inputs have moved, with no notice, no badge and no failing test —
directive 7 inverted, and the reason M6 was never optional.

`rule_dependency_definitions` has held the information needed to fix this since migration
0007. Nothing read it: `RequirementCatalogRepository.list_dependencies` had no caller in
`app/`.

## Decision

**Stale propagation resolves the affected requirement set from the declared dependencies of
each ACTIVE rule, then closes over composition edges, in the same transaction as the input
change.** `invalidate_for_input_change` and `resolve_affected_requirements` in
`app/assessments/invalidation.py` fill the role Domain §48.5 names
`AssessmentInvalidationService`; they replace `invalidate_residence_results`, and the blunt
function and its repository primitive are deleted.

### Composition edges are a first-class relation

`route.standard_section_6_1` composes the `route.adult_applicant` and
`route.supported_status` **conclusions**. Domain §25.1 has no result kind, deliberately — a
conclusion is not a versioned input and has no version to record in an `AssessmentInputLink`.
So the edge is its own table, `rule_composition_edges`, keyed to the composite's
`rule_version_id` and therefore versioned with the rule exactly as §25.3 requires a
dependency to be (new Domain §25.4).

Closure is transitive on **staling**, not on conclusion-change: if an upstream result is
STALE its conclusion is no longer known-current, so everything composing it is STALE too,
regardless of what recalculation would eventually produce. The closure iterates to a fixed
point rather than expanding one level, because chains can be deeper than one hop: once
`preparation.case_complete` has an evaluator, `case_complete → standard_section_6_1 →
adult_applicant` is a two-hop walk a single-level expansion would under-fire on. It also
tolerates a cycle, though none exists — the referee slots' mutual dependency (RULES_SPEC §8)
is a `REFEREE_RECORD` *input* dependency on both sides, matched in one pass, never a
composition edge.

### Matching is on input kind only, never on `input_key`

Some dependency rows name a field — `status.holding_period` declares
`ROUTE_PROFILE/status_granted_on` — and narrowing on that looks free: why stale a rule
reading only the grant date when the date of birth moved?

Because narrowing on a key is sound only when the input is versioned *per key*, and none of
ours is. A `RouteProfileVersion` is a whole-row snapshot: `confirmed_copy` mints a new
version id for a change to any field. Narrow on the key and a rule keeps a CURRENT result
whose recorded `ROUTE_PROFILE_VERSION` link points at a superseded version — breaking "every
current trusted assessment references current relevant input versions" (CLAUDE.md §9), with
nothing to catch it.

So `input_key` stays what it already is: provenance, recorded on `AssessmentInputLink` and
held to strict equality by the provenance test. It documents what a rule reads; it does not
filter what a change touches. Revisit only if a per-field-versioned input kind appears, and
cite that input's versioning as the reason.

### What changed in the numbers

| Change | Blunt | Selective |
|---|---|---|
| Travel record | 5 residence | **4** — `qualifying_period` declares no travel dependency |
| Application date | 5 residence | **8** — 7 declared dependants + the composite via closure |

## Consequences

- **Easier:** the affected set is data, not code, so a new rule is invalidated correctly by
  declaring its dependencies; the declaration rows finally have a consumer, which means
  drift between them and the evaluators is now load-bearing rather than decorative.
- **Harder / committed:** correctness now depends on declarations being complete, so three
  test layers hold them (below). The `ROUTE_PROFILE` path is implemented and tested but has
  no reachable writer — `confirm_route_profile` requires a draft case, so a confirmed profile
  cannot be edited on an active case. Because matching ignores `input_key`, whoever builds
  that edit path inherits nothing subtle: any profile write stales every rule reading the
  profile.
- **Known gap, not closed here.** Dependencies resolve against the *currently active* rule
  version, not the version that produced the result being invalidated. If a rule's v2 drops a
  dependency its v1 declared, a change to that input misses a v1-produced result which stays
  CURRENT. Unreachable today (one rule version each, nothing emits `RULE_VERSION_CHANGED`);
  closing it means joining dependencies to `AssessmentResult.rule_version_id`, and belongs
  with the first rule-set migration at M9. Recorded in the repository docstring.

## How under-firing is prevented

Three layers, because each is blind to what the others catch. Demonstrated by mutation, not
assumed:

1. **Strict-equality provenance** (`test_provenance.py`) — a result's input links equal its
   rule's declared dependencies, both directions, for all nine evaluated rules, plus the
   composite's edges against the conclusions it recorded. A coverage assertion forbids a rule
   sitting outside both checks, which `residence.qualifying_period` silently did.
2. **Differential vs blunt** (`test_selective_invalidation.py`) — selective must retain
   everything blunt caught except requirements declaring no dependency of the changed kind,
   with the exception set computed from the rows rather than written down.
3. **The recalculation-diff oracle** (`test_invalidation_completeness.py`) — recalculate,
   change an input, recalculate, and assert every requirement whose output moved was staled.
   Trusts no declaration.

Layer 3 is not redundant. An evaluator reading an input it neither declares nor links passes
every test in layers 1 and 2 — both read the declarations it is lying about — and fails only
here. Verified by introducing exactly that mutation.

Conversely, layer 3 alone is not enough: a missing composition edge is invisible to it unless
the upstream conclusion actually flips, which needs an applicant whose 18th birthday the
application date straddles. That fixture is now explicit, and it was written only after a
mutation showed the generated cases passing with the closure removed.

## Invariants touched

- **§2.3 (assessment history immutable):** upheld — staling changes currency only.
- **§2.4 (conclusion and currency separate):** upheld — a STALE result keeps its conclusion.
- **"A stale result is never returned as current":** upheld.
- **"Changing an unrelated input does not invalidate an unrelated assessment":** now held in
  both directions. ADR-0008 held it across groups and relaxed it within residence; this
  restores it, and closes the cross-group gap it did not hold at all.
- **An already-STALE result is not re-marked**, so `stale_reason_code` names the change that
  ended its currency rather than the most recent change. Deliberate; see §6.5 of the M6 plan.

## Related

An issue is not created by this slice. The boundary that governs the queue built on top of
it, recorded here because it belongs with the invalidation model:

> **Issues are data problems and process state. Priority actions are requirement outcomes.**

A reached negative conclusion is therefore not an issue.
`residence.physical_presence_start_date = NOT_CURRENTLY_SATISFIED` yields a priority action
from its `next_action`, as it does today, and no issue. Without the boundary the queue
becomes a second rendering of the requirements list, and UI/UX §10's action groups have no
home for "choose a different date".
