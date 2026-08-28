# Demo assets

Capture a short screen recording and one or two screenshots at the end of each
milestone, while the work is fresh.

`IMPLEMENTATION_ROADMAP.md` §3.6: M12 then edits existing material rather than
reconstructing seven weeks of work from memory.

Naming: `m<N>-<slug>.<ext>`, e.g. `m3b-stale-recalculation.mp4`.

Synthetic data only. Review every asset before it becomes public.

## M3B (Rules and assessments)

M3B is backend-only — the assessment workspace UI is M4 — so its assets are terminal
captures of the dev walkthrough rather than screenshots:

- `m3b-requirements-list.txt` — the nine assessed requirements after recalculate.
- `m3b-total-absences-provenance.txt` — 439 with the application-date + travel-record input links.
- `m3b-presence-resolving-date.txt` — presence fails, resolving date 2027-04-25 offered.
- `m3b-stale-transition.txt` — the edit → STALE → recalc → 440, prior result SUPERSEDED cycle.

Regenerate on a fresh case with `just seed` then `just recalc` / `just inspect` /
`just edit-trip` (see the recipes in `justfile`). Kept alongside the M4 screenshots
rather than replaced: they are the oracle the screens are checked against, and the
figures in both must agree.

## M4 (Explainable case workspace)

The same canonical case, now on screen. Every figure matches the M3B captures above —
that agreement is the point, so check it when regenerating either set.

- `m4-case-overview.jpg` — the Overview destination. It leads with what the reader has to
  do ("1 requirement needs your attention"), then the counts by named state, then the one
  blocking action, then one row per requirement group stating what its members concluded
  in counts of named states and linking through to that group. It ends there: the
  requirements themselves and the editable inputs are their own destinations now. Note
  what the group rows are *not* — `Residence 4 / 5`, which would be a readiness score
  arrived at sideways and would render a reached failure as a missing requirement. The derived phase is a quiet chip beside the case title, not
  the heading — context, not the answer to "where do I stand". The header above the
  navigation carries identity, metadata, currency and Recalculate on every destination.
  No percentage, no fraction, no ratio, no score anywhere. See
  `docs/design/Evidence_First_Citizenship_Workspace_UI_UX.md` §4 and §6.2, and ADR-0012.
- `m4-explanation-stack.jpg` — the signature interaction: "439 confirmed days against a
  threshold of 450", then the calculation naming which records it counted.
- `m4-supported-and-stale.jpg` — the ADR-0001 pair. `Near threshold` beside `Stale` as
  two badges, the conclusion preserved, and the notice naming the input that moved
  ("What changed: Trip to Italy").
- `m4-assessment-history-439-to-440.jpg` — the headline moment. Both runs conclude
  `Near threshold`, so the conclusions alone read as no change; the figure row is what
  makes it legible. The superseded run stays inspectable and is not struck through.

### Regenerating

```bash
just seed <your-clerk-user-id>          # after your last `just test-be`, which truncates
just recalc <case-id> <your-user-id>    # -> 439
# screenshot the overview and the requirement detail
just edit-trip <case-id> 2026-05-04 2026-05-11 <your-user-id>   # -> STALE
# screenshot the stale pair
just recalc <case-id> <your-user-id>    # -> 440, prior run SUPERSEDED
# screenshot the assessment history
```

Captured at 1280px wide. The case detail pages do not render the Clerk user button, so
no real account appears; the visible name is synthetic seed data.

### Still to capture

A short screen recording of the stale → recalculate loop. The four stills carry the
states, but §3.6 asks for a recording per milestone and this one has the motion that
makes the loop legible.


## M6 — Issue Detection and Stale-State Workflow

### Slice 1 — selective invalidation

`m6/m6-slice1-selective-invalidation.gif` — the stale → recalculate loop on the canonical
case, captured in the browser. Trip 11's return moves 10 → 11 May 2026; **four** conclusions
go stale (not five — `residence.qualifying_period` reads only the application date);
Recalculate supersedes them; total absences moves 439 → 440 with both earlier runs still
inspectable and marked Superseded.

This closes the gap M4 carried forward ("no screen recording of the stale → recalculate
loop").

Not captured as stills: the application-date case, where the header reads **8** conclusions
and the Identity-and-status group shows 3 of its 4 requirements stale. Under M3B's blunt rule
that group read entirely CURRENT while the date beneath it had moved — the ADR-0008
under-invalidation window. `route.supported_status` correctly stays current: it reads the
status type, not the date.

### Slice 2 — the issue queue

`m6/m6-slice2-issue-queue.gif` — the lifecycle end to end. A trip edit opens four issues,
one per stale requirement, grouped under "Confirm information". **Recheck now** resolves all
four at once — not through a special case in the recalculation path, but because the
reconciler finds those causes gone — and they move to Settled with their history retained
rather than deleted. A further edit **reopens the same four rows**, each marked "This was
resolved before and has come back", so a recurrence is never shown as a first occurrence.

Note for the walkthrough: the phase pill reads "Resolving issues" while the queue reads
"Nothing needs your attention". Both are correct and they measure different things — the
phase derives from requirement conclusions (ADR-0009), and this case has a requirement that
is `NOT_CURRENTLY_SATISFIED`, which is a requirement outcome and deliberately not an issue
(ADR-0014). Side by side it reads as a contradiction. Logged as a gap.

The group heading in this capture reads "Confirm information", which is what severity alone
produced. It now reads "Recheck your conclusions" — see slice 4.

### Slice 3 — dismissal

`m6/m6-slice3-dismissal.gif` — the only dismissible thing in the product. An uncertain trip
*outside* the qualifying period is INFORMATION and can be set aside; the same uncertainty
inside the period is ACTION_REQUIRED and cannot, because there it is holding a confirmed
total back. Dismiss moves the item to Settled marked **Dismissed**, distinct from the
**Resolved** rows above it — the cause has not gone away, the user has judged this episode
of it. The near-threshold item stays open throughout, which is the contrast the queue exists
to show: items that clear themselves beside one that does not, for a visible reason.

Dismissal is not optimistic. The card is not hidden until the server agrees, because the
server refuses to dismiss anything not marked dismissible — and an optimistic hide would
show the item leaving the queue in exactly the cases where it must not.

### Slice 4 — a failed recalculation, made visible

`m6/m6-slice4-failed-recalculation.gif` — Domain §41.4, captured against a deliberately
broken API (a temporary switch in `_run_trusted_assessment`, removed before commit; the
failure is genuinely exceptional and no fixture can produce it, see `SYNTHETIC_DEMO_CASE`
§10).

Four stale conclusions, one **Recheck now**. The recheck fails: the count goes to **6**, the
control renames to **Try again**, and a `PROCESSING_FAILURE` card appears **above** the stale
items it explains — ordering the cause before its effects, which time alone would invert
since the failure opens last. The copy states that nothing changed without claiming the run
did or did not happen.

Then the reload, which is the whole point: the header's transient alert is gone and the
durable item is still there. Before this slice a failure left *nothing at all* — no run row,
no issue — so a reload erased the only evidence and left stale conclusions with nothing
explaining why they had not refreshed.

The API is repaired mid-recording. **Try again** clears all five: the failure resolves
through the ordinary reconciler diff, because the latest finished run is no longer FAILED.
Settled retains the dismissal from slice 3 alongside them.

Also visible: the group heading now reads "Recheck your conclusions" rather than "Confirm
information". That string labels an `aria-labelledby` region, so a screen-reader user
navigating by landmark was being routed away from the one item explaining why their figures
were stale — an accessibility defect, not only awkward copy.

## M5 (Timeline and application-date simulation)

*Built after M6, per the roadmap's reordering. The same canonical case: 439 days, presence
failing at 16 April 2022, resolving at 25 April 2027.*

### The date simulation

`m5/m5-date-simulation.gif` — the milestone, and the reason ADR-0002 exists.

Two candidate dates, in order. **20 April 2027** first: the whole five-year window slides
to 21 Apr 2022 – 20 Apr 2027, the total drops **439 → 434**, and presence is *still* not
satisfied. That middle frame is the point. A five-day move changed the arithmetic and fixed
nothing, because clearing an absent anchor means moving past the entire trip covering it —
which here is ten days. A mockup once taught that one day was enough, and correcting it is
what ADR-0002 is.

The screen says so rather than leaving it to be inferred: **"Still not satisfied on this
date"**, then the presence row, then the button offering the date that does work. An earlier
version listed only what *changed*, so a user who moved the date to fix presence saw a
shorter absence total and no mention of presence at all — improvement-only reporting, which
is the false reassurance directive §2.7 exists to prevent. Found by using the screen, not by
a test.

Then **25 April 2027**: presence flips `Not currently satisfied → Supported`, the total
settles at **429**, and `Travel record consistency` appears with *identical badges* on both
sides — its entire output is limitations (RULES_SPEC §7.8), and the trip that covered the
anchor is now outside the window. The API could not express that change until the rules
review caught it.

Every conclusion carries the **Preview** badge, and nothing has been written: no run, no
result, no provenance. A simulated result has no field in which to record any, so persisting
one is a type error rather than a guard (Domain §42.2).

### Saving it

`m5/m5-save-and-reassess.gif` — two requests, deliberately: `/select` appends a date version
and marks the dependent results stale, then `/assessments/recalculate` produces the new ones.
The header moves to 25 April, the phase chip changes, the preview closes and focus returns to
the date field. Between the two calls the case is genuinely stale, and if the second fails
that is what the user is left with — which M6's queue already handles honestly.

### The timeline

`m5/m5-timeline-table.png` — the chronological table, built **before** the visual band so
that "semantically equivalent" (UI/UX §15) is checkable rather than aspirational.

The Spain row is why the table exists: **14 April 2022 to 26 April 2022, 10 days**, with
"1 day of this trip falls outside your qualifying period, so 10 days count." The trip is
eleven days long and contributes ten, because the window opens on the 16th — the single most
common reason a user's own arithmetic disagrees with the product's, said in words on the row
rather than left as a discrepancy. "Covers the first day tested" marks the one trip that
decides the presence check.

Three columns, not five. Departure and return are one fact, and a "Record" column reading
`Confirmed` on all twelve rows buried the one row that would not be — only the exception is
flagged.

`m5/m5-timeline-band.png` — the shape, above the table it describes. `aria-hidden`
throughout: every value in it is in the table in words, and a screen reader announcing it
would be reading a second, worse copy. Bars are clipped at the window edges, trips wholly
outside are not drawn, and the trip covering the presence anchor is drawn **taller** than
its neighbours — height rather than an outline, because against the boundary line beside it
an outline alone was indistinguishable.

No charting library: a linear date→x scale over a fixed five-year domain is nine lines, and
D3 would be a dependency (CLAUDE.md §10). Labels are real DOM rather than SVG text, so they
scale with the page instead of the viewBox — SVG text shrinks relative to its surroundings
at 200% zoom, which is the usual way a chart quietly fails the zoom requirement.

### Regenerating

```bash
just seed <your-clerk-user-id>          # after your last `just test-be`, which truncates
just recalc <case-id> <your-user-id>    # -> 439, presence NOT_CURRENTLY_SATISFIED

# the simulation: /cases/<id>/data, set 20/04/2027, Preview this date,
#   then "Preview 25 April 2027 instead", then Save
# the timeline: /cases/<id>/timeline — on a *fresh* case, since saving 25 April moves
#   the window and the Spain row then reads 0 days
```

The figures must agree with the M3B terminal captures and the M4 screens above: 439, 17,
and 2027-04-25. The post-move figures — 429 at 25 April, 434 at 20 April — are recorded in
`SYNTHETIC_DEMO_CASE.md` §8 and asserted in `tests/assessments/test_simulation.py`.

## M7 — Evidence Foundation

Both captured in Chrome against the local stack, on a synthetic case with one trip to
Greece and one attached document. The M7 story is what happens when a document that
*mattered* goes away, so both assets are deletions.

### Slice 5 — deletion, and what it invalidates

`m7/m7-slice5-delete-and-stale.gif` — the chain the milestone exists to demonstrate.

The confirmation dialog names the document and states the consequence **before** the
action: contents destroyed, cannot be undone, the trip it supports will show as having no
document, and the travel-records check will need working out again. That is four sentences
because deletion is the one irreversible thing in the product.

On confirmation the whole case responds at once, in the same transaction: the phase chip
moves from *Building your case* to *Resolving issues*, the stale banner appears, and Issues
goes 0 → 1 — before the bytes are destroyed, which happens asynchronously afterwards.

**The frame that carries the milestone is the requirements list.** *Travel record
consistency* shows **Supported** and **Stale** side by side, with the reason named — "The
documents attached to your travel records changed after this was worked out. This is the
conclusion from before that change; it has not been rechecked." Directly above it, *Total
absences* (39 days) and *Final-year absences* (0 days) are still **Supported** with no stale
marker at all.

Two invariants in one image:

- **Conclusion and currency are separate** (directive 4, ADR-0001). The conclusion was not
  rewritten into something false, and the currency does not pretend nothing happened.
- **Selective invalidation does not over-fire** (ADR-0014). Deleting a document reached
  exactly the one rule that declares a dependency on evidence support. The absence totals
  are computed from dates the user entered, and no document was ever load-bearing for them.

Recheck then closes the loop: the stale issue moves to Settled, and the coverage gap the
deletion created opens as "No document attached to your trip to Greece" — information, not
an action, because *nothing in the assessment depends on it*. That the queue says so in as
many words is the honesty the milestone is for.

### Slice 5 — the failure path

`m7/m7-slice5-failed-deletion.gif` — the API stopped mid-deletion, per the gate's rule that
a walkthrough must deliberately break one thing.

Captured because it was **broken until the accessibility review found it**, and it is the
state nobody looks at. The failure was announced only into a visually-hidden live region, so
a sighted user saw the dialog close, the row still listed, and nothing saying why — a user
believing an irreversible action had succeeded when it had not. The jsdom test asserting
`getByText(/could not be deleted/)` passed against the hidden node, satisfied by exactly the
state its own comment called broken.

What the capture now shows: a visible alert naming the document, saying the row is still
listed and **nothing about the case has changed**. Not in the recording, because focus is
invisible to a screen capture: focus returns to the Delete control that failed, not to the
section heading — the row still exists on this path, so throwing the user to the top of the
section would make them tab past the upload form and the whole table to retry.

### Not captured, and why

The **deletion announcement** is the finding this walkthrough produced and it cannot be
screenshotted: the live region held "Athens booking deleted." for **38 milliseconds** before
the refetched document count overwrote it with "No documents yet.". Measured with a
`MutationObserver` in Chrome, fixed, and re-measured — the sequence is now a single message.
The regression test records the whole sequence rather than the final text, because the final
text was correct even while the bug was live.

The **purge** has no UI by design — the object is gone and the row is a tombstone, so there
is nothing to show. It is verified in `tests/evidence/test_storage_minio.py` against real
MinIO, and was verified against real S3 in production: a presigned URL returning 200
immediately before the deletion answered `NoSuchKey` five seconds after.
