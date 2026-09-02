"""model_runs and ai_daily_spend: the record of every model invocation, and its ceiling

Technical Architecture RFC §20. Two tables, both **deliberately outside the tenant**,
which is the decision this migration is really about.

`model_runs` carries no `case_id`. RFC §8's `ExtractionRun` (slice 2) is the
case-scoped record of "capability X ran against evidence file Y"; this is the
telemetry of one invocation, and the two are not the same row because a single
extraction that retries makes several invocations and the ceiling has to see all of
them. Keeping the case off it means it has no tenant dimension — so RLS here would
be wrong rather than missing — and means it needs no handling in the case-deletion
path, which is right for a table that by construction holds nothing about a person.

That is also why both tables are added to a new `NON_TENANT_TELEMETRY` list in
`tests/security/test_rls_coverage.py` rather than to `UNPROTECTED_INFRASTRUCTURE`.
The latter is ADR-0006 R3's list of *gaps* — tables that should have a policy and do
not. These should not have one, and filing them under "gap" would put two different
claims in one list and lose the distinction the day someone closes R3.

**There is no column into which a prompt, a document, or a model payload could be
written.** `output_hash` is a digest; `failure_class` is an exception class name, not
its message, because a provider error message can quote the request body and the
request body is the document. Architecture §20's *"do not store sensitive document
content in telemetry"* is enforced by the table's shape, not by a redaction step
someone has to remember. `tests/ai/test_model_run_shape.py` asserts the column list.

`ai_daily_spend` is one row per UTC day, and exists as a lockable object rather than
as `SUM(estimated_cost_usd)` over `model_runs`: `SELECT ... FOR UPDATE` on one row is
what stops two workers reading the same total and each writing it back as though the
other had not spent. It also survives a retention prune of `model_runs`, which a
running total over a table that might be trimmed would not.

Revision ID: 0025_model_runs
Revises: 0024_travel_consistency_v2_1
Create Date: 2026-09-02
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0025_model_runs"
down_revision: str | None = "0024_travel_consistency_v2_1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

APP_ROLE = "app_rls"

_STATUSES = (
    "SUCCEEDED",
    "REFUSED",
    "INVALID_OUTPUT",
    "FAILED",
    "TERMINAL",
    "TIMED_OUT",
    "SPEND_CEILING_REACHED",
)


def upgrade() -> None:
    op.create_table(
        "model_runs",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("capability", sa.String(40), nullable=False),
        sa.Column("provider", sa.String(30), nullable=False),
        sa.Column("model", sa.String(80), nullable=False),
        sa.Column("prompt_version", sa.String(60), nullable=False),
        sa.Column("schema_version", sa.String(60), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("latency_ms", sa.Integer(), nullable=False),
        sa.Column("input_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("output_tokens", sa.Integer(), nullable=False, server_default="0"),
        # Numeric, not float: this is summed into a ledger a ceiling reads, and
        # binary floating point accumulating thousands of small costs is a rounding
        # argument nobody should have to have.
        sa.Column(
            "estimated_cost_usd", sa.Numeric(12, 8), nullable=False, server_default="0"
        ),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("trace_id", sa.String(64), nullable=True),
        sa.Column("output_hash", sa.String(64), nullable=True),
        sa.Column("failure_class", sa.String(80), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.CheckConstraint(
            "status IN " + str(_STATUSES), name="ck_model_runs_status"
        ),
        # A negative cost is a price-table or arithmetic error being accumulated into
        # a budget as a credit, which would raise the effective ceiling silently.
        sa.CheckConstraint("estimated_cost_usd >= 0", name="ck_model_runs_cost_non_negative"),
        # Zero attempts is meaningful and only meaningful in one case: the call was
        # refused before dialling because the day's ceiling was spent. Encoding that
        # as a constraint rather than `attempts >= 1` keeps "never dialled" and
        # "dialled and failed" structurally distinguishable — otherwise a reader
        # counting attempts cannot tell a ceiling refusal from a call that failed on
        # its first try, and those are different operational stories.
        sa.CheckConstraint(
            "(status = 'SPEND_CEILING_REACHED' AND attempts = 0) "
            "OR (status <> 'SPEND_CEILING_REACHED' AND attempts >= 1)",
            name="ck_model_runs_attempts_match_status",
        ),
    )
    op.create_index("ix_model_runs_capability", "model_runs", ["capability"])
    op.create_index("ix_model_runs_status", "model_runs", ["status"])
    op.create_index("ix_model_runs_trace_id", "model_runs", ["trace_id"])
    op.create_index("ix_model_runs_created_at", "model_runs", ["created_at"])

    op.create_table(
        "ai_daily_spend",
        sa.Column("day", sa.Date(), primary_key=True),
        sa.Column("spent_usd", sa.Numeric(12, 8), nullable=False, server_default="0"),
        sa.Column("calls", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.CheckConstraint("spent_usd >= 0", name="ck_ai_daily_spend_non_negative"),
    )

    # Both tables are written from request and task paths, which run as `app_rls`.
    # 0004's ALTER DEFAULT PRIVILEGES already grants this; stated explicitly so the
    # intent is legible rather than inherited, and so a future tightening of the
    # default privileges does not silently break the ledger.
    for table in ("model_runs", "ai_daily_spend"):
        op.execute(f"GRANT SELECT, INSERT, UPDATE ON {table} TO {APP_ROLE}")
    # No DELETE: nothing in the application removes a spend record. Retention, if it
    # ever exists, is a migration or an operator task — not something a request path
    # can reach, because a ledger the request role can erase is not a ledger.
    for table in ("model_runs", "ai_daily_spend"):
        op.execute(f"REVOKE DELETE ON {table} FROM {APP_ROLE}")


def downgrade() -> None:
    op.drop_table("ai_daily_spend")
    op.drop_index("ix_model_runs_created_at", table_name="model_runs")
    op.drop_index("ix_model_runs_trace_id", table_name="model_runs")
    op.drop_index("ix_model_runs_status", table_name="model_runs")
    op.drop_index("ix_model_runs_capability", table_name="model_runs")
    op.drop_table("model_runs")
