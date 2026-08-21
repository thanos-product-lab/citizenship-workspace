# ADR-0016: A failed recalculation is recorded best-effort, in its own transaction

**Status:** Accepted
**Date:** 2026-08-21
**Milestone:** M6 (Issue Detection and Stale-State Workflow), slice 4

## Context

Domain §41.4 says that when recalculation fails, the old result stays `STALE`, nothing is
promoted to current, **a processing issue is opened**, and the user sees the last conclusion
and why it is stale.

Only the first two were true. `recalculate` had no `try`: a failure propagated, the
transaction rolled back, and *nothing survived* — no run row, no issue, no record of any
kind. The header showed a transient alert that a reload erased, leaving stale conclusions
with nothing on screen explaining why they had not been refreshed. Silence and success
looked identical, which is the shape of every false-reassurance defect in this product
(CLAUDE.md §2.7).

The difficulty is that the durable record has to be written by the code path whose defining
feature is that writing has just failed.

## Decision

### The record is written in a separate transaction, and is best-effort

On any non-`DomainError` failure, `recalculate` rolls the failed transaction back, then in a
**fresh session and transaction** writes an `AssessmentRun` with `status = FAILED`, emits
`AssessmentRunFailed`, and reconciles the issue queue. It then re-raises the **original**
exception.

The whole recovery is wrapped and **must never raise**. It runs from inside an `except`
block, and an exception thrown from a handler replaces the one that caused it: the engineer
investigating would be shown the recovery's failure and lose the cause on the way out.
Worse, the failure mode that guarantees the recovery also fails — a dead database
connection — is exactly the one where the original error matters most.

So the durable record is an **improvement on the safe state, not a precondition for it**.
The results are already `STALE` and nothing was promoted whether or not this write lands. If
it is lost the user sees stale conclusions without the explanation, which is worse than the
alternative but still not misleading.

### `failure_summary` holds a code, never the exception

`assessment_runs.failure_summary` is a `Text` column and `str(exc)` is the obvious thing to
put in it. Never do that: a driver error renders its statement's bound parameters, so an
exception string is the shortest path from a destination label or a date of birth into a
column nothing treats as case data — the leak §11 forbids in logs, through a door nobody was
watching. Two codes, chosen from the exception *type*:

- `RULE_CONFIGURATION_INVALID` — a catalogued requirement has no definition row or no active
  rule version. A packaging bug; every retry fails identically.
- `UNEXPECTED_ERROR` — anything else. A retry may well clear it.

The recovery's own exception is logged by **type and trace id**, not by message, for the
same reason. The *original* exception propagates unchanged and is handled the ordinary way.

### Precondition failures record nothing

`CaseNotActive` and `CaseNotAssessable` are raised before any work and are already mapped to
409s. A case that is not active, or has no application date, has not suffered a processing
failure — the request was wrong and the case is intact. Recording a FAILED run for one would
put an item in the queue that no retry could ever clear. `ConcurrencyConflict` is excluded on
the same grounds: another writer got there first, and the recalculation it performed stands.

### `PROCESSING_FAILURE` is derived, not created

The recovery path does not create the issue. Derivation asks one question — *did the case's
most recently finished run fail?* — so the failure opens the issue and the next successful
run closes it, both through the ordinary reconciler diff. No special-case cleanup, and
nothing to forget on a recalculation path added later.

It is keyed **on the case, not on the failed run**: `PROCESSING_FAILURE:Case:{case_id}`. The
condition being reported is "the most recent attempt did not complete", which persists across
repeated failures, so a second failure reshapes one open issue rather than resolving the
first and opening a second. Keying on the run id would write a `SYSTEM_AUTO_RESOLVED` row on
every retry for a failure that nothing resolved — false progress in the one record that
exists to rule it out.

Severity is `ACTION_REQUIRED`, never dismissible. Nothing about the case is wrong, and the
stale conclusions underneath are still the honest last word — but setting the item aside
would leave the user looking at figures the product knows are unrefreshed with nothing saying
so.

### "Latest run" is ordered by `completed_at`, not `started_at`

`started_at` carries a `server_default` of `now()`, which in Postgres is the **transaction**
timestamp, not the statement's. The recovery opens its own connection, so its transaction can
begin *after* one that later inserts the successful retry — and the failure then reads as the
newer run while the queue keeps showing a processing failure the user has already cleared.
This was reproduced, not theorised. `completed_at` is set in Python at the moment a run ends,
by both `complete()` and `fail()`, so it orders the way a reader expects. Unfinished
(`RUNNING`) rows are excluded: a process that died mid-flight is not evidence of failure.

## Alternatives rejected

- **Write the FAILED run on the same transaction.** It rolls back with everything else. This
  is the current behaviour, and it is the defect.
- **Let the recovery failure propagate.** Turns one legible failure into an opaque one and
  discards the original cause. Rejected on the strength of the correlation: the likeliest
  reason the recovery fails is the reason the recalculation failed.
- **Store the exception string for diagnosability.** Rejected under §11. The trace id links
  the row to a log line that has the detail, without putting it in a database column.
- **Create the `PROCESSING_FAILURE` issue directly in the recovery path.** Splits the
  lifecycle across two mechanisms: created by a handler, resolved by the reconciler. ADR-0015
  exists because that shape is where auto-resolution rots.
- **Retry automatically.** A retry loop against an unknown failure is how a transient becomes
  an outage. The user has one button and can see what it did.

## Consequences

- **Easier:** `AssessmentRunStatus.FAILED` is finally written; "how many times has this
  failed?" is answerable from the run table; the queue explains why conclusions are still
  stale, and survives a reload.
- **Harder / committed:** the recovery path is deliberately silent about its own failures, so
  a persistently broken recovery is visible only in logs. The `_record_failed_run` seam has
  to stay exception-free as it grows, which is a discipline a test pins rather than a type.
- **Frontend:** `useRecalculate` now refetches on error as well as on success, since a failed
  recalculation leaves server state the client should show. That reverses an earlier
  assertion, which is why the test that made it was rewritten with its reasoning rather than
  deleted.

## Invariants touched

- **"A failed recalculation cannot replace the last historical result"** (CLAUDE.md §9):
  upheld and now tested directly, by result *id* rather than by value — a run that superseded
  the results and wrote identical replacements would pass a value comparison while having
  rewritten history.
- **§2.3 (assessment history immutable):** upheld — the FAILED run is a new row; nothing is
  edited.
- **§2.4 (conclusion and currency separate):** upheld — the failure changes neither. It
  explains why the currency has not moved.
- **§2.7 (prefer visible uncertainty to false reassurance):** this is the ADR's whole
  purpose. A failure that leaves no trace is the reassuring outcome, and the wrong one.
- **§9 / §11 (no PII in logs, traces or events):** upheld by construction — the code is an
  enum value, and a test plants a canary in the exception message and checks every table the
  failure path writes.
