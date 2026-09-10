# Eval run — 10 September 2026

> **Superseded by `EVAL_RESULTS_2026-09-10b.md`, and kept deliberately.** The failure
> recorded below was a defect in the fixture, not in the model: the document stated a night
> count whose arithmetic resolved the ambiguity it was written to preserve, so the extractor
> was marked wrong for reasoning correctly. This file is left as written because a
> measurement that turned out to be measuring the wrong thing is worth keeping next to the
> one that corrected it — deleting it would leave the corpus looking as though it had always
> been sound.

First run that computes the **false-reassurance rate**. Provider: OpenAI,
`gpt-4o-mini` for all three capabilities. Total spend $0.0015 across 9 calls.

```
passed 8  failed 1  unmeasured 0

false-reassurance rate: 11.1%  (1 of 9 measured)
  unnecessary abstentions: 0
  by risk:       HIGH 1/5   MEDIUM 0/4
  by capability: DocumentClassifier 0/6   TravelRecordExtractor 1/3

gate: FAIL
  HIGH-RISK FAILURE  travel_ambiguous_numeric_dates_001
  FALSE REASSURANCE  travel_ambiguous_numeric_dates_001:
    forbidden content in output: ['2025-04-09']
```

## The one failure is the one that matters most

`travel_ambiguous_numeric_dates_001` is the fixture that tests the premise
**blind confirmation rests on**. The document writes its dates as `03/04/2025`
and `09/04/2025` and states no convention. The manifest expects `iso: null` for
both, and lists all four readings under `must_not_extract`.

The model returned `2025-04-09` — a defensible reading of `09/04/2025` under
day-first convention, and precisely the failure the metric is named after: it
chose one reading of an ambiguous date without signalling the ambiguity
(AI_EVALUATION_PLAN §11). A user reviewing that field would be shown a
confident date, and blind entry is the only thing standing between it and a
`FactVersion`.

**This is not a harness artefact.** The grader compared against ground truth
authored before any model ran, and the value it found is on the fixture's own
forbidden list.

Worth noting what the run does *not* tell us: the forbidden-value check fires
before the field-level comparison, so the report says one forbidden date
appeared but not whether the model also asserted the departure date or
abstained on it. Whether this is a systematic convention choice or a partial
abstention is unmeasured, and worth one more fixture rather than one more guess.

## Reading the rate honestly

**Nine measurements.** One failure moves the rate 11 points, so the figure is a
baseline to watch rather than a threshold to defend. §19 forbids setting a
numeric threshold before a baseline exists; this is that baseline, and the
corpus needs to grow before the number means much. CLAUDE.md §9 names thirteen
required scenarios and the corpus covers fewer.

**`DocumentClaimExtractor` contributes nothing.** Its three fixtures are in the
manifest and the capability is unbuilt, so the runner never reaches them — they
are outside the denominator entirely, not scored as passes. The corpus reads as
12 fixtures and 9 were measurable.

**The rate is not one minus the pass rate**, and the abstention line is what
says so. A model that got quieter — refusing more fields — would lower this
number while getting less useful, and `unnecessary abstentions: 0` is the
counterweight that would show it. Both are published for that reason.

## What the gate says

`gate: FAIL`, correctly. A HIGH-risk fixture failed, and §19 makes that
release-blocking regardless of the aggregate.

The metric adds no gating power today — the gate already fails on any failure at
all — so it earns its place as the number to watch across runs and to report in
the case study, not as a new blocker. That changes when the corpus is large
enough that "zero failures" stops being a reasonable bar.
