"""outbox_events gains a trace id, a claim index, and a settled backlog

The outbox has been written since M2 with no reader (Domain §40). This is the migration
that makes it consumable.

Three changes, each with a reason:

- **`trace_id`.** `TraceIdMiddleware`'s docstring has always said a trace should "span
  the browser, the API, and the worker", and `UnitOfWork.emit` already stamps one onto
  the domain event and the audit entry. The outbox row was the gap, so the chain broke
  at exactly the hop M7 introduces.
- **A partial index on unpublished rows.** The relay's claim is
  `WHERE published_at IS NULL`, and the answer is a handful of rows against a table that
  only grows. Indexing the whole column would size the index to the history; indexing
  the predicate sizes it to the backlog.
- **The backlog is declared delivered.** Every row written between M2 and now is
  unpublished and unconsumable: no handler exists for any of those event types, and none
  can be written retroactively for a moment that has passed. Stamping them published is
  honest. Leaving them would hand the new relay a queue of work it must decline on every
  pass, forever, and would bury a genuinely undelivered row in the noise.

Revision ID: 0015_outbox_reader
Revises: 0014_evidence
Create Date: 2026-08-24
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0015_outbox_reader"
down_revision: str | None = "0014_evidence"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("outbox_events", sa.Column("trace_id", sa.String(length=64), nullable=True))

    # The relay claims with FOR UPDATE SKIP LOCKED against this predicate.
    op.create_index(
        "ix_outbox_events_unpublished",
        "outbox_events",
        ["created_at", "id"],
        postgresql_where=sa.text("published_at IS NULL"),
    )

    # One-time, and deliberately not idempotent-on-rerun in any meaningful sense: it
    # stamps whatever is unpublished at the moment it runs, which on a fresh database is
    # nothing and on an existing one is the M2-to-M7 backlog.
    op.execute("UPDATE outbox_events SET published_at = now() WHERE published_at IS NULL")


def downgrade() -> None:
    op.drop_index("ix_outbox_events_unpublished", table_name="outbox_events")
    op.drop_column("outbox_events", "trace_id")
