# ADR-0005: App-level ownership is the M2 control; Postgres RLS is deferred to a tracked hardening slice

**Status:** Accepted
**Date:** 2026-07-26
**Milestone:** M2 (Supported Case Setup), Slice 1

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
  acts on `UPDATE`, and Slice 1 is insert-only. The first mutating command (route
  confirm, Slice 3) must ship with a real stale-revision → 409 integration test.
- **Read path ignores lifecycle state** — `get_case` returns a case regardless of
  `lifecycle_status`. When `request_deletion` / hard delete lands (Slice 4), the read
  path must exclude `DELETION_PENDING` / `DELETED` cases (or deletion must remove the
  rows). Deletion is terminal (§11).
- **`email` from the JWT must never be persisted** — `CurrentUser` carries it but it
  is currently never stored, logged, or placed in a payload. Keep it out of
  `safe_metadata` and log lines as the code grows.

## Invariants touched

- **§11 (case-ownership checks + RLS as defence in depth):** partially satisfied —
  the primary control (server-side ownership check on every case-scoped read/command)
  is in place and tested; the defence-in-depth layer (RLS) is explicitly deferred and
  tracked here, to land before the M2 gate. No other invariant is affected.
