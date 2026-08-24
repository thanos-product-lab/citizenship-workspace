"""row-level security on the case-scoped personal tables

Defence-in-depth behind the application ownership check (CLAUDE.md §11; ADR-0006).

The app connects as the DB owner (a superuser locally), and superusers/owners
bypass RLS. So we introduce a non-superuser role `app_rls`; every case-scoped
request does `SET ROLE app_rls` (in `set_tenant`) before querying, which drops the
privileges that would bypass RLS. Each policy then filters rows by the per-request
tenant GUC `app.user_id`. `current_setting(..., true)` is NULL when the GUC is
unset, so an unset tenant matches no row and rejects every write — fail closed.

The append-only infra tables (events / audit / outbox) are not tenant-scoped: they
hold non-identifying data and are read by system workers across tenants. `app_rls`
still needs DML on them (the unit of work writes there), hence the schema-wide grant.

Revision ID: 0004_row_level_security
Revises: 0003_route_profiles
Create Date: 2026-07-27
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0004_row_level_security"
down_revision: str | None = "0003_route_profiles"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

APP_ROLE = "app_rls"
_TENANT = "current_setting('app.user_id', true)"

# table → the predicate that makes a row visible to / writable by the current tenant.
_POLICIES: dict[str, str] = {
    "cases": f"owner_user_id = {_TENANT}",
    "case_memberships": f"user_id = {_TENANT}",
    "route_profiles": (
        "EXISTS (SELECT 1 FROM cases c "
        f"WHERE c.id = route_profiles.case_id AND c.owner_user_id = {_TENANT})"
    ),
    "route_profile_versions": (
        "EXISTS (SELECT 1 FROM route_profiles rp JOIN cases c ON c.id = rp.case_id "
        f"WHERE rp.id = route_profile_versions.route_profile_id AND c.owner_user_id = {_TENANT})"
    ),
}

_DML = "SELECT, INSERT, UPDATE, DELETE"


def upgrade() -> None:
    # A non-superuser role the app switches into so RLS actually applies.
    op.execute(
        f"DO $$ BEGIN "
        f"IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = '{APP_ROLE}') THEN "
        f"CREATE ROLE {APP_ROLE} NOLOGIN NOSUPERUSER; END IF; END $$;"
    )
    # Postgres 15+ does not grant schema USAGE to new roles by default.
    op.execute(f"GRANT USAGE ON SCHEMA public TO {APP_ROLE}")
    op.execute(f"GRANT {_DML} ON ALL TABLES IN SCHEMA public TO {APP_ROLE}")
    op.execute(f"ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT {_DML} ON TABLES TO {APP_ROLE}")
    # Let the connecting (owner) role switch into app_rls via SET ROLE.
    op.execute(f"GRANT {APP_ROLE} TO CURRENT_USER")

    for table, predicate in _POLICIES.items():
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY {table}_tenant ON {table} "
            f"FOR ALL USING ({predicate}) WITH CHECK ({predicate})"
        )


def downgrade() -> None:
    for table in _POLICIES:
        op.execute(f"DROP POLICY IF EXISTS {table}_tenant ON {table}")
        op.execute(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE {_DML} ON TABLES FROM {APP_ROLE}")
    # DROP OWNED clears the role's grants so the role can be dropped.
    op.execute(f"DROP OWNED BY {APP_ROLE}")
    op.execute(f"REVOKE {APP_ROLE} FROM CURRENT_USER")
    op.execute(f"DROP ROLE IF EXISTS {APP_ROLE}")
