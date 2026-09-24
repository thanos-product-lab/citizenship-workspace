# Known limitations

What this product does not do, and why each gap was left rather than closed.

A limitation stated plainly reads as a judgement someone made. The same gap discovered by
a reader reads as an oversight. Everything here was a decision, so everything here says
who decided, when, and what closing it would take.

Two things this list is not. It is not a backlog, because several entries are deliberate
and would be wrong to close. And it is not a list of defects: a defect is behaviour that
contradicts what the product claims, and those get fixed rather than recorded.

Twenty entries, grouped by kind. Each names what is missing, why it was left, and what
closing it would take. Closed entries move to **Resolved** at the end and keep their numbers,
because code and tests cite them by number.

**One of them runs through four others.** Entry 1 is that the product cross checks dates
and nothing else. It is also the reason immigration status documents are never read (6),
the reason the evaluation corpus has no wrong applicant fixture (14), and the shape of the
defect a walkthrough found when an Italy booking was attached to a trip to Greece. If you
read one entry, read that one.

## Trust and provenance

### 1. Only dates are cross-checked, though names and destinations are read

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
extracted, stored as a claim, and confirmable into a `FactVersion`. None of it is ever
checked against anything the case already says.

**Two observable consequences, which look unrelated and are the same gap.**

Attach an Italy booking to a trip recorded as Greece, with dates a year apart, and the
product says only *"A document you attached gives different dates."* `Journey.destination`
**is** extracted and `ClaimType.TRAVEL_DESTINATION` exists. The model read "Rome", it
became a claim, and nothing compared it to "Greece". The one mismatch the product notices
is the one it happens to compare.

An English-language certificate in somebody else's name, confirmed by a user who was not
looking, becomes a trusted fact supporting a requirement. `EnglishLanguageExtractor` and
`LifeInUkExtractor` both extract `candidate_name`; `ImmigrationStatusExtractor` would
extract `holder_name`. Nothing anywhere compares a confirmed name to the applicant.

#### Why the capabilities cannot notice this themselves

`AI_EVALUATION_PLAN.md` §8.9 already anticipated it, and its wording is the reason it was
never built: a mismatch signal is expected *"where the capability has case identity
context"*. **No capability has one, deliberately.** The classifier and the extractors are
given the document's text and nothing about the case. That is the same reasoning that
withholds the filename, and the reason the misleading filename criterion is met
structurally rather than by a fixture.

That is the right design and it should not change. A model told whose case it is reading
for is a model that can be led by it. The comparison belongs *after* extraction, in
deterministic code, where it can be tested. That is where every other threshold and
boundary in this product already lives.

#### Why the eval corpus has no fixture for it

`CLAUDE.md` §9 lists "wrong applicant name" among the twelve required fixture classes, and
`EVAL_REPORT.md` §3 records it as a gap. It is not a corpus gap. **Adding the fixture
without the check would grade a behaviour that does not exist**, and a fixture that can
only ever fail measures the absence of a feature rather than the quality of a model. The
fixture and the check belong in the same slice.

#### What closing it takes

A comparison surface wider than two date claim types: a mapping from claim type to the
case value it should agree with, one issue type per kind of disagreement, rule-dependency
declarations so a confirmed mismatch stales the conclusions that read it (ADR-0014), and
eval fixtures for wrong-name and wrong-destination once there is something to grade.

It is a new capability and the release slice does not build new capabilities, which is why
it is written down here instead. It is also, on the evidence of two independent
discoveries in two days, the first thing worth building after the release.

---

### 2. Guidance citations carry no version or retrieval date

**Status:** deferred to the guidance registry (M9) · **Affects:** every requirement detail

MVP §8.8 wants a guidance version and a retrieval date on every source link. Every rule view
the API returns carries `guidance_version_recorded: false`, and the screen says so in as many
words rather than leaving the field blank.

That was the choice: state that the value is not recorded, or fill it with the rule's own
`effective_from` dressed up as a retrieval date. Fabricated provenance is the worst defect
this product could ship, so the gap is declared instead of hidden.

**Closing it** needs the `GuidanceVersion` tables, which arrive with the guidance registry.
Until then a reader can see which guidance a rule cites, but not which revision of it.

---

### 3. Invalidation reads the active rule version, not the one that produced the result

**Status:** mitigated bluntly, not closed · **Related:** ADR-0014, ADR-0022

Dependency resolution asks the *currently active* rule version what inputs it reads. If a v2
drops a dependency that v1 declared, a change to that input would miss a v1-produced result,
which would stay `CURRENT` while no longer being true. That is a stale result returned as
current, which CLAUDE.md §9 lists as an invariant.

ADR-0014 recorded this as unreachable because every requirement had exactly one rule version.
**That is no longer the case.** Four requirements now carry more than one, with the earlier
versions retired: `residence.total_absences`, `residence.final_year_absences`,
`residence.physical_presence_start_date` and `residence.travel_consistency`, which is on its
fourth.

What covers it today is ADR-0022 rather than ADR-0014's original reasoning: activating a new
rule version marks every result the old one produced `STALE` with
`stale_reason_code = 'RULE_VERSION_CHANGED'`. That is correct and deliberately over fires,
staling results whose dependencies did not change at all.

**Closing it** means joining declared dependencies to `AssessmentResult.rule_version_id` so
invalidation asks the version that actually produced the result. It belongs with the guidance
and rule set work, because that is when rule versions start changing for reasons other than a
defect.

---

### 4. A fact can only be evidenced through a travel record

**Status:** by design for now · **Related:** ADR-0021

`EvidenceTravelLink` attaches a document to a travel record. `FactEvidenceLink` exists and
joins the graph beside it, but there is no path for a user to say "this document corroborates
this fact" in general. Evidence coverage is therefore answerable for trips and for facts a
confirmed claim produced, and not for anything else.

The rule that reads coverage is already worded to abstract over link kinds, so it asks the
same question of more edges the day more edges exist. Nothing has to change in the rule.

**Closing it** is a product decision before an engineering one: which facts are worth
evidencing separately, and what a user does with a document that supports two of them.

---

## Not built

### 5. There is no preparation summary

**Status:** not built · **Related:** MVP §14 step 15, M10

The last of the fifteen demo steps has no screen. Every figure it would show already exists
on the requirement pages: what each requirement concluded, the facts behind it, what is still
outstanding. What is missing is the assembly of them into one readable page, and a print
layout.

It sits in M10, outside the M0 to M8 plan of record, so this is a scope decision rather than
an oversight. **Closing it** is a milestone rather than a fix, and the roadmap's cut list puts
the print layout last within it.

**One part now exists.** The travel list (ADR-0035) is the summary's "travel summary": the
trips in the qualifying period, printable and as a CSV, reached from Case data. The rest of
the summary, and the page assembling it, does not.

---

### 6. Immigration status documents are classified but never read

**Status:** deferred, and the reason is entry 1 · **Related:** ADR-0029

Three of the four supported categories go end to end. Immigration status documents are
classified correctly, stored, and readable, and no values are proposed from them.

**The reason is worth reading, because it is entry 1 again.** Such a document proposes
`date_of_birth`, `status_type` and `status_granted_on`, which are the same three answers the
user typed at onboarding into their route profile. Nothing compares a confirmed fact to the
route profile. So a document stating a grant date that contradicts what the user typed would
produce a confirmed fact sitting silently beside a contradicting profile answer, with no
surface comparing them and no issue raised.

That is the same defect class as the travel conflict that took a whole slice to build.
Shipping the extractor without the comparison would knowingly add a false reassurance path,
so the capability was held back instead.

Its evaluation fixture stays in the manifest, with ground truth written before any model ran,
and the runner prints it as **NOT RUN** rather than letting an unbuilt capability pass by
absence.

**Closing it** needs fact versus route profile conflict detection first. That is a derivation
rather than a table: raise an issue when a case level fact gains a version whose value differs
from its predecessor's and whose evidence link names a different document.

---

### 7. A document cannot be replaced, only deleted and uploaded again

**Status:** not built

There is no replace path in `app/evidence/service.py`. Correcting a document means deleting
it and uploading the new one, which destroys the original bytes, invalidates its claims, and
withdraws the support it gave any fact.

For a corrected booking that is roughly the right behaviour, because the old document really
is wrong. It is the wrong behaviour for a better scan of the same document, where the user
wanted the same evidence more legibly and lost their review work instead.

**Closing it** means a second `EvidenceFile` version under the same `EvidenceItem`, which the
schema already allows, plus a decision about what happens to claims confirmed against the
previous version. That decision is the hard half.

---

## Deliberate boundaries

### 8. Duplicate detection does not look outside the case

**Status:** by design · **Related:** Domain §15

The same document uploaded twice into one case is detected. The same document uploaded into
two different cases is not, and will not be.

That is a boundary rather than an omission. Matching across cases means reading another user's
rows to answer a question nobody asked, and a checksum is a fingerprint: confirming that a
specific file exists in someone else's case is exactly the disclosure a private bucket exists
to prevent.

**Not for closing.** Recorded so that "we did not think of it" and "we decided against it"
stay distinguishable.

---

### 9. Embedded JavaScript in a PDF is accepted rather than sandboxed

**Status:** accepted, measured · **Related:** ADR-0026

The review screen frames the user's document. A PDF can carry JavaScript, and it runs.

`sandbox` on the iframe was measured and is not a mitigation here: with the attribute the
viewer is blocked entirely and the PDF does not render, for every token combination tried. So
the choice was a preview that works or no preview at all, and the product's central screen is
one where a person reads a document while confirming what a model read out of it.

What bounds it instead: a strict `frame-src` naming only the bucket origin, `object-src
'none'`, documents served only from a private bucket through short lived signed URLs, and
inline disposition withheld until the worker has confirmed the bytes are the type they
claimed. **Closing it** properly means rendering the document with PDF.js rather than the
browser viewer, which is a real slice.

---

## Things that can mislead a user

### 10. A document being read looks exactly like a document that will never be read

**Status:** **partly closed**, 23 September 2026 · found at the M8 gate, confirmed again by
the release-slice walkthrough
**Affects:** the Evidence destination, every upload

**What changed.** The first half below is fixed: a new upload now gets a card on screen that
follows it (Uploaded, then Reading document, then its real outcome), and the library leads
the page with the upload form behind Add document (commit `6330301`). **The worse half is
not:** a run that never starts still reads "Reading document…" on that card and "Not read
yet" on the row, indefinitely, with no timeout. The text below is the entry as it was
recorded; its failure-path paragraph and "What closing it takes" still stand.

Uploading announces *"Uploading …"* and then *"… uploaded. Reading will start shortly."*
into an `aria-live` region that is `cw-visually-hidden`. **Nothing appears on screen.**
Reading then takes around twenty seconds, during which the screen says nothing at all.

The comment beside that third message already conceded it before anyone tested it: *"this
third copy was missed, and it is the only one no sighted user ever sees."*

**The worse half is the failure path.** With the worker stopped, an uploaded document sits
at *"Uploaded · Not read yet"* indefinitely, with no elapsed time, no progress, and no
eventual "this has not started". A document that will be read in fifteen seconds and a
document that will never be read are indistinguishable. That is the shape the whole
product exists to prevent: silence meaning *working* and silence meaning *broken* look
identical, and an unchanging row implies "your document is being read".

The release-slice walkthrough added a third observation: **on a small screen even the row
is below the fold**, so the only signal is off-screen in both senses at once.

#### Why the obvious fix was declined

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

#### What closing it takes

A visible in-progress state rather than an announced-only one; a legible reading state for
those twenty seconds; and a timeout that says so when nothing has happened for long
enough. `RETRYABLE_STATUSES` and the retry control already exist for a *failed* run. What
has no surface at all is a run that never began.

One open question decides the size of the work: **whether the row updates live or only on
refetch.** Live means touching the polling cadence, and ADR-0020 deferred SSE behind
polling deliberately; refetch-only makes it a copy change. That question is why this is its
own slice rather than a gate-buffer fix.

---

### 12. The phase chip and the issue queue can look like they disagree

**Status:** logged, cosmetic · **Found:** M6 slice 2

The header can read "Resolving issues" while the issue queue reads "Nothing needs your
attention". Both are correct and they measure different things. The phase derives from
requirement conclusions (ADR-0009), and a requirement that is `NOT_CURRENTLY_SATISFIED` is a
requirement outcome, deliberately not an issue (ADR-0014).

Side by side it reads as a contradiction, which is a cost the product should not pay on a
screen about trust. **Closing it** is a copy or grouping change, not a model change.

---

### 13. A duplicate issue names its twin by name, not by id

**Status:** known gap · **Related:** ADR-0023

`DUPLICATE_EVIDENCE` stores the other document's `display_name` in the issue's message
parameters. The sibling was never recorded as an identifier, so the issue cannot follow a
rename, and a purge has to clear the name out of the twin's row by matching on the string.

**Closing it** means storing `other_item_id` and resolving the name at render time, which is
what provenance already does everywhere else. It was left because it changes the shape of a
rendered issue, and a purge slice should not be reaching that far.

---

## Measurement and operations

### 14. The evaluation corpus omits the cases most likely to produce a false reassurance

**Status:** measured and stated · **See:** `evaluations/EVAL_REPORT.md` §3

The false reassurance rate is 0.0%, over 16 measured fixtures. Of the twelve fixture classes
CLAUDE.md §9 requires, nine are covered. The three that are not are **poor scan**, **wrong
applicant name** and **partial extraction**.

Those are not randomly distributed. A degraded scan and a document missing the page the value
is on are the two conditions under which a model is most likely to fill a gap confidently
rather than abstain. A zero measured over legible documents is a real result about legible
documents.

Wrong applicant name is a different case and belongs with entry 1: the check it would grade
does not exist, so the fixture would measure the absence of a feature.

---

### 15. Latency and cost are recorded but not reported

**Status:** measurement exists, reporting does not

Every provider call writes `latency_ms` and `estimated_cost_usd` to `model_runs`. Measured
over 98 successful runs during the release audit: p50 927ms, p95 2837ms, max 3051ms, $0.0169
in total.

The evaluation harness does not surface any of it. Neither does it produce per field precision
and recall, conflict precision and recall, or citation validity, all of which the evaluation
plan names.

**Closing it** is reporting work on data already collected. It is the difference between a
suite that proves a safety property, which this one does, and a suite that can tell you
whether a model change made things worse, which it cannot yet.

---

### 16. Observability is structured logs and nothing else

**Status:** gap against the documented stack

`CLAUDE.md` §3 names OpenTelemetry and Sentry. Neither is a dependency. What exists is
structlog with a trace id bound per request and carried into worker tasks, which is genuinely
useful for following one document through the pipeline and is not distributed tracing or error
aggregation.

The practical consequence is that a failure in the deployed environment is found by reading
logs, and a failure nobody is reading logs for is not found at all. The M7 incident where a
worker reported itself healthy for fifteen minutes is the shape of what this does not catch.

**Closing it** is two integrations, and both need care about what they are allowed to capture:
the same rules that keep document text out of logs apply to spans and to error payloads.

---

## Deletion and the demo

### 17. Cases deleted before the purge consumer shipped will never be purged

**Status:** outstanding, and bounded to deletions requested before 13 September 2026
**Affects:** any deployment carrying `DELETION_PENDING` cases from before that date

`CaseDeletionRequested` had no consumer until the release slice (ADR-0030). A case deleted
before then went to `DELETION_PENDING`, stopped accepting writes, vanished from every read,
and its rows and objects stayed where they were.

Shipping the consumer does not retrieve them. The relay is at-least-once over *unpublished*
rows, and those outbox rows were marked published at the time by a relay that dispatched
nothing. Nothing revisits a published row, so the work was not delayed; it was dropped.

**This is not hypothetical.** It happened during development on 13 September: the first
live purge ran against a worker image that predated the fix, the event was marked published
having been declined, and the case had to be purged by hand afterwards.

#### What closing it takes

Finding the `DELETION_PENDING` cases and re-emitting one `CaseDeletionRequested` per case.
Deliberately **not** done as a migration: a migration that re-emits events is a migration
that can re-emit the wrong ones, and this destroys user content. It is a one-off operational
task against a known, countable set (`SELECT id FROM cases WHERE lifecycle_status =
'DELETION_PENDING'`), and it should be run by a person who has read the list first.

On this deployment that set is currently empty, because the only case it ever contained was
the development one purged by hand.

---

### 18. The synthetic case can be replayed but not reset

**Status:** partial · **Affects:** the deployed demo

Seeding is one command and produces identical figures every time, so the demo is replayable.
It is not resettable: running the seed again creates a *second* case rather than replacing the
first, and there is no endpoint that restores a case to its seeded state.

On the deployed environment seeding also needs console access to the API container, so a
reviewer cannot reset the demo themselves.

**Closing it** means a reset command scoped to synthetic cases only. Domain §51.3 already
draws that line: a demo reset is a separate operation from user deletion and must never be
available for a real case.

---

## Not verified by anybody yet

### 19. The review split view is the one screen whose reflow was never measured

**Status:** verified by reading rather than by looking · **See:** `security/ACCESSIBILITY_PASS.md`

Every other destination was measured at 320px and at 640px by loading it in a frame of that
width, which is a genuine viewport because media queries evaluate against the frame. Six
were clean and one, the Evidence page, was not; that overflow is fixed.

The review split view could not be probed. It embeds the user's document in an iframe, so a
probe frame puts a PDF viewer two levels deep and the renderer detaches every time.

Verified from its CSS instead, which handles this case deliberately: `minmax(0, 1fr)` with a
comment naming this exact failure, a `60rem` breakpoint that collapses to one column well
before either test width, and `width: 100%` on the frame. A single full-width column cannot
overflow, so the deduction is sound. It is still a deduction.

**Closing it** means one manual look at that screen on a narrow window, which takes a minute
and needs a person.

---

### 20. The requirement detail's heading levels moved, and the wider question is open

**Status:** the defect is fixed, the better option was not taken

The requirement detail rendered two level one headings, the case title and the requirement
title. It now renders the requirement title as `h2` and the explanation stack's layers as
`h3`, which matches every other destination.

The option not taken is the more correct one. The case title is persistent chrome in a
banner, so arguably each destination's subject should be the `h1`: the overview's readiness
headline, the timeline's title, the requirement's name. As it stands, a screen reader user
jumping by level one always lands on the case name and never on what the page is about.

Rejected on cost rather than on principle. It touches six destinations and their tests,
which is a refactor rather than a fix, and no success criterion requires it.

---

## Resolved

Entries that are closed keep their numbers, because code and tests cite them by number.
Each says what closed it; the reasoning stays, because the way a gap was closed is often the
useful part.

### 11. A saved application date is believed after it has passed

**Status:** **closed**, 22 September 2026, by commits `0c18a65` and `a8e5313` (ADR-0032) ·
**Found:** M8 gate walkthrough

Setting an application date in the past produced every requirement green against a five year
window that had already closed, with the last months of travel silently outside it. That is
the false reassurance shape the product exists to prevent.

A *new* bad selection cannot be made. It does nothing for a saved date that drifts into the
past, which happens to every case eventually, including the seeded demo case when April 2027
arrives.

**This entry used to say the date field closed the first half, and that was wrong.** The
field's `min` attribute was the whole enforcement, and `POST /application-dates/select`
accepted 15 January 2020 with a 200, found in the September 2026 walkthrough (fixed in
commit `0c18a65`). A control that lives only in a React component is not a control. The command now
raises `ApplicationDateInPast` (422, `APPLICATION_DATE_IN_PAST`), so the first half is closed
by the product rather than by the browser.

**Still deliberately not fixed with schema validation.** A `ge=today` rule would reject cases
nobody touched, purely because time passed, and would break on a calendar boundary rather than
a code change. The guard is on the *command* for exactly that reason: it only ever fires on a
date somebody is choosing right now, and a stored date that has since passed still reads back
(`test_a_date_that_drifted_into_the_past_is_still_read_back`).

**The remaining half is closed too, and not the way this entry said.** It proposed a derived
limitation computed at assessment time. ADR-0032 rejected that before building it, for the
reason this entry had not accounted for and then for a better one.

The one this entry missed: staleness is event-driven, so a limitation computed when the
assessment runs would never reach a case nobody recalculates — the case it exists to protect.

The better one: a `Limitation` reduces confidence in a *result*, and no result's confidence
changes here. "451 days across 16 April 2022 to 15 April 2027" stays true of that window
permanently. What changes is whether that window is still the one the applicant means, which
is a fact about the case today, not about the run. Typing it as a limitation is what created
the staleness problem in the first place.

So it is **derived at read time**, like the case phase (ADR-0009): `application_date_has_passed`
on the overview and the requirement detail, with a notice naming the date and offering a new
one. No rule change, no migration, no scheduled job. `DETERMINISTIC_RULES_SPEC.md` §4.0 now
states that the rules do not constrain the date and that its passing is a read-model
condition rather than a rule outcome.
