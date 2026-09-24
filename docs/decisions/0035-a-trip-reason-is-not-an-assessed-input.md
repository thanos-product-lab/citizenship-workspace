# ADR-0035: A trip's reason is not an assessed input, and the travel list lists every trip

**Status:** Accepted, 24 September 2026
**Amends:** Domain RFC §11.1 and §11.8, and adds §11.10
**Partly closes:** KNOWN_LIMITATIONS 5 (the travel summary part of the preparation summary)

## Context

An applicant with more trips than the online form has room for uploads the full list at the
documents step. The workspace held every trip but could not give them back in that shape, and
had no field for the "Reason for trip" such a list carries.

Two things had to be decided: where the reason lives, and which trips the list includes.

## Decision

**The reason lives on the stable `TravelRecord`, not on the immutable version.** A travel
version is an assessed input: appending one stales every result declaring a travel dependency
(ADR-0014), eight of them on the canonical case. No rule reads a reason. On the version,
typing reasons for forty trips would stale the assessment forty times over trips whose dates
never moved. That would make "Update assessment" a reflex, and stale warnings that fire for
nothing are how stale warnings stop being read.

**An edit that changes no version field appends no version and stales nothing.** Every field
a rule can read is a version field, so "no version field changed" is exactly "nothing an
assessment depends on changed". The results stay current because they are still true. It
also stops an unchanged save of the trip form staling results, which it previously did.
`version_matches` is the one comparison, and a property test holds both halves: the same
fields always match, and a change to any version field never does.

**Omitting the reason on an edit keeps it; `null` or blank clears it.** The edit is a whole
snapshot of the version, and a client that predates the field must not erase one.

**The list includes every active trip in the period, and marks the ones the assessment would
not count.** On a list handed to the Home Office, leaving a trip out is the dangerous
direction: an under-declared history is false reassurance in its plainest form (CLAUDE.md
§2.7). The marks come from the trips `gather_trips` produces, with the conflict overlay, so the
list and the assessment agree about which trips are held back (ADR-0028):

- **Dates disputed by a document:** a confirmed document date disagrees with the trip.
- **Not confirmed:** the trip is a draft or marked uncertain.
- **Dates estimated:** the dates were estimated or unknown.

An `ExtractedClaim` is never a trip, so a value proposed by a document and never confirmed
cannot appear (directive 1). If documents are waiting for review, the page says they may hold
trips not listed yet.

**A trip is in the period when its calendar dates overlap it**, not when it has counted days
in it. A same-day trip, or one returning on the period's first day, counts zero days
(RULES_SPEC §5) and is still a trip the form asks about.

**The CSV is shaped like the form's table, not like the import.** It uses these columns:
Country visited, Reason for trip, Departure date, Return date and Note. Dates are ISO,
because `04/05/2023` is two different days depending on who opens the file. Any cell
starting with `=`, `+`, `-`, `@`, tab or carriage return is prefixed with an apostrophe,
because a destination or reason is user text that a spreadsheet would otherwise run
(OWASP CSV injection). A UTF-8 byte-order mark leads, for Excel.

**The PDF is the browser's.** A print stylesheet drops the case shell and controls, repeats
the table header on every page and keeps each trip on one page. The MVP asks for a printable
layout (§8.14), and a server-side PDF library would be a dependency for nothing a browser
does not already do.

**The list names no product and claims no check.** It says it was prepared from the
applicant's own records, and carries no day counts, which a caseworker could read as official.

## Consequences

- A reason's earlier values are not kept. Its changes are audited (that it changed, never the
  text). This is acceptable for text that no conclusion rests on.
- The first `@media print` rules in the design system. Later print layouts (the rest of the
  preparation summary) start from them.
- The case shell hides on print everywhere, which is right for any page printed from the
  workspace.

## Rejected

- **The reason on the version.** Correct history, and a stale assessment for every word typed.
- **A reason edit that appends a version but skips invalidation.** The current results would
  then reference a superseded version, breaking "every current trusted assessment references
  current relevant input versions".
- **Confirmed trips only.** A shorter, cleaner list that under-declares.
- **Reusing the import's CSV columns for round-tripping.** Machine headings on a file meant
  for a caseworker. The import accepts a `reason` column, which is the half of round-tripping
  that matters.
- **A server-generated PDF (WeasyPrint or similar).** A new dependency and a rendering stack
  to secure, for what the print dialog already produces.
