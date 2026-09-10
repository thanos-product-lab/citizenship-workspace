# Evaluations

- `AI_EVALUATION_PLAN.md` — capability fixtures, grading logic, regression
  thresholds, release gates. Blocking document for M8.
- `AI_SPIKE_FINDINGS.md` — what the M8 throwaway spike measured, and the three
  findings that changed the plan. The baseline §19 requires before any numeric
  threshold is set.

The suite itself lives in `services/platform/evals/`. Run it with
`uv run python -m evals.runner --run` — without `--run` it checks only that the
manifests are coherent and calls no model, because calls cost money.

Run results land here as `EVAL_RESULTS_<date>.md`. The headline metric is
**false-reassurance rate**; report it even when it is bad, especially when it is
bad. Honest evaluation reporting is part of the portfolio signal.

- `EVAL_RESULTS_2026-09-10.md` — first measured false-reassurance rate: **11.1%
  (1 of 9)**, the one failure being the ambiguous-date fixture that tests the
  premise blind confirmation rests on. Gate FAIL.
