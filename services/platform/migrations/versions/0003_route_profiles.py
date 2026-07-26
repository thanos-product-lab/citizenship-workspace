"""route profiles and their versions

Migration 1 of Domain Model §55 ("Cases and Route"), second half: the RouteProfile
aggregate and its versions. `current_version_id` and `supersedes_version_id` are
plain UUID pointers (app-maintained) to avoid a circular / self FK; `route_profile_id`
is a real FK for parent-child integrity.

Revision ID: 0003_route_profiles
Revises: 0002_cases_and_events
Create Date: 2026-07-26
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003_route_profiles"
down_revision: str | None = "0002_cases_and_events"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "route_profiles",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("case_id", sa.Uuid(), sa.ForeignKey("cases.id"), nullable=False),
        sa.Column("current_version_id", sa.Uuid(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("revision", sa.Integer(), nullable=False),
    )
    # One case has at most one route profile: a unique index (matches the model's
    # unique=True, index=True on case_id).
    op.create_index("ix_route_profiles_case_id", "route_profiles", ["case_id"], unique=True)

    op.create_table(
        "route_profile_versions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "route_profile_id",
            sa.Uuid(),
            sa.ForeignKey("route_profiles.id"),
            nullable=False,
        ),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("date_of_birth", sa.Date(), nullable=True),
        sa.Column("status_type", sa.String(length=20), nullable=True),
        sa.Column("status_granted_on", sa.Date(), nullable=True),
        sa.Column("married_to_british_citizen", sa.Boolean(), nullable=True),
        sa.Column("may_already_be_british", sa.Boolean(), nullable=True),
        sa.Column("review_state", sa.String(length=20), nullable=False),
        sa.Column("created_by", sa.String(length=255), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("supersedes_version_id", sa.Uuid(), nullable=True),
    )
    op.create_index(
        "ix_route_profile_versions_route_profile_id",
        "route_profile_versions",
        ["route_profile_id"],
    )


def downgrade() -> None:
    op.drop_table("route_profile_versions")
    op.drop_table("route_profiles")
