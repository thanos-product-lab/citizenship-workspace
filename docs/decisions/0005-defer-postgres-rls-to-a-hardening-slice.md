# ADR-0005: App-level ownership is the M2 control; Postgres RLS is deferred to a tracked hardening slice

**Status:** Accepted — RLS deferral **resolved by [ADR-0006](0006-postgres-rls-via-a-non-superuser-role.md)** (RLS hardening slice)
**Date:** 2026-07-26
**Milestone:** M2 (Supported Case Setup), Slice 1

> **Update (2026-07-27):** The RLS hardening slice landed. RLS is now enabled and
> forced on the four case-scoped tables, enforced by switching to a non-superuser
> role per request, and covered by a row-level isolation test — see ADR-0006. The
> "resolve before the M2 gate" commitment below is met; RLS is no longer a blocker.

## Context

CLAUDE.md §11 and the Technical Architecture RFC (§25.2, "row-level isolation")
require Postgres Row-Level Security (RLS) as **defence in depth** behind the
application's case-ownership check. Slice 1 introduces the first case-scoped tables
(`cases`, `case_memberships`, …) but ships **only** the app-level control:
`require_case_access` → `service.get_case` verifies user → membership →
object-to-case. The security review confirmed that control is correct and cannot be
bypassed by changing `case_id`, and that absent and unowned cases are
indistinguishable. But it correctly flagged that RLS is entirely absent — there is no
`ENABLE ROW LEVEL SECURITY`, no tenant policy, and `get_db` sets no per-request
tenant GUC — so a single future case-scoped handler that forgets the membership check
would be a full cross-tenant read with nothing behind it.

## Decision

Ship Slice 1 with the app-level ownership check as the sole enforced control, and
defer RLS to a dedicated hardening slice within M2 (before the milestone gate, not
after it). This ADR is the explicit tracking the review asked for — RLS is a known,
owned gap, not a silent omission. The hardening slice will: enable RLS on every
case-scoped table, add a policy keyed on a per-request tenant identifier, set that
identifier as a `SET LOCAL` GUC inside the request/unit-of-work boundary, and add the
"row-level isolation" backend test (a raw query as the wrong tenant returns nothing)
that cannot pass today.

## Alternatives rejected

- **Add RLS now, inside Slice 1.** RLS with a single application DB role needs a
  per-request GUC threaded through the session boundary and a migration that alters
  every case-scoped table — a cross-cutting change worth doing deliberately and
  testing on its own, not squeezed into the slice that first defines the tables.
  Rejected to keep the slice small and the RLS work reviewable in isolation.
- **Declare app-level checks sufficient and drop RLS.** Contradicts §11 and the
  architecture RFC, and removes the exact safety net that turns "one forgotten
  membership check" from a breach into a blocked query. Rejected.

## Consequences

- **Committed:** M2 does not close until the RLS hardening slice lands and its
  isolation test passes. The milestone gate must check for it.
- **Easier now:** Slice 1 stays a clean vertical; the RLS change gets its own diff.
- **Carries risk in the interim:** every case-scoped handler added before the
  hardening slice must include the membership check, because nothing sits behind it
  yet. `require_case_access` is the sanctioned choke point — new handlers must route
  through it rather than querying by `case_id` directly.

### Related deferred items surfaced by the same review (tracked, not silent)

- **Optimistic-concurrency 409 is wired but unexercised** — `version_id_col` only
  acts on `UPDATE`, and Slice 1 is insert-only. *Resolved in Slice 2:* the draft-save
  UPDATE now has a real stale-revision → 409 integration test, and a concurrent
  first-INSERT unique-violation is translated to 409 in the unit of work
  (`_UNIQUE_VIOLATION`), also tested.
- **Case-lifecycle write guard is a read-then-commit TOCTOU (R2)** — a write command
  read `case.lifecycle_status` from the object loaded by `require_case_access`, while
  the optimistic-concurrency token guarded the *route profile*, not the *case*.
  *Resolved in Slice 4:* both `request_deletion` and the write commands
  (`save_draft` / `confirm`) take a `SELECT … FOR UPDATE` lock on the case row
  (`CaseRepository.get_for_update`) and re-check lifecycle, so a write serialises
  behind a concurrent deletion and cannot land on a case that has become
  `DELETION_PENDING`.
- **Read path ignores lifecycle state** — *Resolved in Slice 4:* `get_case` returns
  None for a `DELETED` case (never served, even before the purge worker removes the
  row); `DELETION_PENDING` remains readable by design, shown as a pending state with
  writes blocked.
- **`email` from the JWT must never be persisted** — `CurrentUser` carries it but it
  is currently never stored, logged, or placed in a payload. Keep it out of
  `safe_metadata` and log lines as the code grows.
- **Terminal purge (`CompleteCaseDeletion`) is deferred (Slice 4)** — M2's `DELETE`
  moves the case to `DELETION_PENDING` and emits `CaseDeletionRequested` to the
  outbox; it does **not** yet hard-delete case-scoped records or stored files. The
  purge belongs to the milestone that builds the outbox worker (and matters only once
  evidence files exist, M4+): consume the outbox event, delete route-profile rows,
  memberships, and the case row within one transaction, retain only a non-identifying
  deletion audit (§11), and transition to `DELETED`. Until then a deleted case sits in
  `DELETION_PENDING`, readable but frozen. **Retention window:** while pending, the
  confirmed route-profile answers (date of birth, status type/date) remain readable to
  the owner; the purge worker must consume the `CaseDeletionRequested` outbox row
  promptly and that latency should be bounded and monitored so this window is short,
  not open-ended.

## Invariants touched

- **§11 (case-ownership checks + RLS as defence in depth):** partially satisfied —
  the primary control (server-side ownership check on every case-scoped read/command)
  is in place and tested; the defence-in-depth layer (RLS) is explicitly deferred and
  tracked here, to land before the M2 gate. No other invariant is affected.
