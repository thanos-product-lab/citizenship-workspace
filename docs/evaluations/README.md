# Evaluations

- `AI_EVALUATION_PLAN.md` — capability fixtures, grading logic, regression
  thresholds, release gates. Blocking document for M8.
- `AI_SPIKE_FINDINGS.md` — what the M8 throwaway spike measured, and the three
  findings that changed the plan. The baseline §19 requires before any numeric
  threshold is set.

The suite itself lives in `services/platform/evals/` (fixtures and manifests
today; graders, runners and reports arrive with the harness).

Run results land here as `EVAL_RESULTS_<date>.md`. The headline metric is
**false-reassurance rate**; report it even when it is bad, especially when it is
bad. Honest evaluation reporting is part of the portfolio signal.
