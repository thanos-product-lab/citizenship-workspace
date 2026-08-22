# ADR-0017: The RLS tenant is transaction-scoped and re-applied automatically

**Status:** Accepted
**Date:** 2026-08-22
**Milestone:** M5 slice 1b (RLS harness follow-up)
**Supersedes the mechanism of:** ADR-0006 (its decision stands; how the tenant is bound changes)
**Resolves:** ADR-0006 R5. **Unblocks:** ADR-0006 R1 Option A.

## Context

ADR-0006 established the tenant context as two statements issued once per request:

```sql
SET ROLE app_rls;
SELECT set_config('app.user_id', '<clerk sub>', false);
```

`is_local=false` was chosen deliberately, and ADR-0005's `SET LOCAL` was rejected, on the
grounds that the unit of work commits in the middle of a request and a transaction-scoped
setting would not survive that.

**The reasoning was right about the problem and wrong about the fix.** Both settings live
on the *connection*, and `Session.commit()` releases the connection back to the pool, where
the checkin listener added by the same ADR runs `RESET ROLE; RESET app.user_id`. Non-LOCAL
survives a `COMMIT`; it does not survive the checkin the commit triggers. Every statement
after a mid-request commit ran with no role and no tenant:

```
set_tenant(session, "user_a")   ->  (app_rls, 'user_a')
session.commit()                ->  connection released, checkin reset fires
session.execute(...)            ->  (login_role, '')
```

This survived from M2 to M5 with a green suite because the login role is a superuser in
every environment, and a superuser bypasses RLS. The tenantless query simply succeeded.
It became visible the moment M5's harness introduced a genuinely non-superuser connection
(`tests/security/`), which is what that harness was built for.

Eleven call sites across six modules query after their own commit. Ten raise
`InvalidRequestError` from a `session.refresh`, which is loud. The eleventh does not:
`_run_trusted_assessment` commits, and the route then builds its response from
`list_requirements`. `POST /assessments/recalculate` therefore answered **200** with
`result_count: 9` and every requirement reading `NOT_YET_ASSESSED`, currency `null`, while
the rows it had just written said `SUPPORTED` / `CURRENT`.

That is a silent wrong answer on the assessment path, on the one endpoint whose job is to
report what the deterministic rules concluded. Prime directive 7 — prefer visible
uncertainty to false reassurance — is about model output, but the same principle applies
harder to deterministic output: a confident `NOT_YET_ASSESSED` over results that exist is
the product lying about its own reasoning.

## Decision

**The tenant is recorded on the `Session`, not on the connection, and re-applied at the
start of every transaction.**

- `set_tenant` writes the user id to `session.info[TENANT_SESSION_KEY]` and applies it to
  the current transaction.
- An `after_begin` listener registered on the SQLAlchemy `Session` class re-applies role
  and GUC whenever the session opens a transaction — which includes the autobegin after
  every commit and every rollback.
- Both settings are now `is_local=True`, in a single round trip
  (`SELECT set_config('role', …, true), set_config('app.user_id', …, true)`). Local is the
  right scope once the listener re-arms per transaction: settings unwind on their own, so
  no connection can carry a tenant anywhere.
- `clear_tenant` exists for the one caller that must act as the owner on a session that has
  been in a tenant context — the test harness truncating tables. Popping `session.info`
  alone would not do it, because the current transaction still carries what the listener
  applied.

Registering on the `Session` class rather than one sessionmaker is deliberate: it covers
the request session, the recalculation-failure recovery's own session, the CLI scripts and
the seed. Anything that calls `set_tenant` is covered by construction rather than by
someone remembering.

## Alternatives rejected

- **Restore the refreshes another way** — e.g. stop calling `session.refresh` after commit,
  or set `expire_on_commit` differently. This addresses the loud half and leaves the silent
  half exactly as it was. `list_requirements` is a genuine query, not a refresh.
- **Keep one transaction open for the whole request.** Would hold a connection and a row
  lock across the unit of work's boundaries, defeating the reason the uow commits when it
  does, and would not help any path that opens its own session.
- **Drop the pool checkin reset.** It is what stops a pooled connection carrying a previous
  request's tenant. Removing it trades a correctness bug for a cross-tenant leak. It stays,
  and is now belt-and-braces rather than load-bearing.
- **Set the tenant in `get_db` instead of `get_tenant_session`.** Would put every session in
  a tenant context including ones that must not be, and still would not survive a commit.

## Consequences

- ADR-0006 **R5** — a pre-first-commit `ROLLBACK` reverting the non-LOCAL role and GUC — is
  the same root cause reached through a different door, and is closed by the same change.
  Verified: the tenant now holds across both a commit and a rollback.
- ADR-0006 **R1 Option A** (a dedicated non-superuser LOGIN role for the app) is no longer
  blocked. It was un-adoptable while every write command failed on such a role. Adopting it
  in production remains a separate decision with its own infrastructure cost.
- Two extra `set_config` calls per transaction, in one round trip. The previous design
  issued two statements per request; this issues one per transaction.
- Three regression tests in `tests/security/test_rls_login_role.py` — the raising half, the
  silent half, and the mechanism itself including the rollback case. Neutering the listener
  turns all three red, and only on the non-superuser connection.

## Invariants touched

CLAUDE.md §11 (server-side case-ownership checks with RLS as defence in depth) — the
backstop is now per-transaction rather than per-request-until-the-first-commit. And §2.7
by extension: the failure mode this closes was the product reporting no conclusion where it
had reached nine.
