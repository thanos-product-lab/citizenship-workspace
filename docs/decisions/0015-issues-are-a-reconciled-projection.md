# ADR-0015: Issues are a reconciled projection, not event-sourced handlers

**Status:** Accepted
**Date:** 2026-08-20
**Milestone:** M6 (Issue Detection and Stale-State Workflow), slice 2

## Context

Domain §36 requires that resolving an underlying cause automatically resolves the issues it
generated, that a returning cause reopens or recreates, that duplicates are prevented, and
that resolution history is retained. §38 lists `IssueOpened`, `IssueResolved` and
`IssueReopened` — an event vocabulary that presupposes issues being created one at a time by
a handler reacting to a change.

The obvious implementation follows that shape: a handler per cause, each opening its issue,
each remembering to close it again. It is also the implementation in which auto-resolution
quietly rots. Every new derivation adds two obligations, the second one — cleaning up when
the cause disappears — being invisible when forgotten. The failure mode is an issue that
never clears, which reads to the user as a problem they cannot fix.

## Decision

**An issue is a projection of durable state with durable identity.** One entry point,
`IssueDerivationService.reconcile`, computes the complete desired open-issue set from
current state and diffs it against what is stored:

```
desired, no live row      → open, or reopen a resolved row with the same key
live row, not desired     → resolve, writing an IssueResolution
live row, still desired   → leave alone (including a dismissed one), refresh its parameters
```

Auto-resolution and reopening are then properties of one diff rather than of N handlers.
The price is that derivation must be a **pure function of durable state** — no clock, no
ordering dependence, nothing that can flap — enforced by `derivation.py` taking no session
and by an idempotency test that reconciles repeatedly with causes still live.

**Reconciliation lives inside `invalidate_for_input_change`**, not at each call site. A
stale result and the issue announcing it must never disagree, and a convention repeated at
four call sites is one a future writer forgets — the CSV-import seam had already been added
without it, which would have left a bulk import staling conclusions while the queue read
"nothing needs your attention".

**One `IssuesReconciled` event replaces §38's three.** Reconciliation moves the whole set at
once; three event types would imply a per-issue ordering that does not exist. The payload
carries the deduplication keys that opened, resolved and reopened — not counts — so the
append-only log can still answer *which*, which is the point of having it (§39). Domain §38
is amended accordingly.

## Consequences

- **Easier:** a new issue type is one function returning `DesiredIssue`s; its resolution,
  reopening and deduplication come free. Adding a type cannot introduce a leak.
- **Harder / committed:** derivation purity is load-bearing rather than stylistic, and every
  seam that changes case state must reconcile. The invalidation service is now the single
  place that guarantees it, and a test raises between the stale marks and the commit to hold
  the coupling.
- **Cost:** every input change reconciles the whole case. Trivial at twelve trips; unexamined
  at hundreds.

## Rejected alternatives

- **Per-cause event handlers**, matching §38's original vocabulary. Rejected above.
- **Deriving issues at read time**, with no `issues` table. Auto-resolution becomes free, but
  dismissal, reopening and resolution history all require durable identity — §36.6 requires
  all three — so the table is not optional.

## Invariants touched

- **"An issue never directly changes an assessment conclusion" (§36.6, CLAUDE.md §2).**
  Upheld structurally: `app/issues/` writes only `issues` and `issue_resolutions`, and
  RULES_SPEC §8 was amended (ADR-0014) to remove the one rule that read issue state, because
  results→issues→results is a cycle that would dissolve the idempotency guarantee above.
- **Deduplication (§36.6).** A partial unique index on `(case_id, deduplication_key)` where
  `status <> 'RESOLVED'`, so a concurrent reconcile raises rather than leaving a queue the
  user cannot clear.
- **Blocking issues are not dismissible (§36.6).** A CHECK constraint, not a service
  assertion.
- **Dismissal is per-episode.** A dismissed issue whose cause disappears becomes RESOLVED, so
  a returning cause opens a new episode. Leaving it dismissed forever would mean a cause that
  came back met silence — the failure-to-reopen this milestone exists to prevent.
