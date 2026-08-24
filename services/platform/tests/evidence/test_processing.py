"""Validation in the worker: what it concludes, and what it refuses to do twice.

The four properties §4 of the M7 plan names, each as its own test:

- a duplicate delivery creates no duplicate processing output;
- a processing failure never deletes the uploaded evidence;
- transient and terminal failures are treated differently;
- a user is shown a domain state, never a queue state.
"""

import uuid
from collections.abc import Callable

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.storage import InMemoryStorage, StorageError, get_storage
from app.evidence import processing
from app.evidence.domain import (
    PROCESSING_STATUS_FOR_RUN,
    EvidenceFile,
    EvidenceItem,
    EvidenceProcessingRun,
    EvidenceProcessingStatus,
    ProcessingFailureCode,
    ProcessingRunStatus,
)
from tests.security.conftest import SUPPORTED_ANSWERS

pytestmark = pytest.mark.integration

Api = Callable[[str], TestClient]

_PDF = b"%PDF-1.7 a synthetic, fictional document"
_NOT_A_PDF = b"MZ\x90\x00 this is a windows executable"


def _store() -> InMemoryStorage:
    store = get_storage()
    assert isinstance(store, InMemoryStorage)
    return store


def _uploaded(api: Api, user: str, *, content: bytes = _PDF) -> uuid.UUID:
    case_id = str(api(user).post("/api/v1/cases", json={"title": "Processing"}).json()["id"])
    api(user).put(f"/api/v1/cases/{case_id}/route-profile", json=SUPPORTED_ANSWERS)
    api(user).post(f"/api/v1/cases/{case_id}/route-profile/confirm", json={})

    grant = (
        api(user)
        .post(
            f"/api/v1/cases/{case_id}/evidence/uploads",
            json={"media_type": "application/pdf", "declared_size_bytes": len(content)},
        )
        .json()
    )
    _store().put(str(grant["upload_fields"]["key"]), content)
    item = (
        api(user)
        .post(
            f"/api/v1/cases/{case_id}/evidence",
            json={
                "upload_token": grant["upload_token"],
                "category": "TRAVEL_SUPPORT",
                "display_name": "A document",
                "original_filename": "doc.pdf",
            },
        )
        .json()
    )
    return uuid.UUID(item["id"])


def _runs(session: Session, evidence_item_id: uuid.UUID) -> list[EvidenceProcessingRun]:
    stmt = select(EvidenceProcessingRun).where(
        EvidenceProcessingRun.evidence_item_id == evidence_item_id
    )
    return list(session.execute(stmt).scalars().all())


# --- what validation concludes -------------------------------------------------------


def test_a_real_pdf_validates_and_returns_to_uploaded(api: Api, db_session: Session) -> None:
    """`UPLOADED` after a successful validation is the honest state in this slice: the
    file is stored, it has been checked, and nothing has read its contents — which is
    exactly what the library already tells the user."""
    item_id = _uploaded(api, "user_a")

    outcome = processing.validate_evidence(
        db_session, _store(), evidence_item_id=item_id, idempotency_key="k1", trace_id=None
    )

    assert outcome.processing_status is EvidenceProcessingStatus.UPLOADED
    assert outcome.failure_code is None
    runs = _runs(db_session, item_id)
    assert [r.run_status for r in runs] == [ProcessingRunStatus.SUCCEEDED]


def test_content_that_contradicts_its_declared_type_is_unsupported(
    api: Api, db_session: Session
) -> None:
    """The presigned policy binds the *declared* type into the signature, so a client
    cannot upload under a different label — but it still controls the bytes. This is
    where a `.exe` called `application/pdf` is caught, and it needs the content, which is
    why it is in the worker."""
    item_id = _uploaded(api, "user_a", content=_NOT_A_PDF)

    outcome = processing.validate_evidence(
        db_session, _store(), evidence_item_id=item_id, idempotency_key="k1", trace_id=None
    )

    assert outcome.processing_status is EvidenceProcessingStatus.UNSUPPORTED
    assert outcome.failure_code is ProcessingFailureCode.CONTENT_DOES_NOT_MATCH_TYPE


def test_the_refusal_is_phrased_in_the_users_vocabulary(api: Api, db_session: Session) -> None:
    """A failure summary is read by someone wondering why their document was refused.
    Answering with a MIME type answers in a vocabulary they did not choose — and the
    first version read "not a application/pdf document", which is also ungrammatical."""
    item_id = _uploaded(api, "user_a", content=_NOT_A_PDF)

    processing.validate_evidence(
        db_session, _store(), evidence_item_id=item_id, idempotency_key="k1", trace_id=None
    )

    summary = _runs(db_session, item_id)[0].failure_summary or ""
    assert summary == "This file is not a PDF."
    assert "application/pdf" not in summary


def test_a_failure_summary_says_nothing_about_the_document(api: Api, db_session: Session) -> None:
    """§16.2: failure summaries must not contain raw document content. The summary talks
    about media types, which this module computed, not about anything it read."""
    item_id = _uploaded(api, "user_a", content=b"%PDF-NOT windows executable secret-token")

    processing.validate_evidence(
        db_session, _store(), evidence_item_id=item_id, idempotency_key="k1", trace_id=None
    )

    summary = _runs(db_session, item_id)[0].failure_summary or ""
    assert "secret-token" not in summary
    assert "doc.pdf" not in summary


# --- idempotency ---------------------------------------------------------------------


def test_a_duplicate_delivery_creates_no_second_run(api: Api, db_session: Session) -> None:
    """CLAUDE.md §9: a duplicate worker delivery cannot create duplicate claims or
    results. `acks_late` makes redelivery ordinary rather than exceptional."""
    item_id = _uploaded(api, "user_a")

    first = processing.validate_evidence(
        db_session, _store(), evidence_item_id=item_id, idempotency_key="same", trace_id=None
    )
    second = processing.validate_evidence(
        db_session, _store(), evidence_item_id=item_id, idempotency_key="same", trace_id=None
    )

    assert second.already_done is True
    assert second.run_id == first.run_id
    assert len(_runs(db_session, item_id)) == 1


def test_a_user_retry_gets_a_new_run(api: Api, db_session: Session) -> None:
    """The reason the key is the *outbox row's* id rather than
    `file_id:pipeline_version`. A retry writes a new outbox row, so it gets a new key —
    and the composite key could not have told the two apart."""
    item_id = _uploaded(api, "user_a")

    first = processing.validate_evidence(
        db_session, _store(), evidence_item_id=item_id, idempotency_key="delivery-1", trace_id=None
    )
    second = processing.validate_evidence(
        db_session, _store(), evidence_item_id=item_id, idempotency_key="delivery-2", trace_id=None
    )

    assert second.already_done is False
    assert second.run_id != first.run_id
    assert len(_runs(db_session, item_id)) == 2


# --- failure never destroys ----------------------------------------------------------


def test_a_terminal_failure_leaves_the_uploaded_file_alone(api: Api, db_session: Session) -> None:
    """MVP §8.9 and Domain §16.2: processing failure never deletes the uploaded evidence.

    Structural rather than careful — nothing in `processing.py` can delete a stored
    object — but asserted, because "no code path does X" is exactly the claim that
    quietly stops being true.
    """
    item_id = _uploaded(api, "user_a", content=_NOT_A_PDF)
    file = db_session.execute(
        select(EvidenceFile).where(EvidenceFile.evidence_item_id == item_id)
    ).scalar_one()
    key = file.storage_key

    processing.validate_evidence(
        db_session, _store(), evidence_item_id=item_id, idempotency_key="k1", trace_id=None
    )

    db_session.refresh(file)
    assert _store().head(key) is not None, "the stored object was removed by a failure"
    assert file.deleted_at is None
    assert db_session.get(EvidenceItem, item_id) is not None


def test_an_unreachable_store_is_transient_and_records_no_verdict(
    api: Api, db_session: Session
) -> None:
    """Nothing was concluded about the file, so nothing terminal is recorded. Marking it
    FAILED would tell a user their document is unreadable because our object store had a
    bad minute — and `autoretry_for` would not fire, because the task returned."""
    item_id = _uploaded(api, "user_a")

    class Unreachable(InMemoryStorage):
        def read_prefix(self, key: str, *, length: int) -> bytes:
            raise StorageError("connection reset")

    with pytest.raises(processing.TransientProcessingError):
        processing.validate_evidence(
            db_session, Unreachable(), evidence_item_id=item_id, idempotency_key="k1", trace_id=None
        )

    run = _runs(db_session, item_id)[0]
    assert run.run_status is ProcessingRunStatus.RUNNING
    assert run.failure_code is None


def test_giving_up_on_a_transient_failure_leaves_a_state_the_user_can_act_on(
    api: Api, db_session: Session
) -> None:
    """The stranded-document defect, pinned.

    `autoretry_for` re-raises when the retries run out and the task simply ends — run
    still RUNNING, item still VALIDATING, and nothing left in the system that will ever
    move them. The user watches a state that cannot resolve and the client polls it for
    as long as the tab is open. Exhaustion has to be a state transition.
    """
    item_id = _uploaded(api, "user_a")

    class Unreachable(InMemoryStorage):
        def read_prefix(self, key: str, *, length: int) -> bytes:
            raise StorageError("connection reset")

    with pytest.raises(processing.TransientProcessingError):
        processing.validate_evidence(
            db_session, Unreachable(), evidence_item_id=item_id, idempotency_key="k1", trace_id=None
        )
    assert _runs(db_session, item_id)[0].run_status is ProcessingRunStatus.RUNNING

    outcome = processing.abandon_run(
        db_session,
        idempotency_key="k1",
        code=ProcessingFailureCode.STORAGE_UNAVAILABLE,
        summary="We could not read this file. You can try again.",
    )

    assert outcome is not None
    assert outcome.processing_status is EvidenceProcessingStatus.FAILED
    run = _runs(db_session, item_id)[0]
    assert run.run_status is ProcessingRunStatus.FAILED
    assert run.failure_code == ProcessingFailureCode.STORAGE_UNAVAILABLE.value
    # And FAILED is terminal for the client, so the poll stops.
    item = db_session.get(EvidenceItem, item_id)
    assert item is not None
    assert item.processing_status == EvidenceProcessingStatus.FAILED.value


def test_abandoning_a_run_that_was_never_written_does_nothing(db_session: Session) -> None:
    """The failure happened before a run existed, so there is nothing to correct — and
    inventing a FAILED run for a document that was never touched would be worse."""
    assert (
        processing.abandon_run(
            db_session,
            idempotency_key="never-existed",
            code=ProcessingFailureCode.STORAGE_UNAVAILABLE,
            summary="…",
        )
        is None
    )


# --- domain states, never queue states ------------------------------------------------


def test_every_run_status_maps_to_a_domain_state_or_explicitly_to_none() -> None:
    """Total over the enum. A status with no mapping falls through to whatever the item
    already said — a document that finished and still reads as though nothing happened,
    which is the quiet failure this product exists to avoid."""
    assert set(PROCESSING_STATUS_FOR_RUN) == set(ProcessingRunStatus)


def test_no_celery_state_can_reach_a_user() -> None:
    """The other half of the schema-level guarantee: the mapping's values are §14.4
    states, so no queue vocabulary exists to be projected in the first place."""
    celery_states = {"PENDING", "STARTED", "RETRY", "SUCCESS", "FAILURE", "REVOKED"}
    mapped = {value.value for value in PROCESSING_STATUS_FOR_RUN.values() if value}
    assert mapped & celery_states == set()
    assert mapped <= {state.value for state in EvidenceProcessingStatus}


def test_a_cancelled_run_leaves_the_users_state_alone() -> None:
    """A case being deleted is not a processing failure, and must not be shown as one."""
    assert PROCESSING_STATUS_FOR_RUN[ProcessingRunStatus.CANCELLED] is None
