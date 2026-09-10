# Eval run — 10 September 2026, fourth run

`classify_document.v2`, measured against the abstention fixtures that failed under v1.
Provider: OpenAI, `gpt-4o-mini`, temperature 0. Two full runs, identical results, $0.005.

```
passed 12  failed 0  unmeasured 0

false-reassurance rate: 0.0%  (0 of 12 measured)
  unnecessary abstentions: 0
  by risk:       HIGH 0/8   MEDIUM 0/4
  by capability: DocumentClassifier 0/9   TravelRecordExtractor 0/3

gate: PASS
```

## What changed in the prompt

v1 described each category and buried the qualifier inside the description:

```
IMMIGRATION_STATUS  Proof of settled status, indefinite leave to remain, or
                    indefinite leave to enter. Home Office or UKVI correspondence
                    confirming a grant of status.
```

The words *"confirming a grant of status"* were already there, and the classifier still
called a letter saying "no decision has been made" an IMMIGRATION_STATUS document. **A
qualifier inside a description is not a condition a reader has to check.**

v2 gives every category an explicit CONDITION, states up front that *"subject matter is
not the test"*, and enumerates the non-grants that fail the immigration condition —
acknowledgements, document requests, fee confirmations, appointments, deferrals,
refusals. For the two test categories it names the difficulty directly: both report
results, a document reporting only an outcome identifies neither, and choosing between
them on layout or on which is more common is forbidden.

It also closes with the consequence, because the consequence is the argument: a letter
misread as a grant of status is sent to be searched for a grant date it does not contain,
and the nearest date on the page will be something else.

## The measurement is attributable

Between the 18.2% run and this one, **the two failing documents did not change.** Same
bytes, same fixtures, same model, same temperature. Only the prompt moved. That is a
cleaner attribution than the travel-extractor case, where re-running under the old prompt
showed the fixture had been the whole cause.

## The held-out fixture is why 0.0% means something here

v2 was written against `classifier_unsupported_ukvi_acknowledgement_001`. That fixture
passing proves only that the prompt addresses the example it was written for — which is
what prompt tuning always achieves and why a re-measured pass rate is so easy to
misread.

`classifier_unsupported_withdrawn_application_001` was added to answer the question the
other fixture cannot. It is Home Office correspondence about indefinite leave that grants
nothing, reaching that state by a route **v2 does not enumerate**: the applicant withdrew
it. Deliberately not a refusal, because v2 names refusals and a refusal fixture would only
check whether the model can read a list back.

It passes. So the condition generalises at least once, on a case the prompt does not
mention. One held-out case is not a generalisation guarantee — it is the difference
between a measurement and a hope.

## No over-abstention, which was the risk

A prompt pushing this hard toward UNSUPPORTED and AMBIGUOUS could easily buy abstention by
making the classifier refuse everything, and the rate would fall while the product got
worse. Two things say it did not:

- `unnecessary abstentions: 0`, the counterweight the metric publishes for exactly this.
- `classifier_travel_ambiguous_dates_001` still returns TRAVEL_SUPPORT. That fixture is
  the AI_SPIKE_FINDINGS §3.2 regression guard: when the date-ambiguity rule sat in the
  shared prompt block, this classifier answered AMBIGUOUS three runs out of three for a
  document that is plainly a travel booking. A travel booking whose dates are ambiguous is
  still a travel booking, and v2 keeps saying so.

All four clean-category fixtures also still pass.

## Reading 0.0%

**Twelve measurements, two identical runs.** Better than the nine of two runs ago and
still a baseline rather than a threshold. What it now says: on twelve fixtures — including
two prompt-injection cases, an ambiguous-date extraction, two abstention cases and one
held-out abstention case — no output was wrong without signalling it.

`classify_document.v1` stays on disk and in `PromptVersion`. Every `ModelRun` from the
first three runs records it, and a version resolving to different text than when recorded
is a dangling provenance claim.

Still outside the denominator: `DocumentClaimExtractor`'s three fixtures, because the
capability is unbuilt. 15 fixtures authored, 12 measurable.
