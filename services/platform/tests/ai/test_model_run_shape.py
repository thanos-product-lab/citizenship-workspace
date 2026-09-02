"""`model_runs` has no column a payload could be written into.

Architecture §20: *"Do not store sensitive document content in telemetry."* The
guarantee is the table's shape, not a redaction step someone has to remember, and
this is the assertion that keeps it that way — the mutation it exists to catch is
adding a `payload`, `prompt`, `response` or `document_text` column because it would
have been convenient for debugging.

CLAUDE.md §11: *"Model-run records store metadata + output hash only."*
"""

import inspect

from sqlalchemy import inspect as sa_inspect
from sqlalchemy.orm import Session

from app.ai import provider, service
from app.ai.domain import AiDailySpend, ModelRun

#: Every column `model_runs` is permitted to have. Not a prefix check or a
#: denylist — an exact set, because a denylist only catches the names someone thought
#: of, and the whole risk is a column nobody thought to forbid.
PERMITTED_COLUMNS = {
    "id",
    "capability",
    "provider",
    "model",
    "prompt_version",
    "schema_version",
    "status",
    "latency_ms",
    "input_tokens",
    "output_tokens",
    "estimated_cost_usd",
    "attempts",
    "trace_id",
    "output_hash",
    "failure_class",
    "created_at",
}


def test_model_runs_has_exactly_the_permitted_columns() -> None:
    actual = {c.name for c in ModelRun.__table__.columns}
    assert actual == PERMITTED_COLUMNS, (
        f"model_runs columns changed: added {sorted(actual - PERMITTED_COLUMNS)}, "
        f"removed {sorted(PERMITTED_COLUMNS - actual)}. A column here is a place "
        "document content can come to rest — if the addition is genuinely metadata, "
        "add it to PERMITTED_COLUMNS deliberately."
    )


def test_neither_ai_table_carries_a_case() -> None:
    """The design decision migration 0025 spells out. If a `case_id` ever appears
    here, these tables become case-scoped — which means they need an RLS policy, need
    handling in the case-deletion path, and stop being a deployment-wide ledger."""
    for model in (ModelRun, AiDailySpend):
        table = model.__table__
        assert "case_id" not in {c.name for c in table.columns}
        assert table.foreign_keys == set(), (
            f"{model.__tablename__} gained a foreign key. A link to a case-scoped table makes "
            "it reachable from `cases` and therefore case-scoped by the derivation in "
            "tests/security/test_rls_coverage.py."
        )


def test_the_run_record_is_never_given_the_document_or_the_prompt() -> None:
    """A structural read of the one function that writes these rows.

    The column check above catches a new column. This catches the other half: a
    prompt or document being stuffed into an existing string column — `failure_class`
    is the tempting one, because a provider's error message often quotes the request.
    """
    source = inspect.getsource(service.invoke)
    for forbidden in ("document=document,\n            provider=", "system.text", "str(document)"):
        assert forbidden not in source.replace("        ", ""), (
            f"`invoke` passes {forbidden!r} into the ModelRun record"
        )


def test_the_provider_records_an_exception_class_never_its_message() -> None:
    """A provider error message can quote the request body, and the request body is
    the document. `type(exc).__name__`, never `str(exc)`."""
    source = inspect.getsource(provider.OpenAIProvider.generate_structured)
    assert "failure_class = type(exc).__name__" in source
    assert "failure_class = str(exc)" not in source


def test_the_failure_log_names_the_class_and_not_the_error(db_session: Session) -> None:
    """The same rule at the logging boundary, where it is easiest to break: a
    `error=str(exc)` in a warning is a document fragment in a log aggregator."""
    source = inspect.getsource(provider.OpenAIProvider.generate_structured)
    log_call = source[source.index("_log.warning(") : source.index("if terminal:")]
    assert "failure_class=failure_class" in log_call
    assert "str(exc)" not in log_call and "exc)" not in log_call.replace("type(exc)", "")


def test_the_orm_model_matches_the_migrated_table(db_session: Session) -> None:
    """The ORM and the database agree. Cheap, and it catches the case where a column
    is added to the model and the migration is forgotten — at which point the shape
    assertion above passes while production has a different table."""
    live = {c["name"] for c in sa_inspect(db_session.get_bind()).get_columns("model_runs")}
    assert live == {c.name for c in ModelRun.__table__.columns}
