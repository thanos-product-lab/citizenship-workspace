"""issues and issue_resolutions: the durable, user-actionable queue (Domain §36 and §37)

Two case-scoped tables with the full 0005/0007 RLS treatment.

Three invariants are enforced structurally rather than only in the service, because each is
a silent failure if application logic ever misses it:

- **Deduplication.** A partial unique index on `(case_id, deduplication_key)` for every
  non-RESOLVED row. Two open issues for one cause is a queue the user cannot clear; a
  concurrent double-reconcile must raise, not duplicate. RESOLVED rows are excluded so the
  same cause can recur across episodes and keep its history.
- **Blocking issues are not dismissible** (§36.6). A CHECK, so no code path can offer a
  dismiss control on an issue that must not have one.
- **A resolved issue has a resolution time**, and an unresolved one does not.

`issue_resolutions` is append-only: reopening an issue leaves its prior resolution row in
place and sets `reopened_at`, so the history survives the cause returning (§36.6).

Revision ID: 0011_issues
Revises: 0010_rule_composition_edges
Create Date: 2026-08-20
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0011_issues"
down_revision: str | None = "0010_rule_composition_edges"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

APP_ROLE = "app_rls"
_TENANT = "current_setting('app.user_id', true)"
_DML = "SELECT, INSERT, UPDATE, DELETE"

_POLICIES = {
    "issues": (
        "EXISTS (SELECT 1 FROM cases c "
        f"WHERE c.id = issues.case_id AND c.owner_user_id = {_TENANT})"
    ),
    "issue_resolutions": (
        "EXISTS (SELECT 1 FROM issues i JOIN cases c ON c.id = i.case_id "
        f"WHERE i.id = issue_resolutions.issue_id AND c.owner_user_id = {_TENANT})"
    ),
}


def upgrade() -> None:
    op.create_table(
        "issues",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("case_id", sa.Uuid(), sa.ForeignKey("cases.id"), nullable=False),
        sa.Column("issue_type", sa.String(length=40), nullable=False),
        sa.Column("severity", sa.String(length=20), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("dismissibility", sa.String(length=20), nullable=False),
        sa.Column("deduplication_key", sa.String(length=200), nullable=False),
        sa.Column("title_code", sa.String(length=60), nullable=False),
        sa.Column(
            "message_parameters",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("affected_object_type", sa.String(length=40), nullable=False),
        # Not an FK: the referent is polymorphic (a requirement key, a travel record, a
        # run), matching `assessment_input_links.input_version_id`.
        sa.Column("affected_object_id", sa.String(length=120), nullable=False),
        sa.Column("source_event_id", sa.Uuid(), nullable=True),
        sa.Column(
            "opened_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reopened_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
        sa.CheckConstraint(
            "status IN ('OPEN', 'IN_PROGRESS', 'RESOLVED', 'DISMISSED')",
            name="ck_issue_status",
        ),
        sa.CheckConstraint(
            "severity IN ('INFORMATION', 'ACTION_REQUIRED', 'REVIEW_REQUIRED', 'BLOCKING')",
            name="ck_issue_severity",
        ),
        sa.CheckConstraint(
            "dismissibility IN ('DISMISSIBLE', 'NOT_DISMISSIBLE')",
            name="ck_issue_dismissibility",
        ),
        # §36.6: blocking issues are never dismissible. A CHECK rather than a service
        # assertion, so no future path can offer the control.
        sa.CheckConstraint(
            "severity <> 'BLOCKING' OR dismissibility = 'NOT_DISMISSIBLE'",
            name="ck_issue_blocking_not_dismissible",
        ),
        sa.CheckConstraint(
            "(status = 'RESOLVED') = (resolved_at IS NOT NULL)",
            name="ck_issue_resolved_at_matches_status",
        ),
    )
    op.create_index("ix_issues_case_id", "issues", ["case_id"])
    # The deduplication invariant. Partial on "not resolved": one live issue per cause, but
    # a cause that returns after resolution opens a new episode rather than colliding.
    op.create_index(
        "uq_issue_live_deduplication_key",
        "issues",
        ["case_id", "deduplication_key"],
        unique=True,
        postgresql_where=sa.text("status <> 'RESOLVED'"),
    )

    op.create_table(
        "issue_resolutions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("issue_id", sa.Uuid(), sa.ForeignKey("issues.id"), nullable=False),
        sa.Column("resolution_type", sa.String(length=40), nullable=False),
        sa.Column("resolved_by", sa.String(length=255), nullable=False),
        sa.Column(
            "resolved_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("related_command_id", sa.Uuid(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "resulting_object_ids",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )
    op.create_index("ix_issue_resolutions_issue_id", "issue_resolutions", ["issue_id"])

    for table, predicate in _POLICIES.items():
        op.execute(f"GRANT {_DML} ON {table} TO {APP_ROLE}")
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY {table}_tenant ON {table} "
            f"FOR ALL USING ({predicate}) WITH CHECK ({predicate})"
        )


def downgrade() -> None:
    for table in ("issue_resolutions", "issues"):
        op.execute(f"DROP POLICY IF EXISTS {table}_tenant ON {table}")
        op.execute(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")
        op.execute(f"REVOKE {_DML} ON {table} FROM {APP_ROLE}")
    op.drop_table("issue_resolutions")
    op.drop_table("issues")
