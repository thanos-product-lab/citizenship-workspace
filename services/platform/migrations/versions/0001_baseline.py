"""baseline — establishes alembic_version only

Domain tables begin at M2. This empty revision exists so the migration chain has
a root and ``alembic upgrade head`` is meaningful from day one.

Revision ID: 0001_baseline
Revises:
Create Date: 2026-07-24
"""

from collections.abc import Sequence

revision: str = "0001_baseline"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
