"""extraction_runs: admit the two quota refusals its status constraint rejects

**A bug fix before it is a feature.** M8 slice 2's review pass added
`ExtractionRunStatus.REFUSED_QUOTA` — the per-case daily limit — to the Python enum and
to no migration. `0027`'s `ck_extraction_runs_status` enumerates five values, so a run
carrying the sixth could not be written at all.

That was not a cosmetic omission. The refusal is constructed in
`classification_service.classify` and persisted by `_analyse` via `session.add`, so a
case reaching its limit would have raised `IntegrityError` inside the pipeline, fallen
through to the worker's catch-all, and abandoned the document with *"Something went
wrong reading this file. You can try again."* — a sentence that is false twice over:
nothing went wrong with the file, and trying again would not have helped.

A cost control that breaks the pipeline instead of gracefully refusing is worse than no
cost control, and it is the same false-reassurance shape the quota was added to prevent,
reintroduced by the fix. It shipped green because the test asserted the returned object
and never wrote it — the lesson recorded in
`tests/ai/test_extraction_run_statuses.py`, which now persists one row of every status
so the enum and the constraint cannot drift again.

**And the feature.** `REFUSED_USER_QUOTA` is the per-*user* limit. Nothing bounds how
many cases a person opens, so the per-case limit of 200 multiplied by an unbounded
number of cases does not bound a user — which is the gap the case limit alone left, and
the reason a single account could still exhaust the deployment's daily ceiling and stop
every other tenant's processing until midnight.

Revision ID: 0029_refusal_statuses
Revises: 0028_extraction_runs_hardening
Create Date: 2026-09-04
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0029_refusal_statuses"
down_revision: str | None = "0028_extraction_runs_hardening"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE = "extraction_runs"

_STATUSES = (
    "SUCCEEDED",
    "ABSTAINED",
    "FAILED",
    "REFUSED_NO_BUDGET",
    "REFUSED_NO_TIME",
    "REFUSED_QUOTA",
    "REFUSED_USER_QUOTA",
)
_OLD_STATUSES = ("SUCCEEDED", "ABSTAINED", "FAILED", "REFUSED_NO_BUDGET", "REFUSED_NO_TIME")

#: Refusals decided before any provider call, so they can carry no `ModelRun`. Mirrors
#: `PRE_DIAL_REFUSALS` in `app/ai/extraction_run.py`; the two are asserted equal by
#: `tests/ai/test_extraction_run_statuses.py` rather than merely written twice.
_PRE_DIAL = ("REFUSED_NO_BUDGET", "REFUSED_NO_TIME", "REFUSED_QUOTA", "REFUSED_USER_QUOTA")
_OLD_PRE_DIAL = ("REFUSED_NO_BUDGET", "REFUSED_NO_TIME")


def upgrade() -> None:
    op.drop_constraint("ck_extraction_runs_status", _TABLE, type_="check")
    op.create_check_constraint("ck_extraction_runs_status", _TABLE, f"status IN {_STATUSES}")

    op.drop_constraint("ck_extraction_runs_refusal_has_no_model_run", _TABLE, type_="check")
    op.create_check_constraint(
        "ck_extraction_runs_refusal_has_no_model_run",
        _TABLE,
        f"model_run_id IS NULL OR status NOT IN {_PRE_DIAL}",
    )

    # `(classified_category IS NOT NULL) = (status IN ('SUCCEEDED','ABSTAINED'))` is
    # unchanged and still correct: a refusal concluded nothing, so it names no category.


def downgrade() -> None:
    op.drop_constraint("ck_extraction_runs_refusal_has_no_model_run", _TABLE, type_="check")
    op.create_check_constraint(
        "ck_extraction_runs_refusal_has_no_model_run",
        _TABLE,
        f"model_run_id IS NULL OR status NOT IN {_OLD_PRE_DIAL}",
    )
    op.drop_constraint("ck_extraction_runs_status", _TABLE, type_="check")
    op.create_check_constraint("ck_extraction_runs_status", _TABLE, f"status IN {_OLD_STATUSES}")
