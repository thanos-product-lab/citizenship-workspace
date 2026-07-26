# ADR-0004: Route support is a service in M2; the requirements engine waits for M3B

**Status:** Accepted
**Date:** 2026-07-26
**Milestone:** M2 (Supported Case Setup)

## Context

M2 must turn a user's route-scope answers into a supported / unsupported /
review-needed outcome, and that outcome is owned by the `route.standard_section_6_1`
composite guard rule (RECONCILIATION item 8; RULES_SPEC §7.2b). But the persistence
for *trusted assessment results* — `RequirementDefinition`, `RuleVersion`,
`RuleDependencyDefinition`, `AssessmentRun`, `AssessmentResult`,
`AssessmentInputLink`, and the selective-invalidation graph — is Migration 3, which
lands in M3B. The roadmap's own M2 domain scope names a "route support service," not
the requirements engine, and Migration 1 ("Cases and Route") contains no assessment
tables. So M2 needs the *decision* without the machinery that normally records it.

## Decision

In M2 the three route rules — `route.adult_applicant`, `route.supported_status`,
and the `route.standard_section_6_1` composite — are implemented as **pure
deterministic functions** whose result is projected onto the case's `support_status`
field (Domain §7.4), not persisted as `AssessmentResult` rows. The composite's
dependency on the two upstream rules is satisfied by **function composition inside a
single service call** (their conclusions are computed in-memory and passed in), not
by a persisted cross-result dependency. Decision provenance (rule set + semantic
version + the profile version and the three conclusions) is recorded in the
domain-event / audit payload so the outcome stays reproducible before assessment
tables exist. At M3B these same pure functions are lifted behind the
`RequirementEvaluator` protocol without rewriting their logic, and the composite's
dependency becomes a real edge in the invalidation graph — the only rule that
depends on other results' conclusions.

## Alternatives rejected

- **Build the full requirements/assessment engine early in M2.** Pulls Migration 3
  and the invalidation graph forward, inflates the milestone, and front-loads the
  hardest correctness surface before the deterministic residence core (M3A/M3B) that
  motivates it. Rejected: the roadmap sequences the engine after versioned inputs
  for a reason.
- **Decide the route in the frontend / ad-hoc UI branching.** Would put a
  trust-bearing decision outside deterministic, tested Python and violate the
  "unsupported routes resolve through the composite guard" invariant. Rejected
  outright.
- **Persist a lightweight bespoke "route assessment" table just for M2.** Invents a
  schema we would delete at M3B when the real engine arrives, and risks a second
  source of truth for conclusions. Rejected: `support_status` on the case plus the
  event payload already carry the decision honestly.

## Consequences

- **Easier:** M2 stays a clean vertical (cases → onboarding → decision) with no
  premature engine; the pure rule functions get the full property-test treatment now
  and are reused verbatim at M3B.
- **Harder / committed:** we must structure the rule functions as
  `(inputs) → conclusion` with no I/O so M3B can wrap them, and we must remember that
  the composite's cross-conclusion dependency is *not yet* in a persisted
  invalidation graph — M3B must wire it. This ADR is the reminder.
- `support_status` is a projection of the composite conclusion:
  `SUPPORTED → SUPPORTED`; `REQUIRES_JUDGEMENT (may-be-British) → REQUIRES_REVIEW`;
  spouse route and unmet prerequisites (under-18, unsupported status) `→ UNSUPPORTED`;
  unconfirmed profile `→ NOT_EVALUATED`. A case only reaches `ACTIVE` on `SUPPORTED`.

## Invariants touched

- **§2.2 (determinism in Python, never prompts):** satisfied — the rules are pure
  Python with property tests; no prompt is involved.
- **§2.5 (no conclusion without provenance):** upheld in spirit — the M2 decision is
  not yet a trusted `AssessmentResult`, but its rule version and inputs are recorded
  in the event/audit payload so it is reproducible and inspectable. When the decision
  becomes a persisted `AssessmentResult` at M3B, structural provenance
  (`AssessmentInputLink` + `RuleVersion`) applies in full.
- **§2.1 (AI output is a proposal):** untouched — no AI in this path.
