"""The trip's reason, on the stable travel record

A nullable `reason` on `travel_records`, not on `travel_record_versions`. No rule reads it,
so it is an annotation for the travel export rather than an assessed input, and a version
column would make every reason typed in append a version and stale the residence results
(ADR-0035). Additive: existing trips simply have no reason.

The length is a literal snapshot of `REASON_MAX_LENGTH`, by the same convention as the
destination label.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0038_travel_record_reason"
down_revision: str | None = "0037_standard_route_v1_1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("travel_records", sa.Column("reason", sa.String(length=200), nullable=True))


def downgrade() -> None:
    op.drop_column("travel_records", "reason")
