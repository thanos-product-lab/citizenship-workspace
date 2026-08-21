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
