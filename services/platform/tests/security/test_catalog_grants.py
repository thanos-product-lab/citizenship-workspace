"""The request role can read the requirement catalog and cannot rewrite it.

RLS is the wrong tool here — the catalog has no tenant dimension, and a policy on it would
be a bug (`test_rls_coverage.py` asserts it has none). Privilege is the right tool, and the
privilege was wrong: migration 0004's `ALTER DEFAULT PRIVILEGES` granted `app_rls` full DML
on every table created after it, so 0007's and 0010's `GRANT SELECT` sat next to a
"SELECT for the app role" comment while granting nothing it did not already have.
Migration 0012 revokes the difference.

This matters because `rule_versions` is what makes a past conclusion reproducible
(Domain §24) and `requirement_definitions` is what the evaluator dispatches on. Provenance
the request role can rewrite is not provenance.

A new catalog table would be created with DML again, by the same default privileges, and
`test_rls_coverage.py` would not notice — it checks policies, not grants. That is what the
last test here is for.
"""

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.requirements.models import CATALOG_TABLES
from app.shared.tenant import APP_ROLE

pytestmark = pytest.mark.integration

WRITE_PRIVILEGES = ("INSERT", "UPDATE", "DELETE")


def _has_privilege(session: Session, table: str, privilege: str) -> bool:
    granted: bool = session.execute(
        text("SELECT has_table_privilege(:role, :table, :privilege)"),
        {"role": APP_ROLE, "table": table, "privilege": privilege},
    ).scalar_one()
    return granted


@pytest.mark.parametrize("table", sorted(CATALOG_TABLES))
def test_the_request_role_can_read_a_catalog_table(db_session: Session, table: str) -> None:
    assert _has_privilege(db_session, table, "SELECT"), (
        f"{table} is unreadable by {APP_ROLE}; every assessment reads the catalog"
    )


@pytest.mark.parametrize("table", sorted(CATALOG_TABLES))
def test_the_request_role_cannot_write_a_catalog_table(db_session: Session, table: str) -> None:
    writable = [p for p in WRITE_PRIVILEGES if _has_privilege(db_session, table, p)]
    assert writable == [], (
        f"{APP_ROLE} can {writable} on {table}. Migration 0004's ALTER DEFAULT PRIVILEGES "
        "grants DML on every table the owner creates, so a new catalog table needs an "
        "explicit REVOKE — add it to a new migration, not to 0012"
    )


def test_the_catalog_list_matches_the_tables_without_row_level_security(
    db_session: Session,
) -> None:
    """Ties this file to `test_rls_coverage.py`: a table is either case-scoped and carries
    a policy, or it is global reference data and carries a revoke. A new table that is
    neither would slip between the two files, so the two definitions of "catalog" are
    asserted equal rather than maintained in parallel."""
    from .test_rls_coverage import GLOBAL_REFERENCE_TABLES

    assert set(CATALOG_TABLES) == set(GLOBAL_REFERENCE_TABLES)
