"""evidence_file_texts.pages_read: how much of the document was actually looked at

`page_count` is the document's own page count. Nothing recorded how many pages the read
covered, so a consumer had only two choices: assume they matched, or guess from the page
cap. The UI guessed — it duplicated `MAX_PAGES` in TypeScript and rendered "60 pages,
first 40 read", which was wrong whenever truncation had been caused by the *character*
cap instead ("10 pages, first 10 read" on a truncated 10-page document).

A conclusion drawn from part of a document, described as though drawn from all of it, is
the failure this whole milestone is arranged against. The number belongs on the row.

Backfilled to `page_count` for existing rows: before this column there was no truncation
in practice (`truncated` was set only by the page cap, and no stored document had hit
it), so the two really were equal.

Revision ID: 0019_pages_read
Revises: 0018_evidence_file_texts
Create Date: 2026-08-24
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0019_pages_read"
down_revision: str | None = "0018_evidence_file_texts"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("evidence_file_texts", sa.Column("pages_read", sa.Integer(), nullable=True))
    op.execute("UPDATE evidence_file_texts SET pages_read = page_count WHERE pages_read IS NULL")
    op.alter_column("evidence_file_texts", "pages_read", nullable=False)
    op.create_check_constraint("ck_file_texts_pages_read", "evidence_file_texts", "pages_read >= 0")
    # A read cannot cover more pages than the document has.
    op.create_check_constraint(
        "ck_file_texts_pages_read_within_document",
        "evidence_file_texts",
        "pages_read <= page_count",
    )


def downgrade() -> None:
    op.drop_constraint("ck_file_texts_pages_read_within_document", "evidence_file_texts")
    op.drop_constraint("ck_file_texts_pages_read", "evidence_file_texts")
    op.drop_column("evidence_file_texts", "pages_read")
