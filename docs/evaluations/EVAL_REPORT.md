# AI evaluation report

**Status:** current as of 13 September 2026 · covers runs from 10–11 September 2026
**Headline:** false-reassurance rate **0.0% — 0 of 16 measured fixtures**, over a corpus
that omits three of the classes most likely to produce one.

Read the second half of that sentence. It is the more useful number.

Per-run detail lives in `EVAL_RESULTS_<date>.md`; this is the summary a reader should
start from. The plan the suite implements is `AI_EVALUATION_PLAN.md`.

---

## 1. What false-reassurance rate means here

The share of measured fixtures where the model produced a **confident wrong answer** — a
value or a category that a person could act on, that is not what the document says.

It is deliberately not `1 − pass rate`. A model that abstains more often has a *worse*
pass rate and a *better* false-reassurance rate, and those must not be the same number:
one of those changes is a safety improvement and the other is not. Abstentions are
counted and published separately (**unnecessary abstentions: 0**) for the same reason —
a false-reassurance rate falling while abstentions climb is a model getting quieter, not
safer, and one number cannot say so.

Directive §2.7 is why this is the headline metric: stopping is a successful outcome.

## 2. The measurement

Provider OpenAI, `gpt-4o-mini`, temperature 0. Five capabilities, 17 fixtures, of which
16 are measured — `ImmigrationStatusExtractor` has a fixture and no implementation
(ADR-0029), and reports `NOT RUN` rather than passing by absence.

| | measured | false reassurances |
|---|---|---|
| DocumentClassifier | 9 | 0 |
| TravelRecordExtractor | 3 | 0 |
| EnglishLanguageExtractor | 2 | 0 |
| LifeInUkExtractor | 2 | 0 |
| ImmigrationStatusExtractor | 0 (not built) | — |
| **Total** | **16** | **0 (0.0%)** |

By risk: HIGH 0/9, MEDIUM 0/7. Gate: **PASS**. Cost across the milestone's runs: about
$0.01.

## 3. What the corpus does not cover

`CLAUDE.md` §9 names twelve fixture classes. Measuring them honestly:

| Class | State | Where |
|---|---|---|
| Clear document | **Covered** | 14 `clean` fixtures |
| Unsupported document | **Covered** | 2 fixtures, one held out |
| Conflicting date | **Covered** | `travel_amended_return_001` |
| Multiple dates on one page | **Covered** | 9 fixtures |
| Prompt-injection text | **Covered** | 3 fixtures, one per extractor family |
| Misleading filename | **Covered structurally** | The filename is never sent to any model. `test_the_filename_is_never_sent` pins it. A guarantee by omission beats a fixture that can only ever observe the model resisting a temptation it was not offered. |
| Duplicate evidence | **Covered deterministically** | Checksum and near-duplicate detection (M7 slice 4b) is arithmetic, not model behaviour — pytest, not evals. |
| Model refusal | **Covered, not by evals** | `test_a_refusal_stops_immediately` — a refusal is treated as a verdict, not an error. |
| Malformed output | **Covered, not by evals** | Structured outputs are schema-validated at the provider boundary; `tests/ai/test_provider_retries.py`. |
| **Poor scan** | **GAP** | No degraded-quality document exists in the corpus. |
| **Wrong applicant name** | **GAP, and wider than the corpus** | See §4. |
| **Partial extraction** | **WEAK** | One classifier fixture is tagged `partial`. No extractor-side fixture exercises a document missing the page the value is on. |

So: nine of twelve covered, two gaps, one weak — and the two gaps are **not** randomly
distributed. A poor scan and a partial document are the two conditions under which a
model is most likely to fill a gap confidently rather than abstain, which is the exact
behaviour this metric exists to catch. A 0.0% measured over a corpus of legible documents
is a real result about legible documents.

## 4. The gap that is not an eval gap

`AI_EVALUATION_PLAN.md` §8.9 expects a mismatch signal "where the capability has case
identity context". **No capability has one**, deliberately: the classifier and the
extractors are given the document's text and nothing about the case — the same reasoning
that withholds the filename.

The consequence is downstream and is a product limitation rather than a model one.
`EnglishLanguageExtractor` and `LifeInUkExtractor` extract `candidate_name`, and
`ImmigrationStatusExtractor` would extract `holder_name`. Those become claims a user can
confirm into `FactVersion`s. **Nothing anywhere compares a confirmed name to the
applicant.** An English certificate belonging to someone else, confirmed by a user who
was not looking, becomes a trusted fact supporting a requirement, and no surface says so.

Adding the fixture without the check would grade a behaviour that does not exist. Both
belong in the same slice; recorded in `KNOWN_LIMITATIONS.md`.

## 5. Metrics the plan asks for and this suite does not produce

`CLAUDE.md` §9 and `AI_EVALUATION_PLAN.md` §§1022–1030 name more than the rate above.
What is not measured:

- **P50/P95 latency** — not recorded per fixture. The only latency figure anywhere is the
  deployed smoke's single AI probe.
- **Field precision/recall, per class** — the harness grades a fixture pass/fail against
  expected values and forbidden strings; it does not accumulate per-field counts.
- **Conflict precision/recall** and **citation validity** — no fixture population large
  enough to make either meaningful.
- **Cost per document** — cost is recorded per run by hand, not per fixture.

None of these blocks the release. All of them are the difference between "this suite
proves a safety property" (it does) and "this suite is a regression instrument for model
changes" (it is not yet).

## 6. Four instrument defects, and why they are the strongest result here

Across four runs, **four apparent model failures were defects in the evaluation itself**:

| Run | Looked like | Actually |
|---|---|---|
| 10 Sep, 1st | Model invented a date from `03/04/2025` | The fixture said "6 nights", resolving the ambiguity it was written to preserve |
| 10 Sep, 3rd | Classifier forced `LIFE_IN_THE_UK` on a bare result slip | The fixture was titled "TEST RESULT NOTIFICATION" and echoed Life-in-the-UK phrasing |
| 11 Sep | Extractor returned `TRINITY COLLEGE LONDON` | The fixture expected title case — a normalisation nobody asked the model to perform |
| 11 Sep | *(nothing — it passed)* | The injection fixture graded no authority channel at all |

The fourth is the one to read. The fixture forbade a forced CEFR level and an issue date,
but its document also said *"approved and confirmed at the highest level"* — and
`EnglishLanguageExtraction` has two free-text fields where a model could echo that. The
assertion that would have caught it **existed and was deleted** while "generalising" a
test. That is the instrument being loosened to accommodate the thing it measures, by the
person who built it. Both halves are fixed and the assertion is restored alongside a new
verbatim check rather than instead of it.

A corrected measurement does not delete the measurement it corrects: every run above is
kept, including the two that failed the gate at 11.1% and 18.2%.

## 7. Reproducing

```bash
just eval           # generates fixture documents, then runs the suite
```

Without `--run` the runner checks only that the manifests are coherent and calls no
model. The full suite is **not** run per commit — it costs money and the deterministic
product does not depend on it.
