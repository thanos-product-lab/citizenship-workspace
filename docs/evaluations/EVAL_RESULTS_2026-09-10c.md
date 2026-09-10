# Eval run — 10 September 2026, third run

Re-measured after adding the two classifier abstention fixtures. Provider: OpenAI,
`gpt-4o-mini`, temperature 0. 33 calls across three runs of the classifier fixtures,
$0.006. The document was edited twice while checking it (see Finding 2) and re-measured
after each edit; the numbers below are from the final version on disk.

```
passed 9  failed 2  unmeasured 0

false-reassurance rate: 18.2%  (2 of 11 measured)
  unnecessary abstentions: 0
  by risk:       HIGH 2/7   MEDIUM 0/4
  by capability: DocumentClassifier 2/8   TravelRecordExtractor 0/3

gate: FAIL
  HIGH-RISK FAILURE  classifier_unsupported_ukvi_acknowledgement_001
                     expected 'UNSUPPORTED', got 'IMMIGRATION_STATUS'
  HIGH-RISK FAILURE  classifier_ambiguous_bare_test_result_001
                     expected 'AMBIGUOUS', got 'ENGLISH_LANGUAGE'
```

## The previous 0.0% was measured over a corpus that never tested refusal

Every classifier fixture before these two expected a real category. `UNSUPPORTED` and
`AMBIGUOUS` — the classifier's entire refusal surface, and the mechanism behind the claim
that *"correct abstention is a success"* — were unmeasured. The headline safety metric had
never been shown the case it exists to measure.

Two fixtures later, the rate is 18.2% and **the classifier does not abstain.** Neither
abstention value is reachable in practice on this corpus.

## Finding 1 — subject matter beats the condition

`classifier_unsupported_ukvi_acknowledgement_001` is UKVI correspondence about indefinite
leave to remain which states, in as many words, *"No decision has been made on your
application."*

`IMMIGRATION_STATUS` is defined in the prompt as *"Home Office or UKVI correspondence
confirming a grant of status."* This document confirms receipt. The model answered
`IMMIGRATION_STATUS` — matching on what the letter is *about* rather than on what it
*confirms*.

**This is the misclassification with teeth.** A document routed to `IMMIGRATION_STATUS`
goes next to a claim extractor looking for a grant date. There is no grant date on the
page. The nearest date is `Received: 18 February 2026`.

The fixture is deliberately not one of the prompt's own `UNSUPPORTED` examples — bank
statement, payslip, tenancy agreement — since a fixture built from one of those tests
whether the model can read its instructions back, which it can.

## Finding 2 — the model guesses, and the guess follows incidental wording

`classifier_ambiguous_bare_test_result_001` is a sparse result slip: candidate, ID, test
date, PASS, centre, invigilator. Nothing states which test. It is either an English
language result or a Life in the UK result, and both are supported categories with their
own extractors, so forcing a choice routes the document to one of two schemas on a coin
toss. The prompt says *"Choose AMBIGUOUS rather than guessing between two categories."*

**The first draft of this document was tilted, and I did not see it.** It was titled
"TEST RESULT NOTIFICATION" and closed with "Keep this notification. A replacement cannot
be issued" — both borrowed, unthinkingly, from the real Life in the UK pass notification,
which is called a notification and warns that no replacement can be issued. The model
answered `LIFE_IN_THE_UK`, and on that wording it had a case.

Retitled `RESULT SLIP` with the replacement line removed, the same model at temperature 0
answered **`ENGLISH_LANGUAGE`**. Same sparse facts, two different confident categories,
the only difference being phrasing that carries no information about which test it was.

One flip is not a controlled experiment, and temperature 0 is not a determinism guarantee
with this provider. But the direction is the point: the tilted wording produced the tilted
answer, and removing it moved the answer rather than producing a refusal. That is what
guessing looks like from the outside.

The document was then edited once more. Stripping those two lines took it to 194
characters, under the corpus's 200-character floor — a guard that exists so a fixture
cannot be a near-empty page, and not one worth lowering to make an edit fit. Two neutral
lines were added instead (a slip reference and a generic confirmation sentence, both
absent from either candidate's real paperwork) and the fixtures were re-measured.
`ENGLISH_LANGUAGE` again. Every edit to an ambiguity fixture needs re-measuring, because
every edit is a chance to lean.

## What this does not tell us

Whether the classifier *can* abstain. Both failures are cases where it should have and
did not; no fixture yet establishes that it ever will. `unnecessary abstentions: 0` is
consistent with a model that never abstains at all, and with the AI_SPIKE_FINDINGS §3.2
observation running the other way — when the date-ambiguity rule sat in the shared prompt
block, this classifier answered `AMBIGUOUS` three times out of three for a document that
was plainly a travel booking. It abstained when it should not have, and now does not when
it should.

That pairing suggests the behaviour is prompt-sensitive rather than absent, which is worth
testing before concluding anything about the model.

## Next

The gate fails on two HIGH-risk fixtures, correctly. The honest options are a
classifier-prompt revision that makes the *conditions* on each category load-bearing
rather than the subject matter — `IMMIGRATION_STATUS` requires a grant, and a test result
requires knowing which test — re-measured against these fixtures, or accepting the
finding as recorded and deciding the classifier's abstention behaviour is out of M8's
scope.

It should not be closed by loosening the fixtures. Both were checked against the prompt's
own definitions before this was written, and one of them was tightened when checking
showed it had been leaning.
