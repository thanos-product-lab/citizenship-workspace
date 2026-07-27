"""The `requirements` module: deterministic requirement rules and their vocabulary.

At M2 this holds only the route-scope rules (§7.1, §7.2, §7.2b) as **pure
functions** and the shared `Conclusion` enum. The full requirements engine —
`RequirementDefinition`, `RuleVersion`, persisted `AssessmentResult`, the
selective-invalidation graph — arrives at M3B and will wrap these same functions
in the `RequirementEvaluator` protocol without changing their logic (ADR-0004).

This module imports nothing from other domain modules: rules take primitive and
enum inputs so the dependency only ever runs *into* here, never back out.
"""
