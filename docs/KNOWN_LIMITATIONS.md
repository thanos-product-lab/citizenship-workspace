# Known limitations

What the product does not do yet, and why each gap was left open.

Every entry here was a decision, not an oversight. Some are gaps worth closing, some are
boundaries that should stay, and one is closed. Code and tests cite entries by number, so
the numbers never change, even when an entry closes.

**If you read one entry, read entry 1.** The product checks a document's dates against your
trips, and nothing else. That same gap is why immigration status documents are never read
(entry 6) and why the AI tests have no wrong-name case (entry 14).

## At a glance

| # | Limitation | Status |
|---|---|---|
| 1 | Only dates are cross-checked, though names and destinations are read | Open, highest priority |
| 2 | Guidance links carry no version or retrieval date | Open, waits for the guidance registry |
| 3 | Invalidation asks the current rule version, not the one that produced the result | Covered bluntly |
| 4 | A document can only support a fact through a trip | By design for now |
| 5 | There is no preparation summary (the travel list part exists) | Partly built |
| 6 | Immigration status documents are classified but never read | Held back, because of entry 1 |
| 7 | A document cannot be replaced, only deleted and uploaded again | Not built |
| 8 | Duplicate detection does not look outside the case | By design, will not change |
| 9 | JavaScript inside a PDF is allowed to run in the preview | Accepted, with limits |
| 10 | A document that will never be read looks like one being read | Partly fixed |
| 11 | A saved application date was believed after it had passed | **Closed** |
| 12 | The phase and the issue list can seem to disagree | Cosmetic |
| 13 | A duplicate issue names the other document by name, not by id | Open |
| 14 | The AI tests leave out the cases most likely to mislead | Open, stated in the report |
| 15 | Speed and cost are recorded but not reported | Open |
| 16 | Monitoring is logs only | Open |
| 17 | Cases deleted before 13 September 2026 are never purged | Open, none on this deployment |
| 18 | The demo case can be replayed but not reset | Partly built |
| 19 | One screen's narrow layout was checked by reading the CSS, not by looking | Needs one manual check |
| 20 | Page headings could be better for screen readers | Defect fixed, better option not taken |

---

## Trust and provenance

### 1. Only dates are cross-checked, though names and destinations are read

**Status:** open, and the first thing worth building next · **Affects:** travel conflicts,
English-language and Life in the UK certificates

**The gap.** When a document is attached to a trip, the conflict check compares two things
only: the departure date and the return date (`TRAVEL_DATE_CLAIM_TYPES`). The model also
reads names and destinations, and a user can confirm them into facts, but nothing compares
them with the rest of the case.

Two things follow from that one gap:

- Attach an Italy booking to a trip recorded as Greece, and the product only says the dates
  differ. It read "Rome" and never compared it with "Greece".
- A certificate in someone else's name, confirmed by a user who was not looking closely,
  becomes a trusted fact. Nothing compares a name on a document with the applicant.

This is a false-reassurance risk, which CLAUDE.md §2.7 treats as the most important thing
to get right.

**Why the AI does not catch it.** The model is deliberately told nothing about the case,
only the document's text. A model that knows whose case it is reading can be led by that.
The comparison belongs after extraction, in ordinary tested code, like every other rule.
That design is right and stays.

**Why there is no test fixture for it.** A wrong-name fixture would grade a check that does
not exist, so it could only ever fail. The fixture and the check belong in the same change
(see `evaluations/EVAL_REPORT.md` §3 and §4).

**Closing it** takes a mapping from each claim type to the case value it should agree with,
an issue type for each kind of mismatch, rule dependencies so a confirmed mismatch marks the
affected results out of date (ADR-0014), and the matching eval fixtures.

---

### 2. Guidance links carry no version or retrieval date

**Status:** waits for the guidance registry · **Affects:** every requirement detail

Each requirement links to the guidance it relies on, but not to a particular revision of it.
The API returns `guidance_version_recorded: false` and the screen says so, rather than
showing a blank.

The alternative was to show the rule's own start date as if it were a retrieval date. Made
up provenance is the worst thing this product could ship, so the gap is stated instead.

**Closing it** needs the `GuidanceVersion` tables that come with the guidance registry.

---

### 3. Invalidation asks the current rule version, not the one that produced the result

**Status:** covered bluntly, not closed · **Related:** ADR-0014, ADR-0022

When an input changes, the product asks the *current* rule version which inputs it reads,
to decide which results are now out of date. If a newer version stopped reading an input
the older one read, a result from the older version could miss that change and stay current
while no longer true.

This used to be impossible because every rule had one version. Four now have more than one.
What covers it today is ADR-0022: switching to a new rule version marks every result the old
version produced out of date. That is correct, and it over-fires on purpose.

**Closing it** means looking up dependencies through the rule version recorded on each
result (`AssessmentResult.rule_version_id`). It belongs with the guidance and rule set work.

---

### 4. A document can only support a fact through a trip

**Status:** by design for now · **Related:** ADR-0021

A document can be attached to a trip, and a fact confirmed from a document is linked to it.
There is no way for a user to say "this document supports that fact" in general.

The rule that reads evidence coverage already works for any kind of link, so it needs no
change when more kinds exist.

**Closing it** is a product decision first: which facts are worth evidencing on their own,
and what happens when one document supports two of them.

---

## Not built

### 5. There is no preparation summary

**Status:** partly built · **Related:** the last step of the demo journey

The demo journey ends with a summary page that has no screen yet. Everything it would show
already exists on the requirement pages. What is missing is one page that brings it together
and prints well.

**One part exists.** The travel list (ADR-0035) is the summary's travel section: the trips in
the qualifying period, printable and as a CSV, reached from Case data.

It was planned after the core build (M10) and never started, so **closing it** is a
project of its own, not a fix.

---

### 6. Immigration status documents are classified but never read

**Status:** held back because of entry 1 · **Related:** ADR-0029

Three of the four document categories work end to end. Immigration status documents are
recognised and stored, but no values are proposed from them.

The reason is entry 1 again. These documents hold the date of birth, status type and grant
date, which the user already typed at the start. Nothing compares a confirmed fact with those
answers, so a document with a different grant date would sit silently beside the typed one.
Shipping the extractor without that check would add a known false-reassurance path.

Its eval fixture stays in place, and the runner shows it as **NOT RUN** so an unbuilt
capability cannot pass by being absent.

**Closing it** needs a check that raises an issue when a confirmed fact disagrees with the
route profile answers.

---

### 7. A document cannot be replaced, only deleted and uploaded again

**Status:** not built

Deleting a document removes its file, withdraws its claims and removes the support it gave.
For a corrected booking that is roughly right. For a clearer scan of the same document it
is wrong: the user loses their review work.

**Closing it** means a second file version under the same evidence item, which the schema
already allows, and a decision about claims confirmed against the old file. That decision is
the hard part.

---

## Deliberate boundaries

### 8. Duplicate detection does not look outside the case

**Status:** by design, will not change · **Related:** Domain §15

The same document uploaded twice into one case is caught. Across two cases it is not. A
file's checksum is a fingerprint, and checking it against other people's cases would reveal
that a file exists in someone else's case. Recorded so that "we decided against it" is not
mistaken for "we did not think of it".

---

### 9. JavaScript inside a PDF is allowed to run in the preview

**Status:** accepted, with limits · **Related:** ADR-0026

The review screen shows the user's document in the browser's PDF viewer, and a PDF can carry
JavaScript. Sandboxing the frame was tried, and with it the PDF does not render at all. The
choice was a working preview or none, on the screen where people check what the model read.

What limits it: the frame may only load from the storage origin, plugins are blocked,
documents come from a private bucket through short-lived links, and a file is only shown
inline after the worker has confirmed its type.

**Closing it** means rendering documents with PDF.js instead of the browser viewer.

---

## Things that can mislead a user

### 10. A document that will never be read looks like one being read

**Status:** partly fixed, 23 September 2026 · **Affects:** every upload

**Fixed:** a new upload gets a card that follows it on screen (Uploaded, Reading document,
then the outcome), and the upload form sits behind Add document (commit `6330301`).

**Still open:** if reading never starts, for example because the worker is down, the card
says "Reading document…" and the row says "Not read yet" forever. A document read in fifteen
seconds and one that will never be read look the same, and silence that could mean
"working" or "broken" is exactly what the product exists to avoid.

**Why not redirect to the review screen after upload?** Reading is asynchronous, so there is
nothing to review yet. Redirecting later would move the page under the user, which WCAG
advises against, and would fight uploading several documents in a row.

**Closing it** needs a timeout that says when nothing has happened for too long. The retry
control already exists for a run that failed. What is missing is any signal for a run that
never began. Whether the row updates live or on refresh decides the size of the work, because
live updates touch polling (ADR-0020).

---

### 12. The phase and the issue list can seem to disagree

**Status:** cosmetic · **Found:** M6 slice 2

The header can say "Resolving issues" while the issue list says "Nothing needs your
attention". Both are right: the phase comes from requirement results (ADR-0009), and a
requirement that is not currently satisfied is a result, not an issue (ADR-0014). Side by
side it still reads like a contradiction.

**Closing it** is a wording or grouping change, not a model change.

---

### 13. A duplicate issue names the other document by name, not by id

**Status:** open · **Related:** ADR-0023

A duplicate-document issue stores the other document's name, not its id. So the issue cannot
follow a rename, and deleting the other document has to find it by matching the name.

**Closing it** means storing `other_item_id` and looking the name up when showing the issue,
as provenance already does everywhere else.

---

## Measurement and operations

### 14. The AI tests leave out the cases most likely to mislead

**Status:** open, stated in the report · **See:** `evaluations/EVAL_REPORT.md` §3

The false-reassurance rate is 0% across 16 test documents. Nine of the twelve required test
cases are covered. The three missing are **poor scan**, **wrong applicant name** and
**partial extraction**.

Those gaps are not random. A bad scan or a missing page is exactly when a model is most
likely to guess instead of abstaining. So the 0% is a real result about clear documents only.
Wrong applicant name waits on entry 1.

---

### 15. Speed and cost are recorded but not reported

**Status:** open

Every model call records its latency and estimated cost. Over 98 calls in the release audit:
median 927ms, 95th percentile 2837ms, $0.0169 in total. The eval harness reports none of it,
nor per-field precision and recall, conflict precision and recall, or citation validity.

**Closing it** is reporting on data already collected. Today the suite proves the safety
property but cannot tell you whether a model change made things worse.

---

### 16. Monitoring is logs only

**Status:** gap against the planned stack

CLAUDE.md §3 names OpenTelemetry and Sentry, and neither is installed. What exists is
structured logging with a trace id that follows a request into the worker. A failure in the
deployed app is found by reading logs, and one nobody is reading for is not found at all.

**Closing it** is two integrations, both kept to the same rule as the logs: no document text
or personal data.

---

## Deletion and the demo

### 17. Cases deleted before 13 September 2026 are never purged

**Status:** open, and none exist on this deployment

Before the purge worker shipped (ADR-0030), deleting a case hid it and blocked writes but
left its data in place. The deletion events were marked as sent at the time, and nothing
resends a sent event, so shipping the worker did not pick them up. This happened once in
development and that case was purged by hand.

**Closing it** is a one-off task, not a migration: list the cases still marked
`DELETION_PENDING`, have a person check the list, then resend one deletion event for each.
A migration that resends events could resend the wrong ones, and this destroys data.

---

### 18. The demo case can be replayed but not reset

**Status:** partly built · **Affects:** the deployed demo

Seeding always gives the same figures, but running it again creates a second case instead of
replacing the first, and on the deployed app it needs console access. A reviewer cannot reset
the demo themselves.

**Closing it** means a reset limited to synthetic cases. Domain §51.3 requires that it never
works on a real case.

---

## Not verified by anybody yet

### 19. One screen's narrow layout was checked by reading the CSS, not by looking

**Status:** needs one manual check · **See:** `design/DESIGN_SYSTEM_FOUNDATIONS.md` §12

Every screen was measured at 320px and 640px except the document review screen, because its
embedded PDF broke the measuring tool. Its CSS collapses to one full-width column well before
those widths, so it should not overflow. That is a deduction, not an observation.

**Closing it** is one look at that screen in a narrow window.

---

### 20. Page headings could be better for screen readers

**Status:** defect fixed, better option not taken

The requirement page used to have two top-level headings. It now has one, matching the other
pages. The better option is to make each page's subject its top heading rather than the case
name, so a screen reader user jumping to it lands on what the page is about. That touches six
pages and their tests, and no WCAG criterion requires it, so it was left.

---

## Resolved

Closed entries keep their numbers because code and tests cite them.

### 11. A saved application date was believed after it had passed

**Status:** **closed**, 22 September 2026, commits `0c18a65` and `a8e5313` (ADR-0032) ·
**Found:** M8 gate walkthrough

A past application date gave results against a five-year window that had already ended, with
recent travel silently outside it. Two halves, both closed:

- **Choosing a past date.** Only the date field blocked it, and the API accepted a past date.
  Now the command refuses it (`APPLICATION_DATE_IN_PAST`, 422). This is not a schema rule,
  because that would reject stored dates that simply aged. A stored date that has passed still
  reads back.
- **A saved date that passes.** The overview and requirement pages work out at read time
  whether the date has passed (`application_date_has_passed`) and show a notice asking for a
  new one. This entry first proposed a limitation computed at assessment time, and ADR-0032
  rejected it before it was built. The result stays true of its window, so it is not a
  limitation on the result.
  What changed is whether that window is still the one the applicant means, and a check at
  assessment time would never reach a case nobody recalculates. No rule change, no migration,
  no scheduled job (`DETERMINISTIC_RULES_SPEC.md` §4.0).
