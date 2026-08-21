"""Stop the request role from being able to rewrite the migration head.

The same finding as 0012, one table further out. Migration 0004's
`GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO app_rls` included
`alembic_version`, which existed by then, so the role every HTTP request runs as can
`UPDATE` the row recording which migration the database is at.

Unlike the catalog tables this is not a disclosure risk — the row is one version string
with no case data in it. It is a sabotage risk: rewriting the head makes the next
`alembic upgrade head` skip or re-run migrations, which corrupts the schema rather than
reading it. `app_rls` needs no privilege on this table at all; migrations run as the owner.

It escaped 0012 and the new coverage test for the same reason: `alembic_version` has no ORM
model, and both derived their universe from `Base.metadata`.
`tests/security/test_rls_coverage.py` now reads `pg_class` instead, so the next table
Postgres knows about and Python does not has to be classified rather than skipped.

Revision ID: 0013_alembic_version_grants
Revises: 0012_catalog_grants
Create Date: 2026-08-21
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0013_alembic_version_grants"
down_revision: str | None = "0012_catalog_grants"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

APP_ROLE = "app_rls"


def upgrade() -> None:
    op.execute(f"REVOKE ALL ON alembic_version FROM {APP_ROLE}")


def downgrade() -> None:
    op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON alembic_version TO {APP_ROLE}")
