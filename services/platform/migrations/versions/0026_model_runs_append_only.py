"""model_runs is append-only: take back the UPDATE grant 0025 handed out

0025 granted `SELECT, INSERT, UPDATE` on both AI tables and revoked only `DELETE`. That
is right for `ai_daily_spend`, which is a read-modify-write row by design. It is wrong
for `model_runs`, which nothing in the application ever updates — `ai/service.py` only
adds and flushes, and the table has no `updated_at`.

The gap it left is the assessment-immutability principle applied to telemetry: with
`UPDATE`, the request role could rewrite the cost, the status or the `output_hash` on a
historical invocation record. Provenance a request path can rewrite is not provenance,
and 0025's own comment — "a ledger the request role can erase is not a ledger" — was
making exactly that argument while granting the privilege that undoes it.

Found by review, not by a failure. Noted while here: the ledger write path opens its own
session and never calls `set_tenant`, so it runs as the table owner rather than as
`app_rls`. These grants therefore constrain request paths rather than the ledger itself —
still worth having as defence in depth, and narrower than 0025's comment implies.

Revision ID: 0026_model_runs_append_only
Revises: 0025_model_runs
Create Date: 2026-09-02
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0026_model_runs_append_only"
down_revision: str | None = "0025_model_runs"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

APP_ROLE = "app_rls"


def upgrade() -> None:
    op.execute(f"REVOKE UPDATE ON model_runs FROM {APP_ROLE}")


def downgrade() -> None:
    op.execute(f"GRANT UPDATE ON model_runs TO {APP_ROLE}")
