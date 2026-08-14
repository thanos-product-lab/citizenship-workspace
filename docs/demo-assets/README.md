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
`just edit-trip` (see the recipes in `justfile`). Replace these with UI recordings at M4.
