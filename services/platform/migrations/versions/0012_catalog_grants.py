"""Narrow `app_rls` to SELECT on the requirement catalog, which 0004 silently widened.

Migration 0004 ends with

    ALTER DEFAULT PRIVILEGES IN SCHEMA public
      GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO app_rls

so every table the owner has created *since* — including the catalog tables in 0007 and
0010 — was born with full DML for the request role. The later explicit
`GRANT SELECT ON <catalog> TO app_rls` in those migrations narrowed nothing: it granted a
privilege the role already held, next to a comment saying "SELECT for the app role". The
comment was the intent; the grant was a no-op superset.

The consequence is not theoretical. `rule_versions` is the immutable record of what a
conclusion was reached under (Domain §24) and `requirement_definitions` is the catalog the
evaluator dispatches on. A request path is never supposed to be able to write either —
provenance that the request role can rewrite is not provenance. Any request-scoped SQL
injection, or a stray `session.add` of a catalog object, could have.

This revokes the three write privileges and leaves SELECT. It does not touch the default
privileges themselves: a future case-scoped table *should* be created with DML for
`app_rls`, which is what that line is for. A new catalog table would need its own revoke —
and `tests/security/test_rls_coverage.py` will not catch that, so the revoke list here is
paired with an explicit privilege assertion in `tests/security/test_catalog_grants.py`.

Found while retrofitting the RLS test harness in M5, not by a failure.

Revision ID: 0012_catalog_grants
Revises: 0011_issues
Create Date: 2026-08-21
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0012_catalog_grants"
down_revision: str | None = "0011_issues"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

APP_ROLE = "app_rls"

# Global reference data: the same rows for every user, written only by migrations.
CATALOG_TABLES = (
    "requirement_definitions",
    "rule_versions",
    "rule_dependency_definitions",
    "rule_composition_edges",
)


def upgrade() -> None:
    for table in CATALOG_TABLES:
        op.execute(f"REVOKE INSERT, UPDATE, DELETE ON {table} FROM {APP_ROLE}")
        op.execute(f"GRANT SELECT ON {table} TO {APP_ROLE}")


def downgrade() -> None:
    for table in CATALOG_TABLES:
        op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON {table} TO {APP_ROLE}")
