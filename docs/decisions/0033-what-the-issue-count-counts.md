# ADR-0033: What the issue count counts

**Status:** Accepted, 23 September 2026
**Closes:** the issue-count note from the September 2026 manual UX pass (commit `297f256`)
**Amends:** Domain RFC §36.3 (a definition over existing values; no enum changes)

## Context

The case navigation shows a number beside Issues. A user reads it as the answer to "how
much is left for me to do". It was the count of every open issue at every severity.

Two things made that number wrong for the question it answers.

**Notes counted as work.** INFORMATION issues are frequent and are not requests:
`MISSING_EVIDENCE` on every confirmed trip with no document attached, `DUPLICATE_EVIDENCE`,
`DUPLICATE_TRAVEL_RECORD`, and `UNCERTAIN_TRAVEL_DATE` for a trip outside the window. On the
scenario 1 case, six of fourteen open issues were notes of this kind.

**One job counted many times.** A change that stales eight results opens eight
`STALE_ASSESSMENT` issues, one per requirement. One command clears all of them. The badge
said 8, and the Issues page showed eight cards under a single button placed above them.

The command itself also had three names: "Update assessment" in the case header, "Recheck
now" on Issues, and "Run assessment" before the first run.

## Decision

**An action is an open issue that is BLOCKING, ACTION_REQUIRED or REVIEW_REQUIRED, with every
`STALE_ASSESSMENT` and `PROCESSING_FAILURE` together counted as one.** INFORMATION issues are
counted separately as notes for awareness. The rule is `issues.domain.count_actions`, one pure
function used by both the queue (`action_count`, `awareness_count`) and the overview
(`issue_action_count`). The client never recomputes it.

**REVIEW_REQUIRED stays in.** Near-threshold absences, overlapping trips and unsupported
complexity are exactly the items CLAUDE.md §2.7 says must not be under-stated. A smaller
number bought by leaving them out would be the false reassurance the product exists to avoid.

**The recheck issues are presented as one task, and stored as they were.** The queue carries a
`recheck` block: one server-rendered title, body and impact, the list of conclusions it
covers (each linking to its requirement), and the underlying issue views. Those issues are
left out of `groups` so none is shown twice. Nothing about storage changes. ADR-0015 needs
each issue's own identity for resolution history, reopening and dismissal rules, and each
still resolves on its own and appears on its own in the history, now titled
"Total absences: out of date" (a state, where "Recheck Total absences" was a command with no
button beside it). After a failed run the task takes the failure's own sentences and its
button becomes "Try again".

**One label for the one command.** "Update assessment" on Issues as in the header. "Run
assessment" stays only for the first run, where there is nothing yet to update.

**The outcome is visible.** After an update the Issues page says what is left, "Assessment
updated. 1 action remains.", in the same unit as the badge, and keeps saying it until the
next update. Previously it was only announced, and in issues resolved rather than actions.

## Consequences

- The badge can read nothing while notes are open. That is intended: a note is something to
  know, and the page still lists it and says how many there are.
- `open_count` and `open_issue_count` stay, as the plain total. The recheck announcement no
  longer uses them.
- The case phase is unaffected. It still ignores the queue (ADR-0009).

## Rejected

- **Keep counting every open issue** and only regroup the page. Fixes the layout and leaves
  the number the note complained about.
- **Count only BLOCKING and ACTION_REQUIRED.** A smaller number, bought by hiding the review
  items §2.7 protects.
- **Collapse rechecks into one stored issue.** Loses per-requirement history and reopening,
  which ADR-0015 made the point of the design.
- **Compose the task's sentences in the client.** Every other issue sentence is rendered on
  the server; this one would have been the exception.
