
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
