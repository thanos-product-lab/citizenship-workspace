# AI evaluation suite

Structure per `docs/evaluations/AI_EVALUATION_PLAN.md` §6. Run with `just eval`.
**Not run on every commit** (CLAUDE.md §9) — it makes real model calls and costs
real money.

```
evals/
├── fixtures/     the documents, and the script that authors them
├── manifests/    what each fixture is, and what it must and must not yield
├── graders/      deterministic scoring          (slice 1)
├── runners/      capability harness             (slice 1)
└── reports/      run output                     (slice 1)
```

At present only `fixtures/` and `manifests/` exist. They came out of the M8
throwaway spike (`IMPLEMENTATION_ROADMAP.md` §3.3); the spike itself is deleted,
and its numbers are in `docs/evaluations/AI_SPIKE_FINDINGS.md`.

## Fixtures

Six documents, all synthetic, all consistent with `SYNTHETIC_DEMO_CASE.md`. No
real personal data appears here or anywhere else public (CLAUDE.md §2.9).

**Generated, not committed** — the same rule `scripts/make_fixtures.py` follows,
for the same reason: a checked-in PDF is a binary nobody reviews, whereas
`fixtures/make_documents.py` puts every value in every document in reviewable
source. The expected values in `manifests/` are only worth trusting if the
document they describe can be read, and that file is where it is read. The PDFs
are gitignored.

Generate with `uv run python evals/fixtures/make_documents.py` from
`services/platform`.

This corpus is separate from `scripts/make_fixtures.py`, which authors the
*hostile* documents — scans with no text layer, password-protected files, an
executable wearing a PDF's name — to exercise the reader. These are the opposite:
clean and content-rich, to exercise extraction quality. The two injection fixtures
are likewise distinct — that one proves the reader treats injected text as inert,
this one carries injected text *and* real extractable dates, because §14 requires
genuine extraction to still succeed on an attacked document and a page with
nothing to extract cannot show that.

## Ground truth

`manifests/*.jsonl` hold the expectations, authored from the documents and
**before** any model output was seen (§9's independence requirement).

Two fields carry most of the value:

- `expected` — what the fixture must yield. A `null` expectation is a real
  expectation: on `travel/ambiguous_numeric_dates.pdf` the only correct answer for
  `date_iso` is null, and a confident date is a failure however plausible it looks.
- `must_not_extract` — the plausible wrong answers. Four of the six documents
  place a credible distractor next to the right value, because wrong-and-confident
  is the failure mode that matters and a fixture with only one candidate answer
  cannot detect it.

`risk: HIGH` marks fixtures whose failure changes an assessment conclusion or
breaches a §19 zero-tolerance gate. These are never averaged into a headline
number (§3.4).
