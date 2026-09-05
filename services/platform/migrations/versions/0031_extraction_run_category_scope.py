"""Only a classifier run names a category

`0027` gave `extraction_runs` this constraint:

    (classified_category IS NOT NULL) = (status IN ('SUCCEEDED','ABSTAINED'))

It read as *"a settled run says what it concluded"*, which was true when the only
capability writing a run was `DocumentClassifier` and a conclusion was category-shaped
by definition.

M8 slice 3a adds `TravelRecordExtractor`, whose runs settle `SUCCEEDED` and conclude
nothing about a category — what they conclude is a set of claims, in another table. So
every successful extraction violated a constraint asserting a classifier-specific
property of every capability's run, and the whole travel path failed at the insert.

The constraint was doing its job: it refused a row whose columns did not mean what the
schema said they meant. What was wrong was the schema's claim, which had generalised
from one capability to all of them without anyone deciding to.

Scoped rather than relaxed. `classified_category IS NULL` is now *required* of every
non-classifier run — a travel extraction that somehow set one would be a run claiming a
finding it is not capable of making, and dropping the constraint instead of narrowing it
would have permitted exactly that.

Revision ID: 0031_run_category_scope
Revises: 0030_claims_and_facts
Create Date: 2026-09-05
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0031_run_category_scope"
down_revision: str | None = "0030_claims_and_facts"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE = "extraction_runs"
_NAME = "ck_extraction_runs_category_matches_status"

_SCOPED = (
    "(classified_category IS NOT NULL) = "
    "(capability = 'DocumentClassifier' AND status IN ('SUCCEEDED', 'ABSTAINED'))"
)
_OLD = "(classified_category IS NOT NULL) = (status IN ('SUCCEEDED', 'ABSTAINED'))"


def upgrade() -> None:
    op.drop_constraint(_NAME, _TABLE, type_="check")
    op.create_check_constraint(_NAME, _TABLE, _SCOPED)


def downgrade() -> None:
    op.drop_constraint(_NAME, _TABLE, type_="check")
    op.create_check_constraint(_NAME, _TABLE, _OLD)
