"""evidence_file_texts: what a parser read out of one file version (Domain §15.1)

A separate table from `evidence_files` for two reasons, one of which is a security
property rather than a preference.

**The library projection selects the file row for every document on screen.** Document
text is Tier-3 content (threat model §3). Columns here rather than there mean a page load
cannot drag a hundred documents' text into the API process on its way to rendering a list
of filenames.

**Deletion is different.** An `evidence_files` row survives evidence deletion as a
tombstone (Domain §51.1 step 7); this row must not. It is a copy of exactly the content
the user asked to have removed, and it carries no audit value — so slice 5 deletes it
outright rather than blanking columns on a row it needs to keep.

`UNIQUE (evidence_file_id)` because extraction reads a file version once. A second row
for the same bytes would mean two answers to a question with one answer, and nothing
downstream would know which to believe.

RLS predicates through `evidence_files → evidence_items → cases` — a great-grandchild,
one level deeper than anything before it, and the reason the predicate is worth reading
twice.

Revision ID: 0018_evidence_file_texts
Revises: 0017_evidence_owner_function
Create Date: 2026-08-24
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0018_evidence_file_texts"
down_revision: str | None = "0017_evidence_owner_function"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

APP_ROLE = "app_rls"
_TENANT = "current_setting('app.user_id', true)"
_DML = "SELECT, INSERT, UPDATE, DELETE"

_TABLE = "evidence_file_texts"
_PREDICATE = (
    "EXISTS (SELECT 1 FROM evidence_files f "
    "JOIN evidence_items e ON e.id = f.evidence_item_id "
    "JOIN cases c ON c.id = e.case_id "
    f"WHERE f.id = {_TABLE}.evidence_file_id AND c.owner_user_id = {_TENANT})"
)


def upgrade() -> None:
    op.create_table(
        _TABLE,
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "evidence_file_id", sa.Uuid(), sa.ForeignKey("evidence_files.id"), nullable=False
        ),
        sa.Column("page_count", sa.Integer(), nullable=False),
        sa.Column("character_count", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("pipeline_version", sa.String(length=40), nullable=False),
        sa.Column("truncated", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column(
            "extracted_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("page_count >= 0", name="ck_file_texts_page_count"),
        sa.CheckConstraint("character_count >= 0", name="ck_file_texts_character_count"),
        # A document with no text layer is a real, readable file that happens to say
        # nothing — `character_count = 0` is a finding, not a failure, so the constraint
        # allows it while still requiring the two to agree.
        sa.CheckConstraint(
            "(character_count = 0) = (length(content) = 0)",
            name="ck_file_texts_count_matches_content",
        ),
        sa.UniqueConstraint("evidence_file_id", name="uq_file_texts_evidence_file_id"),
    )

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
