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
- `EVAL_RESULTS_2026-09-11.md` — **0.0% (0 of 16)**, gate PASS, with the two new
  claim extractors (ADR-0029). Records that the injection fixture graded no authority
  channel until the security review caught it, and that four of this milestone's eval
  failures were defects in the harness rather than the model. **Current.**
- `EVAL_RESULTS_2026-09-10d.md` — **0.0% (0 of 12)**, gate PASS, under
  `classify_document.v2`. The two documents that failed at 18.2% are byte-identical;
  only the prompt changed. Includes a held-out fixture the prompt was not written
  against, which is what makes the zero mean anything. **Current.**
- `EVAL_RESULTS_2026-09-10c.md` — **18.2% (2 of 11)**, gate FAIL, after adding the
  two classifier abstention fixtures. The 0.0% below was measured over a corpus
  where `UNSUPPORTED` and `AMBIGUOUS` had no fixture at all; given one each, the
  classifier forces a category both times. Read this one first.
- `EVAL_RESULTS_2026-09-10b.md` — **0.0% (0 of 9)**, gate PASS. The first run's
  failure was a defect in that fixture, not in the model: the document stated a
  night count whose arithmetic resolved the ambiguity it was written to
  preserve. Both runs are kept. A corrected measurement does not delete the
  measurement it corrects.
