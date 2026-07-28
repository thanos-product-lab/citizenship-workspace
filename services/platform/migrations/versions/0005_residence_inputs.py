"""residence inputs: proposed application dates and travel records, with versions

Migration 2 of Domain Model §55 ("Residence"): the ProposedApplicationDate and
TravelRecord aggregates and their immutable version tables. Mirrors the pointer
conventions proved in 0003 — `current_version_id` and `supersedes_version_id` are
plain app-maintained UUID pointers (no circular / self FK); the parent-child link
(`*_id`) is a real FK for integrity.

Two structural invariants are enforced here at the database, not only in the service:

- `ck_travel_version_date_order` rejects any version whose departure is after its
  return (Domain §11.8). Versions are insert-only, so a CHECK is a clean backstop.
- `uq_proposed_date_one_current` is a partial unique index making "at most one
  current proposed date per case" (Domain §10.3) structurally impossible to violate,
  even though M3A only ever creates one candidate root per case.

All four tables get RLS policies and grants in the same migration (0004's pattern):
a new case-scoped table without a tenant policy is a data leak, so the table and its
policy ship together. Dates stored as `DATE`, audit stamps as `TIMESTAMPTZ`
(Domain §6.2, §6.3); no derived absence count or window is stored — those are the M3B
rules' job, computed from these raw endpoints.

Revision ID: 0005_residence_inputs
Revises: 0004_row_level_security
Create Date: 2026-07-28
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005_residence_inputs"
down_revision: str | None = "0004_row_level_security"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

APP_ROLE = "app_rls"
_TENANT = "current_setting('app.user_id', true)"
_DML = "SELECT, INSERT, UPDATE, DELETE"

# table → predicate that makes a row visible to / writable by the current tenant.
# Same shape as 0004: root tables filter on their own case_id; version tables reach
# the case through their parent root.
_POLICIES: dict[str, str] = {
    "proposed_application_dates": (
        "EXISTS (SELECT 1 FROM cases c "
        f"WHERE c.id = proposed_application_dates.case_id AND c.owner_user_id = {_TENANT})"
    ),
    "proposed_application_date_versions": (
        "EXISTS (SELECT 1 FROM proposed_application_dates pad "
        "JOIN cases c ON c.id = pad.case_id "
        "WHERE pad.id = proposed_application_date_versions.proposed_application_date_id "
        f"AND c.owner_user_id = {_TENANT})"
    ),
    "travel_records": (
        "EXISTS (SELECT 1 FROM cases c "
        f"WHERE c.id = travel_records.case_id AND c.owner_user_id = {_TENANT})"
    ),
    "travel_record_versions": (
        "EXISTS (SELECT 1 FROM travel_records tr JOIN cases c ON c.id = tr.case_id "
        "WHERE tr.id = travel_record_versions.travel_record_id "
        f"AND c.owner_user_id = {_TENANT})"
    ),
}


def upgrade() -> None:
    op.create_table(
        "proposed_application_dates",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("case_id", sa.Uuid(), sa.ForeignKey("cases.id"), nullable=False),
        sa.Column("current_version_id", sa.Uuid(), nullable=True),
        sa.Column("is_current", sa.Boolean(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("revision", sa.Integer(), nullable=False),
    )
    op.create_index(
        "ix_proposed_application_dates_case_id", "proposed_application_dates", ["case_id"]
    )
    # At most one current proposed date per case (Domain §10.3), enforced in the DB.
    op.create_index(
        "uq_proposed_date_one_current",
        "proposed_application_dates",
        ["case_id"],
        unique=True,
        postgresql_where=sa.text("is_current"),
    )

    op.create_table(
        "proposed_application_date_versions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "proposed_application_date_id",
            sa.Uuid(),
            sa.ForeignKey("proposed_application_dates.id"),
            nullable=False,
        ),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("application_date", sa.Date(), nullable=False),
        sa.Column("review_state", sa.String(length=20), nullable=False),
        sa.Column("source", sa.String(length=20), nullable=False),
        sa.Column("created_by", sa.String(length=255), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("supersedes_version_id", sa.Uuid(), nullable=True),
    )
    op.create_index(
        "ix_proposed_application_date_versions_root_id",
        "proposed_application_date_versions",
        ["proposed_application_date_id"],
    )

    op.create_table(
        "travel_records",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("case_id", sa.Uuid(), sa.ForeignKey("cases.id"), nullable=False),
        sa.Column("current_version_id", sa.Uuid(), nullable=True),
        sa.Column("lifecycle_status", sa.String(length=20), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("revision", sa.Integer(), nullable=False),
    )
    op.create_index("ix_travel_records_case_id", "travel_records", ["case_id"])

    op.create_table(
        "travel_record_versions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "travel_record_id",
            sa.Uuid(),
            sa.ForeignKey("travel_records.id"),
            nullable=False,
        ),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("destination_country_code", sa.String(length=2), nullable=True),
        sa.Column("destination_label", sa.String(length=120), nullable=False),
        sa.Column("departure_date", sa.Date(), nullable=False),
        sa.Column("return_date", sa.Date(), nullable=False),
        sa.Column("date_confidence", sa.String(length=20), nullable=False),
        sa.Column("review_state", sa.String(length=20), nullable=False),
        sa.Column("entry_source", sa.String(length=20), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_by", sa.String(length=255), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("supersedes_version_id", sa.Uuid(), nullable=True),
        # Departure not after return (Domain §11.8). Equal is allowed: a same-day
        # trip is zero absent days under RULES_SPEC §5.4, not an error.
        sa.CheckConstraint("departure_date <= return_date", name="ck_travel_version_date_order"),
    )
    op.create_index(
        "ix_travel_record_versions_travel_record_id",
        "travel_record_versions",
        ["travel_record_id"],
    )

    # RLS + grants for the new case-scoped tables (0004's pattern). ALTER DEFAULT
    # PRIVILEGES from 0004 should already cover app_rls on tables this owner creates,
    # but grant explicitly too — a missing grant on a forced-RLS table is a silent
    # "permission denied" for every request, so make it certain.
    for table, predicate in _POLICIES.items():
        op.execute(f"GRANT {_DML} ON {table} TO {APP_ROLE}")
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
        op.execute(f"REVOKE {_DML} ON {table} FROM {APP_ROLE}")

    op.drop_table("travel_record_versions")
    op.drop_table("travel_records")
    op.drop_table("proposed_application_date_versions")
    op.drop_table("proposed_application_dates")
