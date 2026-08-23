"""evidence_items and evidence_files: private supporting documents (Domain §14 and §15)

The first tables in the product that describe something a user uploaded rather than
typed, and therefore the first whose rows point at bytes outside Postgres.

Both get the full 0005/0007/0011 RLS treatment. `tests/security/test_rls_coverage.py`
derives its universe from `pg_constraint` and from any `case_id` column, so both tables
are covered by that suite the moment this migration runs — its docstring has named
`evidence_items` as the test case since M5, and mutation 6 of the M5 gate created
exactly this table shape with no policy to prove the harness catches it.

`evidence_files` predicates through its parent, the grandchild shape already used by
`issue_resolutions`.

Nothing is written until an upload's bytes are confirmed present, so every column here
is populated at creation: there is no reservation state, and an `evidence_items` row
that exists is a document the case actually holds. The storage key survives the round
trip to the client inside a signed token instead (`app/evidence/upload_token.py`).

Three things enforced here rather than only in the service:

- **A file version is unique within its item.** `(evidence_item_id, version_number)`,
  because §14.5 makes replacement an append and two rows claiming version 2 would make
  "the current file" ambiguous.
- **A storage key is used once, globally.** Keys carry 128 bits of randomness, so a
  collision means a generator defect, not bad luck — and two items sharing a key means
  deleting one destroys the other's content.
- **A checksum is unique within an item's version sequence** (§15), so re-uploading the
  identical file as a new version of the *same* item is refused. Cross-item duplicate
  detection is deliberately *not* a constraint: it is an issue to raise, not a write to
  reject (§11.8, "duplicate detection proposes an issue; it does not merge
  automatically"), and it arrives in slice 4.

Revision ID: 0014_evidence
Revises: 0013_alembic_version_grants
Create Date: 2026-08-23
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0014_evidence"
down_revision: str | None = "0013_alembic_version_grants"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

APP_ROLE = "app_rls"
_TENANT = "current_setting('app.user_id', true)"
_DML = "SELECT, INSERT, UPDATE, DELETE"

_POLICIES = {
    "evidence_items": (
        "EXISTS (SELECT 1 FROM cases c "
        f"WHERE c.id = evidence_items.case_id AND c.owner_user_id = {_TENANT})"
    ),
    "evidence_files": (
        "EXISTS (SELECT 1 FROM evidence_items e JOIN cases c ON c.id = e.case_id "
        f"WHERE e.id = evidence_files.evidence_item_id AND c.owner_user_id = {_TENANT})"
    ),
}

_CATEGORIES = (
    "IMMIGRATION_STATUS",
    "ENGLISH_LANGUAGE",
    "LIFE_IN_THE_UK",
    "TRAVEL_SUPPORT",
    "OTHER",
    "UNKNOWN",
)
_LIFECYCLE = ("ACTIVE", "DELETION_PENDING", "DELETED")
_PROCESSING = (
    "UPLOADED",
    "VALIDATING",
    "EXTRACTING_TEXT",
    "ANALYSING",
    "AWAITING_CONFIRMATION",
    "COMPLETED",
    "PARTIALLY_COMPLETED",
    "FAILED",
    "UNSUPPORTED",
)


def _in_list(column: str, values: Sequence[str]) -> str:
    rendered = ", ".join(f"'{value}'" for value in values)
    return f"{column} IN ({rendered})"


def upgrade() -> None:
    op.create_table(
        "evidence_items",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("case_id", sa.Uuid(), sa.ForeignKey("cases.id"), nullable=False),
        sa.Column("category", sa.String(length=30), nullable=False),
        sa.Column("display_name", sa.String(length=255), nullable=False),
        sa.Column("lifecycle_status", sa.String(length=20), nullable=False),
        sa.Column("processing_status", sa.String(length=30), nullable=False),
        sa.Column("current_file_id", sa.Uuid(), nullable=True),
        sa.Column("created_by", sa.String(length=255), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
        sa.CheckConstraint(_in_list("category", _CATEGORIES), name="ck_evidence_items_category"),
        sa.CheckConstraint(
            _in_list("lifecycle_status", _LIFECYCLE), name="ck_evidence_items_lifecycle"
        ),
        sa.CheckConstraint(
            _in_list("processing_status", _PROCESSING), name="ck_evidence_items_processing"
        ),
        # A tombstone has a deletion time and a live item does not (the 0011 shape).
        sa.CheckConstraint(
            "(lifecycle_status = 'DELETED') = (deleted_at IS NOT NULL)",
            name="ck_evidence_items_deleted_at",
        ),
    )
    op.create_index("ix_evidence_items_case_id", "evidence_items", ["case_id"])

    op.create_table(
        "evidence_files",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "evidence_item_id", sa.Uuid(), sa.ForeignKey("evidence_items.id"), nullable=False
        ),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("storage_key", sa.String(length=500), nullable=False),
        sa.Column("original_filename", sa.String(length=255), nullable=True),
        sa.Column("media_type", sa.String(length=120), nullable=False),
        # Read from the store at creation, never from the request.
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("checksum", sa.String(length=128), nullable=False),
        sa.Column("encryption_metadata", postgresql.JSONB(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("uploaded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("supersedes_file_id", sa.Uuid(), nullable=True),
        sa.CheckConstraint("size_bytes >= 0", name="ck_evidence_files_size"),
        sa.UniqueConstraint(
            "evidence_item_id", "version_number", name="uq_evidence_files_item_version"
        ),
        sa.UniqueConstraint("storage_key", name="uq_evidence_files_storage_key"),
    )
    op.create_index("ix_evidence_files_evidence_item_id", "evidence_files", ["evidence_item_id"])
    # §15: "a checksum is unique within one evidence item version sequence where
    # practical". Partial on `deleted_at IS NULL`, so removing a version does not block
    # re-uploading the same content later.
    op.create_index(
        "uq_evidence_files_item_checksum",
        "evidence_files",
        ["evidence_item_id", "checksum"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )

    for table, predicate in _POLICIES.items():
        op.execute(f"GRANT {_DML} ON {table} TO {APP_ROLE}")
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY {table}_tenant ON {table} "
            f"FOR ALL USING ({predicate}) WITH CHECK ({predicate})"
        )


def downgrade() -> None:
    for table in ("evidence_files", "evidence_items"):
        op.execute(f"DROP POLICY IF EXISTS {table}_tenant ON {table}")
        op.execute(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")
        op.execute(f"REVOKE {_DML} ON {table} FROM {APP_ROLE}")
    op.drop_table("evidence_files")
    op.drop_table("evidence_items")
