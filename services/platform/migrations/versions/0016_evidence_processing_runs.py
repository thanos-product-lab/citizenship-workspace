"""evidence_processing_runs: one execution of the pipeline against one file version

Domain §16. The table exists as much for its **unique constraint** as for its columns.

`idempotency_key` is the outbox row's own id, and unique. That makes the delivery
identity the idempotency identity, which gets both cases right with no extra state:

- a duplicate delivery carries the same outbox row, so it collides here and the task
  returns having done nothing (§16.2, and CLAUDE.md §9 — "a duplicate worker delivery
  cannot create duplicate claims or results");
- a user-initiated retry writes a *new* outbox row, so it gets a new key and a genuinely
  new run.

The obvious alternative, `file_id:pipeline_version`, cannot distinguish those two and
would need an attempt counter bolted on to try.

RLS predicates through `evidence_items`, the grandchild shape used by `issue_resolutions`
and `evidence_files`.

Revision ID: 0016_evidence_processing_runs
Revises: 0015_outbox_reader
Create Date: 2026-08-24
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0016_evidence_processing_runs"
down_revision: str | None = "0015_outbox_reader"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

APP_ROLE = "app_rls"
_TENANT = "current_setting('app.user_id', true)"
_DML = "SELECT, INSERT, UPDATE, DELETE"

_TABLE = "evidence_processing_runs"
_PREDICATE = (
    "EXISTS (SELECT 1 FROM evidence_items e JOIN cases c ON c.id = e.case_id "
    f"WHERE e.id = {_TABLE}.evidence_item_id AND c.owner_user_id = {_TENANT})"
)

_STATUSES = ("QUEUED", "RUNNING", "SUCCEEDED", "PARTIAL", "FAILED", "CANCELLED")


def upgrade() -> None:
    op.create_table(
        _TABLE,
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "evidence_item_id", sa.Uuid(), sa.ForeignKey("evidence_items.id"), nullable=False
        ),
        sa.Column(
            "evidence_file_id", sa.Uuid(), sa.ForeignKey("evidence_files.id"), nullable=False
        ),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("pipeline_version", sa.String(length=40), nullable=False),
        sa.Column(
            "started_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("retry_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("failure_code", sa.String(length=40), nullable=True),
        # Short and safe. §16.2: failure summaries must not contain raw document content,
        # and never an exception string — a driver error carries bound parameters.
        sa.Column("failure_summary", sa.String(length=200), nullable=True),
        sa.Column("trace_id", sa.String(length=64), nullable=True),
        sa.Column("idempotency_key", sa.String(length=80), nullable=False),
        sa.CheckConstraint(
            "status IN " + str(_STATUSES).replace("'", "'"), name="ck_processing_runs_status"
        ),
        # A finished run has an end; a running one does not.
        sa.CheckConstraint(
            "(status IN ('RUNNING', 'QUEUED')) = (completed_at IS NULL)",
            name="ck_processing_runs_completed_at",
        ),
        # A failure names why. Anything else must not pretend to have failed.
        sa.CheckConstraint(
            "(failure_code IS NULL) OR (status = 'FAILED')",
            name="ck_processing_runs_failure_code",
        ),
        sa.UniqueConstraint("idempotency_key", name="uq_processing_runs_idempotency_key"),
    )
    op.create_index(f"ix_{_TABLE}_evidence_item_id", _TABLE, ["evidence_item_id"])

    op.execute(f"GRANT {_DML} ON {_TABLE} TO {APP_ROLE}")
    op.execute(f"ALTER TABLE {_TABLE} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {_TABLE} FORCE ROW LEVEL SECURITY")
    op.execute(
        f"CREATE POLICY {_TABLE}_tenant ON {_TABLE} "
        f"FOR ALL USING ({_PREDICATE}) WITH CHECK ({_PREDICATE})"
    )


def downgrade() -> None:
    op.execute(f"DROP POLICY IF EXISTS {_TABLE}_tenant ON {_TABLE}")
    op.execute(f"ALTER TABLE {_TABLE} NO FORCE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {_TABLE} DISABLE ROW LEVEL SECURITY")
    op.execute(f"REVOKE {_DML} ON {_TABLE} FROM {APP_ROLE}")
    op.drop_table(_TABLE)
