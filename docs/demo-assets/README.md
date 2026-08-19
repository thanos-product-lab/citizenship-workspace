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
  blocking action, and it ends there: the requirements list and the editable inputs are
  their own destinations now. The derived phase is a quiet chip beside the case title, not
  the heading — context, not the answer to "where do I stand". The header above the
  navigation carries identity, metadata, currency and Recalculate on every destination.
  No percentage, no fraction, no ratio, no score anywhere. See
  `docs/design/CASE_OVERVIEW_REDESIGN.md` and the information-architecture brief beside it.
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
