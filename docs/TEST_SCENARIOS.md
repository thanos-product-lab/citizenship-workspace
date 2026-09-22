# End to end test scenarios

Manual scenarios for driving the whole product. Each has steps, an expected result, and
what a failure would mean.

**Read this first.** The M8 gate found three defects in minutes, and all three were
unreachable on the seeded case, because `just seed` creates a case that is already active,
already has an application date and already has twelve trips. **Scenario 1 is the most
valuable one here.** Do not skip it because it looks like setup.

Some scenarios are expected to look broken. Those are marked **documented limitation** and
name the entry in `KNOWN_LIMITATIONS.md`. If one of them behaves *better* than described,
that is also a finding: the document is out of date.

**Write down what you find.** Defects found by running these go in
`SCENARIO_FINDINGS.md`, one section per scenario, not in `KNOWN_LIMITATIONS.md`, which is
for gaps that were decided rather than discovered.

## Setup

```bash
just up                    # postgres, redis, minio, api, worker
just dev                   # web on :3000
cd services/platform && uv run python -m scripts.make_fixtures          # test documents
cd services/platform && uv run python evals/fixtures/make_documents.py  # eval documents
```

Sign in at `http://localhost:3000/sign-in`. The root path returns 404 to a cold tab, which
is the Clerk dev instance and not a bug.

**Check which API is answering before you start.**

```bash
lsof -nP -iTCP:8000 -sTCP:LISTEN
```

`just up` starts an `api` container and `just api` runs a local `uvicorn --reload`, and both
bind port 8000. The local one picks up a source change; the container does not — it has no
`--reload` and no source volume, so it serves whatever was baked into its image. With both
running, which one answers the browser is not yours to choose, and the symptom is a code
change that appears to do nothing. Run one of them, not both.

Test documents land in `services/platform/tests/fixtures/documents/`. They are gitignored,
so generate them before starting.

Reference data for the scenarios below:

| | |
|---|---|
| Absent days for a trip | strictly between departure and return, so `return - departure - 1`. A trip out on the 4th back on the 10th is 5 days. |
| Total absences bands | 0 to 420 supported · 421 to 450 near threshold · 451 to 480 requires judgement · 481 to 900 professional review · over 900 not satisfied |
| Final year bands | 0 to 75 supported · 76 to 90 near threshold · 91 to 100 requires judgement · 101 to 179 professional review · 180 or more not satisfied |
| Supported statuses | ILR, indefinite leave to enter, EU settled status |
| Upload limits | 20 MB, PDF or JPEG, checked by magic bytes rather than by the declared type |

---

## 1. A case built from nothing

**Why:** every automated check and most walkthroughs use the seeded case. This is the path a
real user takes and the one where defects have actually hidden.

1. **Your cases** then create a case.
2. Answer onboarding: date of birth **14 March 1990**, status **ILR**, granted
   **1 March 2020**, not a spouse-route application, no chance of already being British.
   Confirm.
3. Land on the overview.

**Expected:** the case activates. The overview says nothing has been assessed yet and shows
a **Start here** list of three steps: set an application date, add your travel history, then
open **Requirements** and choose **Run assessment**.

Check the last step names Requirements, not the header. The header's Update assessment button
is hidden until a case has been assessed once, and this list only appears while nothing has
been — so a step pointing "above" was naming a control guaranteed to be absent
(`SCENARIO_FINDINGS.md` finding 1).

**A failure here means** the empty state has regressed to a dead end, which is what it was
before the release slice.

**Not checkable here: "the step disappears once a date exists".** An earlier version of this
scenario said so, and it passed for the wrong reason — the whole list disappears, because
saving a date also recalculates. To see the two-step list you need a date with nothing
assessed, which the web form never produces: select a date through the API without
recalculating, or have a recalculation fail. Covered by `CaseOverviewPanel.test.tsx`, which
names both routes.

4. Case data, set the application date to **30 June 2027**. The control should read **Save
   this date**, not Preview.

**Expected:** it saves directly. Before the release slice a new case could not be given a
first date at all, because the only control was Preview and a preview needs a date to
compare against.

5. Check the date field will not offer a past date.
6. Add a trip: **France, out 10 August 2023, back 20 August 2023**. When you set the
   departure, the return field should already hold the same date, so the picker opens in
   2023 rather than today.
7. Add a second trip: **Spain, out 1 June 2027, back 5 June 2027**.
8. Recalculate.

**Expected:** total absences **12 days**, supported. Final year absences **3 days**,
supported. Presence on the first day supported, because no trip covers 1 July 2022. Age and
holding period supported.

The qualifying period is **1 July 2022 to 30 June 2027**: five years ending on the
application date, starting the day after the same date five years earlier.

---

## 2. The three ways a case is stopped

**Why:** unsupported routes must stop before any assessment is created.

Create a case for each and confirm onboarding.

| Answer | Expected |
|---|---|
| Spouse or civil partner of a British citizen: **yes** | Unsupported. The case stays in draft and is never activated. |
| Status: **Other** | Unsupported, not currently satisfied. Stays in draft. |
| Any chance you are already British: **yes** | Requires review, requires judgement. Stays in draft. |
| Status: **I'm not sure** | **Needs an answer**, not evaluated, not yet assessed. Stays in draft, and nothing on screen says "not supported". |

The fourth is the one to watch. "I'm not sure" is an answer the form offers, and it used to
come back as *"Please answer immigration status before confirming"* — a refusal of a question
that had been answered, with no way out but to claim a status. Getting it wrong in the other
direction is worse: an unsure applicant told their status is **not supported** is a
definitive negative drawn from missing data. Check the words, not only the outcome.

**A failure here means** an unsupported applicant reached the residence engine, which is the
one thing the onboarding gate exists to prevent.

---

## 3. The bands, by moving one date

**Why:** it demonstrates that the thresholds are real and that a conclusion is not a guess.

Use a freshly seeded case (`just seed <your-clerk-user-id>`).

0. A new seed is **not assessed**. Open Requirements and choose **Run assessment**. The
   header's Update assessment button does not exist yet, which is why this step names a
   different control. Confirm the case now reads **439 days, near threshold**.
1. Note the Spain trip: out 1 February 2026, back 25 March 2026, contributing 51 days.
2. Edit its return date to **6 April 2026**, making it 63 days.
3. Recalculate.

**Expected:** total absences **451 days**, and the conclusion moves from near threshold to
**requires judgement**. 439 minus 51 plus 63.

Requires judgement rather than not satisfied is the point: 451 is over the guidance figure
and inside the range where the Home Office may exercise discretion, so the product escalates
instead of refusing.

4. Open the requirement and read the calculation. It should name the records it counted.

**Why this trip and not trip 11.** An earlier version of this scenario extended trip 11
(Italy, 4 to 10 May 2026) to 22 May and expected 451. That is wrong. Trip 12 is the United
States, 16 to 29 May 2026, so the extended Italy trip overlaps it, and absent days are the
**cardinality of a union**, not a sum (`DETERMINISTIC_RULES_SPEC.md` §173). The five shared
days, 17 to 21 May, are counted once. The real answer is **446**, and two
`OVERLAPPING_TRAVEL` issues are raised. The Spain trip has no neighbour, so its 12 extra
days land whole. See `SCENARIO_FINDINGS.md` finding 4.

---

## 4. Evidence, end to end

1. Evidence, upload `evals/fixtures/travel/italy_booking_amended_return.pdf`.
2. File it under the **wrong** document type, for instance Immigration status.

**Expected:** the row shows your category and, separately, **"Analysis suggests: Travel
booking"**. The machine's reading is shown beside yours rather than replacing it.

3. Wait for **Values proposed**, then follow **Confirm what we read**.

**Documented limitation 10:** for about twenty seconds nothing on screen changes. A document
being read and a document that will never be read look identical. Expected, and recorded.

4. On the review screen, check the return date field is **empty**. The document says 11 May
   2026 and the model read it, and the value is not on the page.
5. Type `11/05/2026`.

**Expected:** refused, with a message bound to the field naming an acceptable shape. It must
not contain a usable date.

6. Type `11 May 2026` and save.

**Expected:** badge reads **Confirmed**.

7. Confirm the remaining fields, then return to the Evidence library.

**Expected:** the row now offers **See what we read**, not "Confirm what we read". Before the
release slice the link disappeared entirely and the reading became unreachable.

---

## 5. The conflict, and what it moves

**Why:** this is the product's central claim, end to end.

1. From Case data, attach the amended booking to **trip 11** (Italy, 4 to 10 May 2026).
2. Confirm its return date as **11 May 2026**, which disagrees with the trip.

**Expected on the Case data table:** the trip shows **Dates disputed**, not plain
"Confirmed".

**Expected on Requirements:** `residence.total_absences` reads **434 confirmed days**. The
disputed trip is held back entirely rather than counted, so 439 minus its 5 days.

**Expected on the Timeline:** also 434. The two surfaces must agree. They disagreed once, and
the timeline reported the more reassuring figure on the more prominent screen.

3. Open the requirement detail.

**Expected:** the disputed trip is named as not counting, and the fact that caused it appears
under Facts used.

4. Go to **Issues**. The conflict appears there, naming both dates and the document. Press
   **Use the dates from the document**, then Recalculate.

Adopting stales the residence conclusions rather than recalculating them, so the two steps
are separate and the case is genuinely stale in between.

**Expected:** **440 days**, because the trip is now 4 to 11 May, which is 6 days. All three
runs stay readable in assessment history with the rule version that produced each.

The arc across this scenario is **439, then 434, then 440**, and every figure is
inspectable afterwards.

---

## 6. Stale, and what does not go stale

1. On the seeded case, edit trip 11's return date.

**Expected:** exactly **four** conclusions go stale. `residence.qualifying_period` does not,
because it reads only the application date.

2. Check a stale requirement.

**Expected:** it shows its conclusion **and** a stale marker at once, for instance Supported
beside Stale. The conclusion is not rewritten into something false.

3. Issues should show one item per stale conclusion, grouped under **Recheck your
   conclusions**.
4. Press **Recheck now**.

**Expected:** all of them resolve together and move to Settled with their history kept.
5. Edit again.

**Expected:** the same rows reopen, each marked as having come back, rather than appearing as
first occurrences.

---

## 7. Deletion

**Delete a document**

1. Delete a document attached to a trip.

**Expected:** the confirmation dialog names the document and states the consequences before
you act. On confirming, the phase chip moves, a stale banner appears and Issues increases,
all at once.

**Expected on Requirements:** `residence.travel_consistency` shows **Supported and Stale**
together, while the absence totals stay Supported with no stale marker. Deleting a document
reaches only the rule that declares a dependency on evidence.

**Delete a case**

2. Create a throwaway case, add a trip, upload a document, then delete the case.

**Expected:** it disappears from your list immediately and, within a few seconds, the worker
purges it. This completes now; before the release slice the rows and objects stayed for ever.

3. Verify properly:

```bash
docker exec citizenship-workspace-postgres-1 psql -U citizenship -d citizenship -tAc \
  "SELECT lifecycle_status, title, owner_user_id FROM cases WHERE id='<case-id>';"
```

**Expected:** `DELETED`, with an empty title and an empty owner. The tombstone records that a
deletion happened, not whose.

---

## 8. Failure paths

The gate rule: break one thing deliberately and watch what a user sees.

**Worker stopped**

```bash
docker compose stop worker
```

1. Upload a document.

**Expected, and documented limitation 10:** it sits at "Uploaded, not read yet" indefinitely.
No elapsed time, no progress, no eventual "this has not started". This is the most serious
open gap in the product. Restart the worker and the document proceeds.

```bash
docker compose start worker
```

**API stopped**

2. With the API stopped, press Recalculate.

**Expected:** a visible failure that survives a reload, not a toast. The copy should say
nothing changed without claiming the run did or did not happen.

**Storage stopped**

3. With MinIO stopped, try to upload.

**Expected:** a clear refusal rather than a silent failure.

---

## 9. Documents that should be refused or handled carefully

Upload each from `services/platform/tests/fixtures/documents/`.

| File | Expected |
|---|---|
| `not-really-a-pdf.pdf` | Refused as unsupported, with a reason. The declared type is a PDF and the bytes are not, and the magic bytes decide. |
| `empty.pdf` | Refused or reported as having nothing to read. Never silently accepted. |
| `password-protected.pdf` | Refused with a reason, not a crash. |
| `scan-no-text-layer.pdf` | Accepted, with the text pane saying there is nothing to read and pointing at the document view. It must not invent content. |
| `prompt-injection.pdf` | The instructions in it must not change anything. Values are still proposed, still require confirmation, and nothing is auto-confirmed. |
| `many-pages.pdf` | Handled, with a note if the character cap stopped the read. |
| A file over 20 MB | Refused by the store rather than by the API, because the limit is a condition in the signed upload policy. |

---

## 10. Accessibility spot checks

1. **Keyboard only, no mouse.** From the top of any case page, press Tab once.

**Expected:** a **Skip to main content** link appears. Activating it moves focus into the
page content, so the next Tab does not return you to the navigation.

2. Tab through the overview, requirements and evidence. Every control should show a visible
   focus ring, and focus order should match visual order.
3. Open the delete dialog with the keyboard. Focus should land on **Cancel**, Tab should
   cycle inside the dialog, and Escape should close it.
4. **Narrow window.** Resize to about 320px wide.

**Expected:** no sideways scrolling on any destination. A table may scroll inside itself.

5. **Greyscale.** Apply a greyscale filter, or use a monochrome display setting.

**Expected:** every status is still readable, because each carries a glyph and a word rather
than a colour.

---

## 11. Things that should look wrong, and are documented

Confirm each behaves as described. A surprise here means the documentation is stale.

| Check | Expected behaviour | Entry |
|---|---|---|
| Attach a document for the wrong country to a trip, for instance the Italy booking on a trip to Greece | Only the **date** disagreement is reported. The destination mismatch is not detected. | 1 |
| Open any requirement and look at Rule used | It states that no guidance version was recorded, rather than showing one | 2 |
| Upload an immigration status document | Classified correctly, and no values are proposed from it | 6 |
| Try to replace a document | There is no replace. Delete and upload again. | 7 |
| Upload the same document to two different cases | Not detected as a duplicate. Within one case it is. | 8 |
| Set an application date, then imagine time passing it | A saved date that drifts into the past is still believed. Only new selections are blocked. | 11 |
| Compare the phase chip with the issue queue | They can read as contradictory while both being correct | 12 |

---

## Recording what you find

For anything unexpected, note the case id, the URL, what you did, what you expected and what
happened. If it is a new defect rather than a documented limitation, the useful question is
the one the M8 gate asked: **why did no test catch this?** The answer is usually that the
test used the seeded case, or the happy path, or asserted the defect.
