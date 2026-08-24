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
    EvidenceFileText,
    EvidenceItem,
    EvidenceProcessingRun,
    EvidenceProcessingStatus,
    ProcessingFailureCode,
    ProcessingRunStatus,
)
from tests.evidence.conftest import fixture_bytes as _fixture
from tests.security.conftest import SUPPORTED_ANSWERS

pytestmark = pytest.mark.integration

Api = Callable[[str], TestClient]

_NOT_A_PDF = b"MZ\x90\x00 this is a windows executable"


def _store() -> InMemoryStorage:
    store = get_storage()
    assert isinstance(store, InMemoryStorage)
    return store


def _text_for(session: Session, evidence_item_id: uuid.UUID) -> EvidenceFileText | None:
    stmt = (
        select(EvidenceFileText)
        .join(EvidenceFile, EvidenceFile.id == EvidenceFileText.evidence_file_id)
        .where(EvidenceFile.evidence_item_id == evidence_item_id)
    )
    return session.execute(stmt).scalar_one_or_none()


def _uploaded(
    api: Api, user: str, *, content: bytes | None = None, media_type: str = "application/pdf"
) -> uuid.UUID:
    # A *real* PDF by default. `b"%PDF-1.7 ..."` passes the magic-byte check and is not a
    # document — fine while validation was all that ran, and a corrupt file the moment a
    # parser had to open it.
    if content is None:
        content = _fixture("travel-booking.pdf")
    case_id = str(api(user).post("/api/v1/cases", json={"title": "Processing"}).json()["id"])
    api(user).put(f"/api/v1/cases/{case_id}/route-profile", json=SUPPORTED_ANSWERS)
    api(user).post(f"/api/v1/cases/{case_id}/route-profile/confirm", json={})

    grant = (
        api(user)
        .post(
            f"/api/v1/cases/{case_id}/evidence/uploads",
            json={"media_type": media_type, "declared_size_bytes": len(content)},
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


def _process(
    evidence_item_id: uuid.UUID,
    *,
    idempotency_key: str,
    storage: object | None = None,
    evidence_file_id: uuid.UUID | None = None,
) -> processing.ProcessingOutcome:
    """Run the pipeline on its own session, as the worker does.

    Not on `db_session`, and the reason is not tidiness. Sync FastAPI endpoints run in a
    threadpool, so the TestClient mutates the shared session from *another thread*; this
    pipeline is the first thing in the suite to make multi-commit updates to a versioned
    aggregate (`EvidenceItem` carries a `version_id_col`) that the API created. Sharing
    the session produced an intermittent `StaleDataError: expected to update 1 row(s); 0
    were matched`, appearing on a different test each run.

    In production these are different processes on different connections, so a separate
    session is also the more faithful arrangement — the shared one was the artificial
    part.
    """
    from app.core.storage import get_storage as _get_storage
    from app.shared.db import get_sessionmaker
    from app.shared.tenant import set_tenant

    session = get_sessionmaker()()
    try:
        set_tenant(session, "user_a")
        return processing.validate_evidence(
            session,
            storage or _get_storage(),  # type: ignore[arg-type]
            evidence_item_id=evidence_item_id,
            idempotency_key=idempotency_key,
            trace_id=None,
            evidence_file_id=evidence_file_id,
        )
    finally:
        session.close()


def _runs(session: Session, evidence_item_id: uuid.UUID) -> list[EvidenceProcessingRun]:
    stmt = select(EvidenceProcessingRun).where(
        EvidenceProcessingRun.evidence_item_id == evidence_item_id
    )
    return list(session.execute(stmt).scalars().all())


# --- what validation concludes -------------------------------------------------------


def test_a_real_pdf_is_validated_then_read(api: Api, db_session: Session) -> None:
    """The whole pipeline in one: validate the bytes, then read the text out of them."""
    item_id = _uploaded(api, "user_a", content=_fixture("travel-booking.pdf"))

    outcome = _process(item_id, idempotency_key="k1")

    assert outcome.processing_status is EvidenceProcessingStatus.COMPLETED
    assert outcome.failure_code is None
    assert [r.run_status for r in _runs(db_session, item_id)] == [ProcessingRunStatus.SUCCEEDED]

    text = _text_for(db_session, item_id)
    assert text is not None
    assert text.page_count == 1
    assert text.character_count > 0
    assert "Amara Okonkwo" in text.content


def test_a_scan_completes_partially_rather_than_failing(api: Api, db_session: Session) -> None:
    """A photograph of a page is a valid document with nothing for a text parser to read.
    `FAILED` would tell the user to fix a file that is perfectly fine."""
    item_id = _uploaded(api, "user_a", content=_fixture("scan-no-text-layer.pdf"))

    outcome = _process(item_id, idempotency_key="k1")

    assert outcome.processing_status is EvidenceProcessingStatus.PARTIALLY_COMPLETED
    assert outcome.failure_code is None
    text = _text_for(db_session, item_id)
    assert text is not None and text.character_count == 0


def test_a_multi_page_scan_completes_partially_through_the_whole_pipeline(
    api: Api, db_session: Session
) -> None:
    """The single-page scan test could not find this.

    Through the pipeline rather than through `extract()` alone, because the defect lived
    between them: `character_count` counted the joined string, so a three-page scan
    reported two characters — and after that was fixed, migration 0018's consistency
    check still encoded the buggy relationship and rejected the row outright. Only a
    multi-page scan going all the way to the database exercises both.
    """
    item_id = _uploaded(api, "user_a", content=_fixture("scan-multi-page.pdf"))

    outcome = _process(item_id, idempotency_key="k1")

    assert outcome.processing_status is EvidenceProcessingStatus.PARTIALLY_COMPLETED
    assert outcome.failure_code is None
    text = _text_for(db_session, item_id)
    assert text is not None
    assert text.page_count == 3
    assert text.pages_read == 3
    assert text.character_count == 0


def test_a_password_protected_document_fails_with_a_reason(api: Api, db_session: Session) -> None:
    item_id = _uploaded(api, "user_a", content=_fixture("password-protected.pdf"))

    outcome = _process(item_id, idempotency_key="k1")

    assert outcome.processing_status is EvidenceProcessingStatus.FAILED
    assert outcome.failure_code is ProcessingFailureCode.PASSWORD_PROTECTED
    # Nothing was read, so nothing is stored.
    assert _text_for(db_session, item_id) is None


def test_a_long_document_records_that_the_read_was_bounded(api: Api, db_session: Session) -> None:
    """`truncated` is what stops M8 drawing a conclusion from page 40 of 60 without
    knowing that is what it is looking at."""
    item_id = _uploaded(api, "user_a", content=_fixture("many-pages.pdf"))

    _process(item_id, idempotency_key="k1")

    text = _text_for(db_session, item_id)
    assert text is not None
    assert text.truncated is True
    assert text.page_count == 60


def test_an_image_is_completed_partially_without_being_parsed(
    api: Api, db_session: Session
) -> None:
    """A JPEG is a supported document with no text layer. Handing it to a PDF parser to
    find that out would be a parser failure standing in for a known answer."""
    item_id = _uploaded(
        api, "user_a", content=b"\xff\xd8\xff a synthetic jpeg", media_type="image/jpeg"
    )

    outcome = _process(item_id, idempotency_key="k1")

    assert outcome.processing_status is EvidenceProcessingStatus.PARTIALLY_COMPLETED
    assert _text_for(db_session, item_id) is None


def test_content_that_contradicts_its_declared_type_is_unsupported(
    api: Api, db_session: Session
) -> None:
    """The presigned policy binds the *declared* type into the signature, so a client
    cannot upload under a different label — but it still controls the bytes. This is
    where a `.exe` called `application/pdf` is caught, and it needs the content, which is
    why it is in the worker."""
    item_id = _uploaded(api, "user_a", content=_NOT_A_PDF)

    outcome = _process(item_id, idempotency_key="k1")

    assert outcome.processing_status is EvidenceProcessingStatus.UNSUPPORTED
    assert outcome.failure_code is ProcessingFailureCode.CONTENT_DOES_NOT_MATCH_TYPE


def test_the_refusal_is_phrased_in_the_users_vocabulary(api: Api, db_session: Session) -> None:
    """A failure summary is read by someone wondering why their document was refused.
    Answering with a MIME type answers in a vocabulary they did not choose — and the
    first version read "not a application/pdf document", which is also ungrammatical."""
    item_id = _uploaded(api, "user_a", content=_NOT_A_PDF)

    _process(item_id, idempotency_key="k1")

    summary = _runs(db_session, item_id)[0].failure_summary or ""
    assert summary == "This file is not a PDF."
    assert "application/pdf" not in summary


def test_a_failure_summary_says_nothing_about_the_document(api: Api, db_session: Session) -> None:
    """§16.2: failure summaries must not contain raw document content. The summary talks
    about media types, which this module computed, not about anything it read."""
    item_id = _uploaded(api, "user_a", content=b"MZ\x90\x00 windows executable secret-token")

    _process(item_id, idempotency_key="k1")

    summary = _runs(db_session, item_id)[0].failure_summary or ""
    assert "secret-token" not in summary
    assert "doc.pdf" not in summary


# --- idempotency ---------------------------------------------------------------------


def test_a_duplicate_delivery_creates_no_second_run(api: Api, db_session: Session) -> None:
    """CLAUDE.md §9: a duplicate worker delivery cannot create duplicate claims or
    results. `acks_late` makes redelivery ordinary rather than exceptional."""
    item_id = _uploaded(api, "user_a")

    first = _process(item_id, idempotency_key="same")
    second = _process(item_id, idempotency_key="same")

    assert second.already_done is True
    assert second.run_id == first.run_id
    assert len(_runs(db_session, item_id)) == 1


def test_a_user_retry_gets_a_new_run(api: Api, db_session: Session) -> None:
    """The reason the key is the *outbox row's* id rather than
    `file_id:pipeline_version`. A retry writes a new outbox row, so it gets a new key —
    and the composite key could not have told the two apart."""
    item_id = _uploaded(api, "user_a")

    first = _process(item_id, idempotency_key="delivery-1")
    second = _process(item_id, idempotency_key="delivery-2")

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

    _process(item_id, idempotency_key="k1")

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
        _process(item_id, idempotency_key="k1", storage=Unreachable())

    run = _runs(db_session, item_id)[0]
    assert run.run_status is ProcessingRunStatus.RUNNING
    assert run.failure_code is None


def test_a_retry_after_a_transient_failure_actually_runs(api: Api, db_session: Session) -> None:
    """The defect this test exists for was in the fix for the previous one.

    The idempotency short-circuit fired on *any* existing run for the key — including the
    RUNNING one this same delivery had written seconds earlier. So the retry found its own
    attempt, returned `already_done=True`, and the task succeeded having done nothing.
    `request.retries` never advanced, the exhaustion branch never ran, `abandon_run` was
    unreachable in production, and the document sat in VALIDATING for good while the
    client polled it every 1.5 seconds for as long as the tab was open.

    A RUNNING run under the same key is this delivery's own attempt, not a duplicate.
    """
    item_id = _uploaded(api, "user_a")

    class Unreachable(InMemoryStorage):
        def read_prefix(self, key: str, *, length: int) -> bytes:
            raise StorageError("connection reset")

    with pytest.raises(processing.TransientProcessingError):
        _process(item_id, idempotency_key="k1", storage=Unreachable())

    # The store recovers and the same delivery is retried.
    outcome = _process(item_id, idempotency_key="k1")

    assert outcome.already_done is False, "the retry short-circuited on its own attempt"
    assert outcome.processing_status is EvidenceProcessingStatus.COMPLETED
    runs = _runs(db_session, item_id)
    # One run, not two: the attempt is counted on the run rather than duplicating it
    # (§16.2 — "a retry creates a new run or a new attempt record").
    assert len(runs) == 1
    assert runs[0].retry_count == 1
    assert runs[0].run_status is ProcessingRunStatus.SUCCEEDED


def test_a_settled_run_still_short_circuits(api: Api, db_session: Session) -> None:
    """Fixing the retry must not break the thing the key is for: a redelivery of work
    that already reached a verdict does nothing."""
    item_id = _uploaded(api, "user_a")

    first = _process(item_id, idempotency_key="k1")
    second = _process(item_id, idempotency_key="k1")

    assert second.already_done is True
    assert second.run_id == first.run_id
    assert len(_runs(db_session, item_id)) == 1


def test_the_delivery_acts_on_the_file_version_it_names(api: Api, db_session: Session) -> None:
    """A consumer that re-reads "the newest file" is a consumer two out-of-order
    deliveries can leave carrying the older file's verdict. Latent today — there is one
    version per item — which is exactly why it is cheap to bind now."""
    item_id = _uploaded(api, "user_a")
    file = db_session.execute(
        select(EvidenceFile).where(EvidenceFile.evidence_item_id == item_id)
    ).scalar_one()

    outcome = _process(item_id, idempotency_key="k1", evidence_file_id=file.id)
    assert outcome.processing_status is EvidenceProcessingStatus.COMPLETED

    # A version that does not belong to this item is refused rather than silently
    # falling back to whatever is current.
    with pytest.raises(processing.EvidenceNotProcessable):
        _process(item_id, idempotency_key="k2", evidence_file_id=uuid.uuid4())


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
        _process(item_id, idempotency_key="k1", storage=Unreachable())
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


# --- retry -------------------------------------------------------------------------


def test_a_retry_writes_a_new_outbox_row_so_the_key_differs(
    api: Api, db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The mechanism the whole retry rests on.

    The idempotency key is the outbox row's id, so a retry only works if it *is* a new
    delivery. Re-emitting nothing, or reusing the upload's row, would leave the retry
    short-circuiting as a duplicate — which is what `file_id:pipeline_version` as a key
    could never have distinguished.
    """
    from sqlalchemy import func

    from app.evidence import service as evidence_service
    from app.shared.records import OutboxEventRecord

    # The cooldown is a rate limit, not the behaviour under test here.
    monkeypatch.setattr(evidence_service, "RETRY_COOLDOWN_SECONDS", 0.0)

    item_id = _uploaded(api, "user_a", content=_fixture("password-protected.pdf"))
    _process(item_id, idempotency_key="k1")
    item = db_session.get(EvidenceItem, item_id)
    assert item is not None and item.processing_status == EvidenceProcessingStatus.FAILED.value

    before = db_session.execute(select(func.count()).select_from(OutboxEventRecord)).scalar_one()

    from app.cases import service as cases_service
    from tests.conftest import as_user

    user = as_user("user_a")
    case = cases_service.get_case(db_session, case_id=item.case_id, user=user)
    assert case is not None
    evidence_service.request_reprocessing(
        db_session, case=case, user=user, evidence_item_id=item_id
    )

    after = db_session.execute(select(func.count()).select_from(OutboxEventRecord)).scalar_one()
    assert after == before + 1

    row = db_session.execute(
        select(OutboxEventRecord)
        .where(OutboxEventRecord.event_type == "EvidenceProcessingRequested")
        .order_by(OutboxEventRecord.created_at.desc())
        .limit(1)
    ).scalar_one()
    assert row.published_at is None, "a fresh row, waiting for the relay"
    assert row.payload["previous_status"] == "FAILED"

    # And the document says something is happening again, so the client resumes polling
    # instead of showing a stale verdict until the next reload.
    db_session.refresh(item)
    assert item.processing_status == EvidenceProcessingStatus.VALIDATING.value


def test_an_unsupported_document_is_not_offered_a_retry(api: Api, db_session: Session) -> None:
    """`UNSUPPORTED` is a verdict about the *file*. Running the same bytes through the
    same check reaches the same answer, so a retry there would be a button that cannot
    work — worse than no button, because it invites the user to keep pressing it."""
    from app.cases import service as cases_service
    from app.evidence import service as evidence_service
    from app.shared.errors import EvidenceNotRetryable
    from tests.conftest import as_user

    item_id = _uploaded(api, "user_a", content=_NOT_A_PDF)
    _process(item_id, idempotency_key="k1")
    item = db_session.get(EvidenceItem, item_id)
    assert item is not None

    user = as_user("user_a")
    case = cases_service.get_case(db_session, case_id=item.case_id, user=user)
    assert case is not None
    with pytest.raises(EvidenceNotRetryable):
        evidence_service.request_reprocessing(
            db_session, case=case, user=user, evidence_item_id=item_id
        )


def test_re_extraction_replaces_rather_than_appends(api: Api, db_session: Session) -> None:
    """One row per file version (Domain §15.1). Inserting blindly made a user retry
    violate the unique constraint — and the resulting IntegrityError would have carried
    the entire document text in its bound parameters had `hide_parameters` not been set
    in slice 1."""
    item_id = _uploaded(api, "user_a")

    _process(item_id, idempotency_key="k1")
    first = _text_for(db_session, item_id)
    assert first is not None
    first_id = first.id

    _process(item_id, idempotency_key="k2")
    second = _text_for(db_session, item_id)

    assert second is not None
    assert second.id == first_id, "the reading was replaced, not duplicated"


def test_the_library_carries_what_extraction_found(api: Api, db_session: Session) -> None:
    """The list route, not the detail route.

    `texts_for_case` existed and was never called from the list projection, so
    `page_count` and `text_truncated` were always null there — and the library is the
    only endpoint the Evidence screen reads. A 60-page document read to page 40 rendered
    as "Read" with no qualification at all, which is exactly what `truncated` exists to
    prevent. Every existing test asserted against the database row or the detail route,
    so none of them saw it.
    """
    item_id = _uploaded(api, "user_a", content=_fixture("many-pages.pdf"))
    _process(item_id, idempotency_key="k1")
    db_session.expire_all()

    item = db_session.get(EvidenceItem, item_id)
    assert item is not None
    library = api("user_a").get(f"/api/v1/cases/{item.case_id}/evidence").json()
    row = next(entry for entry in library["items"] if entry["id"] == str(item_id))

    assert row["page_count"] == 60
    assert row["pages_read"] == 40
    assert row["text_truncated"] is True


def test_no_evidence_response_ever_carries_document_text(api: Api, db_session: Session) -> None:
    """Counts and flags cross the boundary; words do not. Asserted against the real
    responses rather than only against the schema, because a field is not the only way
    text can end up in a payload."""
    item_id = _uploaded(api, "user_a")
    _process(item_id, idempotency_key="k1")
    db_session.expire_all()

    item = db_session.get(EvidenceItem, item_id)
    assert item is not None
    for path in ("", f"/{item_id}"):
        body = api("user_a").get(f"/api/v1/cases/{item.case_id}/evidence{path}").text
        # A string from inside the synthetic booking document.
        assert "Amara Okonkwo" not in body
        assert "SYNTH-TRV" not in body


def test_abandoning_cannot_overwrite_a_run_that_already_succeeded(
    api: Api, db_session: Session
) -> None:
    """Duplicate delivery is possible by design — `published_at` commits after the broker
    accepts — so two deliveries can share one idempotency key. If one exhausts its
    retries after the other has succeeded, overwriting would turn a good reading into a
    FAILED document while the text sits in the database.
    """
    item_id = _uploaded(api, "user_a")
    _process(item_id, idempotency_key="k1")

    outcome = processing.abandon_run(
        db_session,
        idempotency_key="k1",
        code=ProcessingFailureCode.RESOURCE_LIMIT,
        summary="…",
    )

    assert outcome is None, "a settled run was overwritten"
    run = _runs(db_session, item_id)[0]
    assert run.run_status is ProcessingRunStatus.SUCCEEDED
    item = db_session.get(EvidenceItem, item_id)
    assert item is not None
    assert item.processing_status == EvidenceProcessingStatus.COMPLETED.value
