"""cases, memberships, and the event/audit/outbox infrastructure

Migration 1 of Domain Model §55 ("Cases and Route"), first half: the ownership
aggregate plus the three append-only sinks every command writes through. Route
profiles and their versions arrive in 0003.

Revision ID: 0002_cases_and_events
Revises: 0001_baseline
Create Date: 2026-07-26
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002_cases_and_events"
down_revision: str | None = "0001_baseline"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _ts(name: str, *, on_update: bool = False) -> sa.Column:
    """A timezone-aware timestamp column defaulting to now() at insert."""
    kwargs = {"onupdate": sa.func.now()} if on_update else {}
    return sa.Column(
        name, sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False, **kwargs
    )


def upgrade() -> None:
    op.create_table(
        "cases",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("owner_user_id", sa.String(length=255), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("route_key", sa.String(length=40), nullable=False),
        sa.Column("lifecycle_status", sa.String(length=20), nullable=False),
        sa.Column("support_status", sa.String(length=20), nullable=False),
        sa.Column("current_phase", sa.String(length=20), nullable=False),
        sa.Column("current_proposed_application_date_id", sa.Uuid(), nullable=True),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deletion_requested_at", sa.DateTime(timezone=True), nullable=True),
        _ts("created_at"),
        _ts("updated_at", on_update=True),
        sa.Column("revision", sa.Integer(), nullable=False),
    )
    op.create_index("ix_cases_owner_user_id", "cases", ["owner_user_id"])

    op.create_table(
        "case_memberships",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("case_id", sa.Uuid(), sa.ForeignKey("cases.id"), nullable=False),
        sa.Column("user_id", sa.String(length=255), nullable=False),
        sa.Column("role", sa.String(length=20), nullable=False),
        _ts("created_at"),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("case_id", "user_id", name="uq_membership_case_user"),
    )
    op.create_index("ix_case_memberships_case_id", "case_memberships", ["case_id"])
    op.create_index("ix_case_memberships_user_id", "case_memberships", ["user_id"])

    op.create_table(
        "domain_events",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("aggregate_type", sa.String(length=60), nullable=False),
        sa.Column("aggregate_id", sa.Uuid(), nullable=False),
        sa.Column("event_type", sa.String(length=60), nullable=False),
        sa.Column("actor_id", sa.String(length=255), nullable=True),
        sa.Column("trace_id", sa.String(length=64), nullable=True),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        _ts("occurred_at"),
    )
    op.create_index("ix_domain_events_aggregate_id", "domain_events", ["aggregate_id"])
    op.create_index("ix_domain_events_event_type", "domain_events", ["event_type"])

    op.create_table(
        "audit_entries",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("case_id", sa.Uuid(), nullable=False),
        sa.Column("actor_type", sa.String(length=20), nullable=False),
        sa.Column("actor_id", sa.String(length=255), nullable=True),
        sa.Column("action", sa.String(length=60), nullable=False),
        sa.Column("target_type", sa.String(length=60), nullable=False),
        sa.Column("target_id", sa.Uuid(), nullable=False),
        sa.Column("trace_id", sa.String(length=64), nullable=True),
        sa.Column("safe_metadata", postgresql.JSONB(), nullable=False),
        _ts("occurred_at"),
    )
    op.create_index("ix_audit_entries_case_id", "audit_entries", ["case_id"])

    op.create_table(
        "outbox_events",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("aggregate_type", sa.String(length=60), nullable=False),
        sa.Column("aggregate_id", sa.Uuid(), nullable=False),
        sa.Column("event_type", sa.String(length=60), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        _ts("created_at"),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_error", sa.String(length=500), nullable=True),
    )
    op.create_index("ix_outbox_events_aggregate_id", "outbox_events", ["aggregate_id"])
    op.create_index("ix_outbox_events_published_at", "outbox_events", ["published_at"])


def downgrade() -> None:
    op.drop_table("outbox_events")
    op.drop_table("audit_entries")
    op.drop_table("domain_events")
    op.drop_table("case_memberships")
    op.drop_table("cases")
