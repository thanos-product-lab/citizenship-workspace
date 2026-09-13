# Known limitations

What this product does not do, and why each gap was left rather than closed.

A limitation stated plainly reads as a judgement someone made. The same gap discovered by
a reader reads as an oversight. Everything here was a decision, so everything here says
who decided, when, and what closing it would take.

Two things this list is not. It is not a backlog — several entries are deliberate and
would be wrong to close. And it is not a list of defects: a defect is behaviour that
contradicts what the product claims, and those get fixed rather than recorded.

> **In progress.** Three entries so far, from the release-slice walkthrough and
> ADR-0030. The remaining
> deferrals from M0–M8 — the guidance version and retrieval date (MVP §8.8),
> `ImmigrationStatusExtractor`, evidence replacement, SSE behind polling, rule-version
> dependency resolution (ADR-0014, ADR-0022), corroborating `FactEvidenceLink`s,
> cross-case duplicate detection, the tombstone purge reach (ADR-0023), embedded PDF
> JavaScript (ADR-0026), the preparation summary, and the rest — are still to be written
> up here.

---

## 1. A document being read looks exactly like a document that will never be read

**Status:** outstanding · found at the M8 gate, confirmed again by the release-slice
walkthrough
**Affects:** the Evidence destination, every upload

Uploading announces *"Uploading …"* and then *"… uploaded. Reading will start shortly."*
into an `aria-live` region that is `cw-visually-hidden`. **Nothing appears on screen.**
Reading then takes around twenty seconds, during which the screen says nothing at all.

The comment beside that third message already conceded it before anyone tested it: *"this
third copy was missed, and it is the only one no sighted user ever sees."*

**The worse half is the failure path.** With the worker stopped, an uploaded document sits
at *"Uploaded · Not read yet"* indefinitely — no elapsed time, no progress, and no
eventual "this has not started". A document that will be read in fifteen seconds and a
document that will never be read are indistinguishable. That is the shape the whole
product exists to prevent: silence meaning *working* and silence meaning *broken* look
identical, and an unchanging row implies "your document is being read".

The release-slice walkthrough added a third observation: **on a small screen even the row
is below the fold**, so the only signal is off-screen in both senses at once.

### Why the obvious fix was declined

Redirecting to `/review` after upload was proposed and rejected, and the reasoning is
worth keeping because the instinct is a common one:

- Processing is asynchronous, so redirecting on upload success arrives at a review screen
  before any claim exists.
- Redirecting *later*, when the worker finishes, moves the page under someone seconds
  after they acted. WCAG 2.2 3.2.x wants context changes on request.
- Uploading several documents in a row is the ordinary case, and a redirect after each one
  fights it.
- The library is a queue. Every row carries its own state, and a redirect is the shape for
  synchronous work.

The absent review link at `UPLOADED` is likewise **correct** and stays: nothing has been
read, so a link would open a review screen with no claims on it. "There is no way to reach
/review, add a link" would paper over the real problem with a worse one.

### What closing it takes

A visible in-progress state rather than an announced-only one; a legible reading state for
those twenty seconds; and a timeout that says so when nothing has happened for long
enough. `RETRYABLE_STATUSES` and the retry control already exist for a *failed* run — what
has no surface at all is a run that never began.

One open question decides the size of the work: **whether the row updates live or only on
refetch.** Live means touching the polling cadence, and ADR-0020 deferred SSE behind
polling deliberately; refetch-only makes it a copy change. That question is why this is its
own slice rather than a gate-buffer fix.

---

## 2. Only dates are cross-checked, though names and destinations are read

**Status:** outstanding · found by the release-slice walkthrough and, independently, while
writing `evaluations/EVAL_REPORT.md`
**Affects:** travel conflicts, English-language and Life-in-the-UK certificates
**Severity:** this is a false-reassurance shape, which directive §2.7 treats as the most
important thing to get right

The conflict detector compares exactly two things:

```python
TRAVEL_DATE_CLAIM_TYPES: dict[str, str] = {
    "travel.departure_date": "departure_date",
    "travel.return_date": "return_date",
}
```

That is the entire comparison surface in the product. Everything else a model reads is
extracted, stored as a claim, confirmable into a `FactVersion` — and never checked against
anything the case already says.

**Two observable consequences, which look unrelated and are the same gap.**

Attach an Italy booking to a trip recorded as Greece, with dates a year apart, and the
product says only *"A document you attached gives different dates."* `Journey.destination`
**is** extracted and `ClaimType.TRAVEL_DESTINATION` exists — the model read "Rome", it
became a claim, and nothing compared it to "Greece". The one mismatch the product notices
is the one it happens to compare.

An English-language certificate in somebody else's name, confirmed by a user who was not
looking, becomes a trusted fact supporting a requirement. `EnglishLanguageExtractor` and
`LifeInUkExtractor` both extract `candidate_name`; `ImmigrationStatusExtractor` would
extract `holder_name`. Nothing anywhere compares a confirmed name to the applicant.

### Why the capabilities cannot notice this themselves

`AI_EVALUATION_PLAN.md` §8.9 already anticipated it, and its wording is the reason it was
never built: a mismatch signal is expected *"where the capability has case identity
context"*. **No capability has one, deliberately.** The classifier and the extractors are
given the document's text and nothing about the case — the same reasoning that withholds
the filename, and the reason the misleading-filename criterion is met structurally rather
than by a fixture.

That is the right design and it should not change. A model told whose case it is reading
for is a model that can be led by it. The comparison belongs *after* extraction, in
deterministic code, where it can be tested — which is where every other threshold and
boundary in this product already lives.

### Why the eval corpus has no fixture for it

`CLAUDE.md` §9 lists "wrong applicant name" among the twelve required fixture classes, and
`EVAL_REPORT.md` §3 records it as a gap. It is not a corpus gap. **Adding the fixture
without the check would grade a behaviour that does not exist**, and a fixture that can
only ever fail measures the absence of a feature rather than the quality of a model. The
fixture and the check belong in the same slice.

### What closing it takes

A comparison surface wider than two date claim types: a mapping from claim type to the
case value it should agree with, one issue type per kind of disagreement, rule-dependency
declarations so a confirmed mismatch stales the conclusions that read it (ADR-0014), and
eval fixtures for wrong-name and wrong-destination once there is something to grade.

It is a new capability and the release slice does not build new capabilities, which is why
it is written down here instead. It is also, on the evidence of two independent
discoveries in two days, the first thing worth building after the release.

---

## 3. Cases deleted before the purge consumer shipped will never be purged

**Status:** outstanding, and bounded — it can only affect deletions requested before
13 September 2026
**Affects:** any deployment carrying `DELETION_PENDING` cases from before that date

`CaseDeletionRequested` had no consumer until the release slice (ADR-0030). A case deleted
before then went to `DELETION_PENDING`, stopped accepting writes, vanished from every read
— and its rows and objects stayed where they were.

Shipping the consumer does not retrieve them. The relay is at-least-once over *unpublished*
rows, and those outbox rows were marked published at the time by a relay that dispatched
nothing. Nothing revisits a published row, so the work was not delayed; it was dropped.

**This is not hypothetical.** It happened during development on 13 September: the first
live purge ran against a worker image that predated the fix, the event was marked published
having been declined, and the case had to be purged by hand afterwards.

### What closing it takes

Finding the `DELETION_PENDING` cases and re-emitting one `CaseDeletionRequested` per case.
Deliberately **not** done as a migration: a migration that re-emits events is a migration
that can re-emit the wrong ones, and this destroys user content. It is a one-off operational
task against a known, countable set — `SELECT id FROM cases WHERE lifecycle_status =
'DELETION_PENDING'` — and it should be run by a person who has read the list first.

On this deployment that set is currently empty, because the only case it ever contained was
the development one purged by hand.
