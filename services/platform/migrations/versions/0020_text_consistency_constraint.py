"""Correct the consistency check between character_count and content

`0018` asserted `(character_count = 0) = (length(content) = 0)`, which was true only
because `character_count` was then computed as `len("\\n".join(pages))` — a bug. Joining
N empty pages yields N-1 newlines, so a three-page scan reported two characters of text,
`has_text_layer` came out True, and the user was told **"Read — the text has been read"**
about a document nothing was read from.

Fixing the count broke the constraint, which is the constraint doing its job: it was
pinning the relationship the bug produced. `character_count` is now the number of
characters that came out of the pages, while `content` is those pages joined with
newlines — so a document with no text has `character_count = 0` and a `content` of
nothing but separators.

The check that is actually true, and worth keeping: **no text means no text**. A reading
that claims zero characters must not carry anything but whitespace, and one that claims
characters must have some.

Revision ID: 0020_text_consistency_constraint
Revises: 0019_pages_read
Create Date: 2026-08-24
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0020_text_consistency_constraint"
down_revision: str | None = "0019_pages_read"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE = "evidence_file_texts"
_OLD = "ck_file_texts_count_matches_content"
_NEW = "ck_file_texts_no_text_means_no_text"


def upgrade() -> None:
    op.drop_constraint(_OLD, _TABLE, type_="check")
    # A whitespace-class regex rather than `btrim`, whose one-argument form trims only
    # spaces — and the whitespace that matters here is exactly the newlines that join
    # empty pages together.
    op.create_check_constraint(_NEW, _TABLE, "(character_count = 0) = (content ~ '^[[:space:]]*$')")


def downgrade() -> None:
    op.drop_constraint(_NEW, _TABLE, type_="check")
    op.create_check_constraint(_OLD, _TABLE, "(character_count = 0) = (length(content) = 0)")
