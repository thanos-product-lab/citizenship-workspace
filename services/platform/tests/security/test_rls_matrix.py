"""Every case-scoped table, proved isolated — not asserted in a migration and trusted.

Migrations 0004, 0005, 0007 and 0011 install thirteen policies. Until now four of them
had a test (`tests/cases/test_rls.py`); the rest were a `CREATE POLICY` statement nobody
had ever watched fail. This suite covers all thirteen, and it covers them the same two
ways a policy can be wrong: it can fail to hide a row (`USING`), and it can fail to
reject a write (`WITH CHECK`).

**How the write probe works.** Building a valid row for thirteen different tables by
hand is brittle and would drift. Instead the owner copies a real row into a temp table
(temp tables carry no RLS), gives it a fresh id, and the *tenant* role inserts it back —
`INSERT INTO t SELECT * FROM probe`. Column order, types and JSONB all come along
untouched, so the probe is a genuine row that only the policy has reason to reject.

The assertion is on the message, not just the exception type. A `ProgrammingError` is
also what a syntax slip raises, and a write-rejection test that passes because the SQL
was malformed proves nothing about the policy.

**What this suite cannot see: `FORCE`.** These tests query as `app_rls`, which does not
own the tables, so policies apply to it whether or not `FORCE ROW LEVEL SECURITY` is set
— `ALTER TABLE ... NO FORCE` leaves every test here green. FORCE is what makes policies
apply to the *owner*, which is the role a query that forgot `set_tenant` runs as. That is
`test_rls_coverage.py`'s job, and the division is deliberate: this file tests behaviour,
that one tests the catalog, and neither covers the other.

Dropping a policy outright also does not leak — Postgres treats a table with RLS enabled
and no policy as deny-all. The mutation that models the real regression is
`ALTER TABLE ... DISABLE ROW LEVEL SECURITY`, and that one turns this file red.
"""

import pytest
from sqlalchemy import text
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.orm import Session

from app.shared.tenant import APP_ROLE, set_tenant

from .conftest import CASE_SCOPED_TABLES, count_rows

pytestmark = pytest.mark.integration

# Copying a row and re-inserting it needs a new primary key. Every case-scoped table
# uses a single `id` column, which the test asserts rather than assumes.
PRIMARY_KEY = "id"


def _assert_populated(session: Session, table: str) -> None:
    """An empty table would make every isolation assertion below vacuously true."""
    session.execute(text("RESET ROLE"))
    assert count_rows(session, table) > 0, (
        f"{table} has no rows, so this test would pass without testing anything — "
        "the seeded_case arrangement no longer reaches it"
    )


@pytest.mark.parametrize("table", CASE_SCOPED_TABLES)
def test_a_case_scoped_table_is_invisible_to_another_tenant(
    seeded_case: str, owner_session: Session, table: str
) -> None:
    _assert_populated(owner_session, table)

    set_tenant(owner_session, "user_b")
    assert count_rows(owner_session, table) == 0, f"{table} leaked rows to another tenant"

    set_tenant(owner_session, "user_a")
    assert count_rows(owner_session, table) > 0, f"{table} hid rows from their own owner"


@pytest.mark.parametrize("table", CASE_SCOPED_TABLES)
def test_a_case_scoped_table_rejects_a_write_for_another_tenant(
    seeded_case: str, owner_session: Session, table: str
) -> None:
    _assert_populated(owner_session, table)

    owner_session.execute(text(f'CREATE TEMP TABLE rls_probe AS SELECT * FROM "{table}" LIMIT 1'))
    owner_session.execute(text(f"UPDATE rls_probe SET {PRIMARY_KEY} = gen_random_uuid()"))
    owner_session.execute(text(f"GRANT SELECT ON rls_probe TO {APP_ROLE}"))

    set_tenant(owner_session, "user_b")
    with pytest.raises(ProgrammingError) as raised:
        owner_session.execute(text(f'INSERT INTO "{table}" SELECT * FROM rls_probe'))

    assert "row-level security policy" in str(raised.value), (
        f"{table} rejected the write for some reason other than its policy: {raised.value}"
    )
    owner_session.rollback()


def test_every_case_scoped_table_fails_closed_with_no_tenant_set(
    seeded_case: str, owner_session: Session
) -> None:
    """The backstop ADR-0006 relies on: under `app_rls` with no `app.user_id` bound, the
    GUC reads NULL and matches no row. A query that forgets to establish a tenant returns
    nothing rather than returning everything."""
    owner_session.execute(text(f"SET ROLE {APP_ROLE}"))  # role set, but no tenant GUC

    leaked = [table for table in CASE_SCOPED_TABLES if count_rows(owner_session, table) > 0]
    assert leaked == [], f"tables readable with no tenant bound: {leaked}"
