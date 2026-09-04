"""Every status the code can produce, the database can store.

This file exists because of a bug that shipped green. M8 slice 2's review pass added
`ExtractionRunStatus.REFUSED_QUOTA` to the Python enum and to no migration, so
`ck_extraction_runs_status` — which enumerates its values — rejected it. A case reaching
its daily limit would have raised `IntegrityError` inside `_analyse`, fallen through to
the worker's catch-all, and abandoned the document with *"Something went wrong reading
this file. You can try again"*: false twice over, since nothing was wrong with the file
and trying again would not have helped. A cost control that breaks the pipeline instead
of refusing gracefully is worse than none.

**Why the existing tests missed it.** They asserted the object `classify` returns, and
never wrote it. An in-memory dataclass has no opinion about a CHECK constraint. So the
tests here do the one thing those did not: they put a row in the table.
"""

import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.ai.extraction_run import (
    PRE_DIAL_REFUSALS,
    PRODUCTIVE_STATUSES,
    SUMMARY_FOR_STATUS,
    ExtractionRun,
    ExtractionRunStatus,
)

pytestmark = pytest.mark.integration


def _chain(session: Session) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID, uuid.UUID]:
    """A real case, document and processing run — the foreign keys and the row-level
    policy both require the run to name rows that exist and belong to this tenant."""
    from app.cases.domain import ApplicationCase
    from app.evidence.domain import (
        PIPELINE_VERSION,
        EvidenceCategory,
        EvidenceFile,
        EvidenceItem,
        EvidenceProcessingRun,
        ProcessingRunStatus,
    )

    case = ApplicationCase.create(owner_user_id="user_a", title="Statuses")
    session.add(case)
    session.flush()

    item = EvidenceItem.uploaded(
        case_id=case.id,
        category=EvidenceCategory.TRAVEL_SUPPORT,
        display_name="A document",
        created_by="user_a",
    )
    session.add(item)
    session.flush()

    file = EvidenceFile(
        evidence_item_id=item.id,
        storage_key=f"k/{uuid.uuid4()}",
        original_filename="doc.pdf",
        media_type="application/pdf",
        size_bytes=1024,
        checksum="x" * 64,
        version_number=1,
        uploaded_at=datetime.now(UTC),
    )
    session.add(file)
    session.flush()

    run = EvidenceProcessingRun(
        evidence_item_id=item.id,
        evidence_file_id=file.id,
        status=ProcessingRunStatus.SUCCEEDED.value,
        pipeline_version=PIPELINE_VERSION,
        completed_at=datetime.now(UTC),
        idempotency_key=f"statuses-{uuid.uuid4()}",
    )
    session.add(run)
    session.flush()
    return case.id, item.id, file.id, run.id


@pytest.mark.parametrize("status", list(ExtractionRunStatus))
def test_every_status_can_actually_be_written(
    db_session: Session, status: ExtractionRunStatus
) -> None:
    """The assertion the original quota was missing.

    Parametrised over the enum rather than over a hand-written list, so a status added in
    a later slice is covered the moment it exists — which is the only arrangement that
    would have caught the one that was not.
    """
    case_id, item_id, file_id, run_id = _chain(db_session)

    db_session.add(
        ExtractionRun.record(
            case_id=case_id,
            evidence_item_id=item_id,
            evidence_file_id=file_id,
            processing_run_id=run_id,
            capability="DocumentClassifier",
            status=status,
            input_text="synthetic",
            started_at=datetime.now(UTC),
            # The category constraint ties its presence to the status: a run that
            # concluded something says what, and a refusal says nothing.
            classified_category="TRAVEL_SUPPORT" if status in PRODUCTIVE_STATUSES else None,
        )
    )
    db_session.flush()


def test_the_database_accepts_exactly_the_statuses_the_enum_defines(db_session: Session) -> None:
    """Both directions. The test above catches a status the constraint rejects; this one
    also catches a value the constraint still permits after the enum dropped it, which is
    how a dead status lingers in production data nothing can any longer produce."""
    definition = str(
        db_session.execute(
            text(
                "SELECT pg_get_constraintdef(oid) FROM pg_constraint "
                "WHERE conname = 'ck_extraction_runs_status'"
            )
        ).scalar_one()
    )
    quoted = {value for value in ExtractionRunStatus}
    for status in quoted:
        assert f"'{status.value}'" in definition, f"{status.value} is not in the constraint"

    # Nothing in the constraint that is not in the enum. Parsed rather than assumed,
    # because a stale value is invisible until someone reads the DDL.
    import re

    in_sql = set(re.findall(r"'([A-Z_]+)'::character varying", definition))
    assert in_sql == {s.value for s in quoted}, (
        f"the constraint and the enum disagree: only in SQL {in_sql - {s.value for s in quoted}}, "
        f"only in Python {{s.value for s in quoted}} - in_sql"
    )


def test_the_pre_dial_refusals_agree_with_the_constraint(db_session: Session) -> None:
    """`PRE_DIAL_REFUSALS` and migration 0029 say the same thing in two languages. A run
    refused before any provider call has no `ModelRun`, and the constraint enforces it —
    so the Python set drifting from the SQL one would let a refusal claim a call that
    never happened."""
    definition = str(
        db_session.execute(
            text(
                "SELECT pg_get_constraintdef(oid) FROM pg_constraint "
                "WHERE conname = 'ck_extraction_runs_refusal_has_no_model_run'"
            )
        ).scalar_one()
    )
    for status in PRE_DIAL_REFUSALS:
        assert f"'{status.value}'" in definition, (
            f"{status.value} is a pre-dial refusal in Python but not in the constraint"
        )
    assert set(ExtractionRunStatus) - PRODUCTIVE_STATUSES >= PRE_DIAL_REFUSALS


def test_a_pre_dial_refusal_cannot_claim_a_model_run(db_session: Session) -> None:
    """The behavioural half. A refusal that named a `ModelRun` would be a call that never
    happened, carrying a cost, in a table the ceiling reads."""
    from sqlalchemy.exc import IntegrityError

    case_id, item_id, file_id, run_id = _chain(db_session)
    db_session.add(
        ExtractionRun.record(
            case_id=case_id,
            evidence_item_id=item_id,
            evidence_file_id=file_id,
            processing_run_id=run_id,
            capability="DocumentClassifier",
            status=ExtractionRunStatus.REFUSED_USER_QUOTA,
            input_text="synthetic",
            started_at=datetime.now(UTC),
            model_run_id=uuid.uuid4(),
        )
    )
    with pytest.raises(IntegrityError):
        db_session.flush()
    db_session.rollback()


def test_every_refusal_tells_the_user_something_different(db_session: Session) -> None:
    """Three limits, three causes, three remedies. "This case has had its share", "you
    have had your share" and "nobody gets any more today" are different sentences, and
    giving someone the last when the first is true blames the system for their own loop."""
    sentences = {
        status: SUMMARY_FOR_STATUS[status]
        for status in (
            ExtractionRunStatus.REFUSED_QUOTA,
            ExtractionRunStatus.REFUSED_USER_QUOTA,
            ExtractionRunStatus.REFUSED_NO_BUDGET,
        )
    }
    assert len(set(sentences.values())) == 3, "two refusals say the same thing"
    assert "this case" in sentences[ExtractionRunStatus.REFUSED_QUOTA].casefold()
    assert "your cases" in sentences[ExtractionRunStatus.REFUSED_USER_QUOTA].casefold()
    for sentence in sentences.values():
        assert "read and stored" in sentence, "a refusal must say what survived"
