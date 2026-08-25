"""evidence_travel_links: a document attached to a trip (Domain §11.9)

The table behind two invariants §11.8 has carried since M3B without one — "a travel record
may link to zero or more evidence items", and "a travel record without evidence may still be
user-confirmed but must expose its support state". See ADR-0021 for why it exists ahead of
`FactEvidenceLink` rather than waiting for it.

Three things enforced here rather than only in the service:

- **One live link per (trip, document).** A partial unique index scoped to
  `availability = 'AVAILABLE'`, so attaching the same document to the same trip twice is
  refused while re-attaching after a detach is allowed. Without the partial scope, a user
  who detached a booking could never attach it again.
- **`availability` is one of the §22.2 values.** A check constraint, because the whole
  point of the column is that it distinguishes *why* a link stopped counting, and a free
  string would let a fourth meaning appear without anyone deciding on it.
- **`unlinked_at` and availability agree.** `AVAILABLE` means no `unlinked_at`, and any
  other value requires one. The pair is what a historical assessment reads to say when
  support was withdrawn, and a row where they disagree can only mislead it.

The RLS policy predicates on this table's own `case_id` rather than joining through either
endpoint. The column is derivable and stored anyway: a policy that reached into
`travel_records` to find its tenant would be a policy whose correctness depended on another
table's policy. `tests/security/test_rls_coverage.py` derives its universe from any
`case_id` column, so this table joins that suite the moment this migration runs.

Both foreign keys are `ON DELETE CASCADE`-free deliberately. Case deletion is a command
(§51.1) that walks the case-scoped tables in order; a cascade would let a row vanish
without that command running, taking its provenance with it.

Revision ID: 0021_evidence_travel_links
Revises: 0020_text_consistency_constraint
Create Date: 2026-08-25
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0021_evidence_travel_links"
down_revision: str | None = "0020_text_consistency_constraint"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

APP_ROLE = "app_rls"
_TENANT = "current_setting('app.user_id', true)"
_DML = "SELECT, INSERT, UPDATE, DELETE"
_TABLE = "evidence_travel_links"

_POLICY = (
    "EXISTS (SELECT 1 FROM cases c "
    f"WHERE c.id = {_TABLE}.case_id AND c.owner_user_id = {_TENANT})"
)

_AVAILABILITY = ("AVAILABLE", "DELETED", "UNAVAILABLE")


def upgrade() -> None:
    rendered = ", ".join(f"'{value}'" for value in _AVAILABILITY)
    op.create_table(
        _TABLE,
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("case_id", sa.Uuid(), sa.ForeignKey("cases.id"), nullable=False),
        sa.Column(
            "travel_record_id", sa.Uuid(), sa.ForeignKey("travel_records.id"), nullable=False
        ),
        sa.Column(
            "evidence_item_id", sa.Uuid(), sa.ForeignKey("evidence_items.id"), nullable=False
        ),
        sa.Column("availability", sa.String(20), nullable=False),
        sa.Column("linked_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("unlinked_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(f"availability IN ({rendered})", name="ck_evidence_travel_links_avail"),
        sa.CheckConstraint(
            "(availability = 'AVAILABLE') = (unlinked_at IS NULL)",
            name="ck_evidence_travel_links_unlinked_at",
        ),
    )
    op.create_index(f"ix_{_TABLE}_case_id", _TABLE, ["case_id"])
    op.create_index(f"ix_{_TABLE}_travel_record_id", _TABLE, ["travel_record_id"])
    op.create_index(f"ix_{_TABLE}_evidence_item_id", _TABLE, ["evidence_item_id"])
    # Partial, so a detached link does not block re-attaching the same document later.
    op.create_index(
        f"uq_{_TABLE}_live",
        _TABLE,
        ["travel_record_id", "evidence_item_id"],
        unique=True,
        postgresql_where=sa.text("availability = 'AVAILABLE'"),
    )

    op.execute(f"GRANT {_DML} ON {_TABLE} TO {APP_ROLE}")
    op.execute(f"ALTER TABLE {_TABLE} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {_TABLE} FORCE ROW LEVEL SECURITY")
    op.execute(
        f"CREATE POLICY {_TABLE}_tenant ON {_TABLE} "
        f"FOR ALL USING ({_POLICY}) WITH CHECK ({_POLICY})"
    )


def downgrade() -> None:
    op.execute(f"DROP POLICY IF EXISTS {_TABLE}_tenant ON {_TABLE}")
    op.execute(f"ALTER TABLE {_TABLE} NO FORCE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {_TABLE} DISABLE ROW LEVEL SECURITY")
    op.execute(f"REVOKE {_DML} ON {_TABLE} FROM {APP_ROLE}")
    op.drop_table(_TABLE)
