"""extraction_runs: one AI capability invocation against one evidence file version

`EVIDENCE_AND_CLAIM_LIFECYCLE_RFC.md` §8, with the provider/cost/latency columns
replaced by `model_run_id` — **ADR-0025** records why: copying them would give two
tables different answers the first time a call retried, and would put a
deployment-wide accounting figure inside a case-scoped, user-deletable row.

**The foreign key direction is load-bearing.** `extraction_runs` (child) references
`model_runs` (parent), never the reverse. `tests/security/test_rls_coverage.py`
derives the case-scoped set as the transitive closure of child→parent edges from
`cases`; a parent is pulled in only if it is itself a child of something reachable.
Reversing this key would make `model_runs` case-scoped, which would demand an RLS
policy on the spend ledger and put it in the case-deletion path — a user action could
then erase spending history and lower the effective ceiling.

This table *is* case-scoped and takes the usual policy, predicated through
`evidence_items` — the same grandchild shape as `evidence_processing_runs` and
`evidence_files`.

**No document text.** `input_hash` is a digest and `input_characters` a count, which
together distinguish a truncated reading from a whole one without this table holding
content. `classification_reasoning` is the one free-text column, bounded at 300
characters in the schema and again here, because it is model-controlled output that
reaches a screen.

Revision ID: 0027_extraction_runs
Revises: 0026_model_runs_append_only
Create Date: 2026-09-02
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0027_extraction_runs"
down_revision: str | None = "0026_model_runs_append_only"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

APP_ROLE = "app_rls"
_TENANT = "current_setting('app.user_id', true)"
_DML = "SELECT, INSERT, UPDATE, DELETE"

_TABLE = "extraction_runs"
_PREDICATE = (
    "EXISTS (SELECT 1 FROM evidence_items e JOIN cases c ON c.id = e.case_id "
    f"WHERE e.id = {_TABLE}.evidence_item_id AND c.owner_user_id = {_TENANT})"
)

_STATUSES = ("SUCCEEDED", "ABSTAINED", "FAILED", "REFUSED_NO_BUDGET", "REFUSED_NO_TIME")
_CATEGORIES = (
    "IMMIGRATION_STATUS",
    "ENGLISH_LANGUAGE",
    "LIFE_IN_THE_UK",
    "TRAVEL_SUPPORT",
    "UNSUPPORTED",
    "AMBIGUOUS",
)


def upgrade() -> None:
    op.create_table(
        _TABLE,
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("case_id", sa.Uuid(), sa.ForeignKey("cases.id"), nullable=False),
        sa.Column(
            "evidence_item_id", sa.Uuid(), sa.ForeignKey("evidence_items.id"), nullable=False
        ),
        sa.Column(
            "evidence_file_id", sa.Uuid(), sa.ForeignKey("evidence_files.id"), nullable=False
        ),
        sa.Column(
            "processing_run_id",
            sa.Uuid(),
            sa.ForeignKey("evidence_processing_runs.id"),
            nullable=False,
        ),
        # Nullable: an invocation refused before it was made — the spend ceiling, or the
        # task deadline — still needs a run to record that nothing happened and why.
        sa.Column("model_run_id", sa.Uuid(), sa.ForeignKey("model_runs.id"), nullable=True),
        sa.Column("capability", sa.String(length=40), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("input_hash", sa.String(length=64), nullable=False),
        sa.Column("input_characters", sa.Integer(), nullable=False),
        sa.Column("classified_category", sa.String(length=30), nullable=True),
        sa.Column("classification_confidence", sa.Float(), nullable=True),
        sa.Column("classification_reasoning", sa.String(length=300), nullable=True),
        sa.Column(
            "started_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("status IN " + str(_STATUSES), name="ck_extraction_runs_status"),
        sa.CheckConstraint(
            "classified_category IS NULL OR classified_category IN " + str(_CATEGORIES),
            name="ck_extraction_runs_category",
        ),
        # Confidence is display metadata, and a value outside 0..1 is arithmetic or a
        # provider surprise rather than a measurement — worth rejecting at the boundary
        # so nothing downstream has to decide what 1.4 means.
        sa.CheckConstraint(
            "classification_confidence IS NULL "
            "OR (classification_confidence >= 0 AND classification_confidence <= 1)",
            name="ck_extraction_runs_confidence_range",
        ),
        # A run that produced an answer names it; one that did not must not appear to.
        # This is the constraint that stops a FAILED run carrying a category nobody
        # concluded, which would read downstream as a classification.
        sa.CheckConstraint(
            "(classified_category IS NOT NULL) = (status IN ('SUCCEEDED', 'ABSTAINED'))",
            name="ck_extraction_runs_category_matches_status",
        ),
        # A refusal happened before any provider call, so it has no model run. The
        # converse is not asserted: a FAILED run may or may not have reached one.
        sa.CheckConstraint(
            "model_run_id IS NULL "
            "OR status NOT IN ('REFUSED_NO_BUDGET', 'REFUSED_NO_TIME')",
            name="ck_extraction_runs_refusal_has_no_model_run",
        ),
    )
    op.create_index(f"ix_{_TABLE}_case_id", _TABLE, ["case_id"])
    op.create_index(f"ix_{_TABLE}_evidence_item_id", _TABLE, ["evidence_item_id"])
    op.create_index(f"ix_{_TABLE}_processing_run_id", _TABLE, ["processing_run_id"])
    op.create_index(f"ix_{_TABLE}_capability", _TABLE, ["capability"])
    op.create_index(f"ix_{_TABLE}_status", _TABLE, ["status"])

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
    op.drop_table(_TABLE)
