---
name: new-rule
description: Procedure for adding or changing a deterministic requirement rule — evaluator, rule version, dependency declaration, guidance link, banding, summary codes, and property tests. Use whenever a requirement is added to the requirements engine or an existing rule's behaviour changes.
---

# Adding a deterministic rule

Rules are the correctness core of this product. A half-added rule — an evaluator
without a dependency declaration, or a threshold without a guidance citation —
silently breaks selective invalidation or provenance. Complete every step.

## 1. Spec first

The rule must exist in `docs/architecture/DETERMINISTIC_RULES_SPEC.md` **before**
it exists in code. If it does not, stop and propose the spec entry.

The spec entry needs: requirement key, inputs, computation, conclusion banding
with exact boundaries, summary codes with parameters, and every threshold tagged
`[GUIDANCE]` (with citation) or `[PRODUCT]` (with rationale).

## 2. Definition and version

- Add the `RequirementDefinition`: `requirement_key`, `route_key`, `group_key`,
  title, `evaluator_key`, display order. Keys are stable public identifiers —
  choose carefully; they cannot be renamed once assessments exist.
- Create the `RuleVersion` with `semantic_version`, `rule_set`, configuration,
  `effective_from`, and `implementation_hash`.
- Link it to approved `GuidanceSection` rows via `RuleGuidanceLink`. **Every rule
  cites at least one guidance source.** No exceptions.

## 3. Declare dependencies — before writing the evaluator

Add `RuleDependencyDefinition` rows for every input the evaluator will read.

Then verify the evaluator reads **nothing else**. An undeclared read is the
subtlest bug in this system: the rule works, tests pass, and selective
invalidation silently misses it, so the result goes stale without being marked
stale. Cross-check against the dependency matrix in `DETERMINISTIC_RULES_SPEC.md`
§8.

## 4. Implement the evaluator

- Conform to the `RequirementEvaluator` protocol.
- Pure function of `(CaseSnapshot, RuleContext) → AssessmentResult`. No I/O, no
  clock reads, no randomness — deterministic means reproducible.
- Return structured `Limitation` and `NextAction` values, never prose.
- Return a `calculation_breakdown` listing the exact inputs used, so the UI can
  render provenance without recomputing anything.
- Use the shared window and absence-counting helpers. Never re-derive window
  arithmetic locally — that is how the `+1 day` gets lost.

## 5. Banding and the sensitivity rule

- Boundaries must match the spec exactly, including which band an edge value
  falls into.
- If the rule compares against a threshold, it computes **both**
  `trusted_total` and `provisional_total` and applies the sensitivity rule
  (`DETERMINISTIC_RULES_SPEC.md` §6.2). A conclusion may be downgraded by
  provisional data, never upgraded.

## 6. Tests

Required in the same change:

- Unit tests for each band, including both sides of every boundary.
- Hypothesis property tests for any property in spec §10 this rule touches.
- Monotonicity: more absence days never yields a less severe conclusion.
- Determinism: same inputs, same output, across repeated runs.
- Provenance: the result writes an `AssessmentInputLink` for every declared
  dependency.
- Leap-year and month-boundary cases if the rule does date arithmetic.

## 7. Wire the invalidation

Add the rule to the selective invalidation path so that changing any declared
input marks its results stale — in the same transaction as the input change.

Then test it: change each declared input, assert this rule's result goes stale;
change an undeclared input, assert it does not.

## 8. Finally

Run `rules-conformance-reviewer`, then `trust-model-reviewer`.

Update the dependency matrix in the spec if it changed.
