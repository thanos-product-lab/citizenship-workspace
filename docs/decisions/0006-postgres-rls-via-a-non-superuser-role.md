# ADR-0006: Postgres RLS enforced by switching to a non-superuser role per request

**Status:** Accepted
**Date:** 2026-07-27
**Milestone:** M2 (Supported Case Setup), RLS hardening slice

## Context

CLAUDE.md §11 and the Technical Architecture RFC (§25.2) require Postgres
Row-Level Security as **defence in depth** behind the application ownership check,
and ADR-0005 made it the blocker for closing M2. The obstacle: the application
connects as the database owner, who — like any superuser — **bypasses RLS
entirely**, even under `FORCE ROW LEVEL SECURITY`. Installing policies against that
connection role is a no-op, and the required "row-level isolation" test cannot pass.
Reprovisioning the runtime connection as a separate non-owner role (a second
`DATABASE_URL`, docker-compose and deploy changes) is the textbook fix but a large,
cross-environment infra change.

## Decision

Introduce a dedicated **non-superuser role `app_rls`** (created and granted DML +
schema `USAGE` in migration `0004`), and have every case-scoped request **`SET ROLE
app_rls`** before it queries — done in `set_tenant`, alongside binding the tenant
identity `SET app.user_id = <clerk sub>`. Switching into a non-privileged role drops
the superuser/owner bypass, so the policies actually apply; the connection role and
`DATABASE_URL` are unchanged. RLS is enabled and **forced** on the four case-scoped
personal tables (`cases`, `case_memberships`, `route_profiles`,
`route_profile_versions`), each with a `FOR ALL` policy keyed on the tenant GUC.

Policies key on **ownership** (`owner_user_id` for `cases`; a parent-case `EXISTS`
check for the child tables; `user_id` for memberships). In the single-owner MVP the
owner is the sole member, so this is the faithful backstop and it avoids the
chicken-and-egg an membership-subquery policy hits at case creation (the membership
does not exist yet when the case row is inserted).

**Fail closed.** Policies read `current_setting('app.user_id', true)`, which is NULL
when unset, matching no row and rejecting every write. A pool **checkin** listener
runs `RESET ROLE; RESET app.user_id` so a connection never returns to the pool
carrying a previous request's tenant — a query that forgot to establish a tenant
context surfaces as "no rows", never a cross-tenant leak.

## Alternatives rejected

- **Separate non-owner connection role (second `DATABASE_URL`).** The most
  conventional approach, but it needs a distinct runtime role, docker-compose, config
  and deploy changes across every environment, and splits migrations (owner) from
  runtime (app role). `SET ROLE` achieves the same enforcement with one migration and
  a two-statement per-request preamble — far less blast radius for identical security.
- **Leave the app as superuser and document that prod must use a non-superuser.**
  Then RLS is installed but unenforced locally and in CI, the isolation test cannot
  pass, and the feature is effectively untested. Rejected — an untested security
  control is not a control.
- **RLS on the infra tables too (events / audit / outbox).** They hold only
  non-identifying data (verified by the security reviews) and are read by system
  workers across tenants; tenant-scoping them would break the outbox worker. Left out
  deliberately; `app_rls` still gets DML on them because the unit of work writes there.

## Consequences

- **Enforced and tested:** the row-level isolation test (`tests/cases/test_rls.py`)
  proves a tenant cannot read or write another tenant's rows at the DB layer, even
  with the app-level check bypassed. A missed membership check is now a blocked query,
  not a breach.
- **Every case-scoped DB access must go through `get_tenant_session`** (which calls
  `set_tenant`). Because unset = fail-closed, a path that forgets it returns nothing
  rather than leaking — the mistake is visible.
- **Background workers** that touch case tables (the deletion purge worker, future
  assessment recalculation) must establish a tenant context or run under a role
  permitted to see the rows they process. None exist yet at M2; noted for when they land.
- **Cross-aggregate single-flush ordering:** there is no ORM `relationship()` between
  modules (a deliberate boundary), so a single flush that inserts a parent and child
  across modules is not ordered by SQLAlchemy. Production never does this (aggregates
  commit separately); test seeds must flush parent-before-child explicitly.
- **Deployment:** migration `0004` runs `CREATE ROLE` / `GRANT`, so the migrating
  role needs `CREATEROLE` (or superuser). Managed Postgres owners generally have it;
  flag for the deploy runbook if a provider restricts role creation.
- **Tests:** the shared session sets a default tenant (`user_a`); `TRUNCATE` teardown
  first `RESET ROLE` (only the owner may truncate). Cross-tenant tests set the tenant
  explicitly and use a second session for the other tenant's reads.

## Residual risks (from the security review, tracked)

The control is sound and non-bypassable for every HTTP path reachable today (all case
routes go through `get_tenant_session`; `SET ROLE app_rls` genuinely drops the bypass;
proven by `tests/cases/test_rls.py`, including a fail-closed test). The following are
tracked residual risks, none a live vulnerability:

- **R1 — the fail-closed guarantee is environment-dependent.** It holds for queries
  running *as `app_rls`* (every real request path, proven by
  `test_rls_fails_closed_when_no_tenant_is_set`). But the login role `citizenship` is
  a **superuser** in local/CI (Postgres image default), and a superuser bypasses RLS
  even under FORCE. So a query that *forgets* `SET ROLE` and runs as the login role
  fails closed only when that role is a non-superuser. Two consequences: (a) the test
  suite, running as superuser, cannot catch a future route wired to `get_db` instead
  of `get_tenant_session`; (b) any environment that connects as a superuser loses the
  backstop entirely.
  - **In place now:** an application **boot check** (`app/main.py` lifespan +
    `connection_is_superuser`) refuses to start a *deployed* environment whose login
    role is a superuser, and warns in local. This makes "prod must connect as a
    non-superuser" an enforced requirement, not just documentation.
  - **Not yet closed:** demoting the local/CI role is **impossible** — `citizenship`
    is the initdb *bootstrap superuser*, and Postgres forbids removing SUPERUSER from
    it (`the bootstrap superuser must have the SUPERUSER attribute`). So the "forgot
    `SET ROLE`" regression cannot be caught in local/CI while tests connect as
    `citizenship`. Closing it requires a **dedicated non-superuser LOGIN role** that
    the app and tests connect as (migrations still run as the owner) — a two-connection
    change (config, docker-compose, CI, deploy). Pending owner decision; tracked here.
- **R2 — `SET ROLE` needs role membership.** The migration grants `app_rls` to
  `CURRENT_USER` (the migrating role). If prod migrates as one role and serves as
  another, the runtime role is not a member and every case request 500s (fail-closed,
  but availability). Grant `app_rls` to the explicit runtime role, or require
  migration-role == runtime-role. Runbook item (with the `CREATEROLE` note).
- **R3 — infra tables are unscoped.** `audit_entries` / `domain_events` hold `case_id`
  and `actor_id`; they are deliberately outside RLS (system-read, non-identifying).
  No route reads them today, but a *future* tenant-facing read of these tables would
  have no isolation. Any such route must add an ownership-keyed policy first.
- **R4 — `SET ROLE` is reversible on the same connection.** Because the login role is
  a member of `app_rls`, an application query that issued `RESET ROLE` / `SET ROLE
  <owner>` would re-acquire the bypass. No application query issues role statements
  (only the checkin listener does, legitimately); an accepted property of this approach.
- **R5 — a pre-first-commit rollback reverts the role and GUC.** `set_tenant` sets the
  role and GUC inside the request's first (uncommitted) transaction; Postgres reverts
  non-LOCAL `SET`/`set_config` on `ROLLBACK`. So after a `session.rollback()` before
  any commit (e.g. `UnitOfWork` catching a conflict), the session drops to the owner
  role with no tenant. Latent — no handler re-queries after such a rollback (they
  raise) — but combined with R1 a future "catch-and-re-query" pattern would fail open
  locally. Fix when the tenant mechanism is revisited: establish the tenant on a
  connection checkout/begin event (driven by a context var) so it survives rollbacks,
  or re-assert `set_tenant` after any rollback.

## Invariants touched

- **§11 (case-ownership checks + RLS as defence in depth):** now fully satisfied —
  the primary control (server-side ownership check) and the defence-in-depth layer
  (enforced, tested RLS) are both in place. This resolves the deferral tracked in
  ADR-0005; RLS is no longer an M2 blocker. R1's "runtime role must be non-superuser"
  is a deployment requirement, not a gap in the control itself.
