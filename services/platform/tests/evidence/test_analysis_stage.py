"""The analysis stage: what a document's state becomes once a model has looked at it.

M8 slice 2 adds one step to the pipeline and four ways for it to end. The tests that
matter are the ones where analysis does *not* produce an answer, because that is where
a document could be left in `ANALYSING` with nothing to move it — the screen says
"analysing", the truth is "nothing will ever happen", and only a log knows.
"""

import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.classifier import ClassificationOutput, ClassifiedCategory
from app.ai.domain import ModelRun, ModelRunStatus
from app.ai.extraction_run import ExtractionRun, ExtractionRunStatus
from app.ai.fake import FakeProvider, failed, succeeded
from app.evidence.domain import EvidenceItem, EvidenceProcessingStatus
from tests.conftest import Api
from tests.evidence.test_processing import _process, _uploaded

pytestmark = pytest.mark.integration


def _answering(category: ClassifiedCategory, confidence: float = 0.92) -> FakeProvider:
    return FakeProvider(
        responses=[
            succeeded(
                ClassificationOutput(
                    category=category, confidence=confidence, reasoning="letterhead and dates"
                )
            )
        ]
    )


def _runs(session: Session, item_id: uuid.UUID) -> list[ExtractionRun]:
    return list(
        session.execute(
            select(ExtractionRun).where(ExtractionRun.evidence_item_id == item_id)
        ).scalars()
    )


def _item(session: Session, item_id: uuid.UUID) -> EvidenceItem:
    session.expire_all()
    item = session.get(EvidenceItem, item_id)
    assert item is not None
    return item


# --- the answers ------------------------------------------------------------------


def test_a_classified_document_completes_and_records_the_category(
    api: Api, db_session: Session
) -> None:
    item_id = _uploaded(api, "user_a", content=_fixture())

    outcome = _process(
        item_id, idempotency_key="a1", provider=_answering(ClassifiedCategory.TRAVEL_SUPPORT)
    )

    assert outcome.processing_status is EvidenceProcessingStatus.COMPLETED
    (run,) = _runs(db_session, item_id)
    assert run.status == ExtractionRunStatus.SUCCEEDED.value
    assert run.classified_category == "TRAVEL_SUPPORT"
    assert run.classification_confidence == 0.92
    assert run.model_run_id is not None


def test_the_users_own_category_is_never_changed_by_the_classifier(
    api: Api, db_session: Session
) -> None:
    """The document is uploaded as TRAVEL_SUPPORT and the model says it is an English
    test. The disagreement is recorded; the user's choice stands. Slice 3b shows them
    both and lets the person decide — this slice must not decide for them."""
    item_id = _uploaded(api, "user_a", content=_fixture())
    before = _item(db_session, item_id).category

    _process(
        item_id, idempotency_key="a2", provider=_answering(ClassifiedCategory.ENGLISH_LANGUAGE)
    )

    assert _item(db_session, item_id).category == before == "TRAVEL_SUPPORT"
    (run,) = _runs(db_session, item_id)
    assert run.classified_category == "ENGLISH_LANGUAGE"


def test_an_unsupported_document_reaches_the_unsupported_state(
    api: Api, db_session: Session
) -> None:
    """A readable document of a kind this workspace does not handle. Same state a wrong
    file type reaches, because the user's remedy is the same: there is nothing we can do
    with this. MVP §8.10 — unsupported documents create no trusted facts."""
    item_id = _uploaded(api, "user_a", content=_fixture())

    outcome = _process(
        item_id, idempotency_key="a3", provider=_answering(ClassifiedCategory.UNSUPPORTED)
    )

    assert outcome.processing_status is EvidenceProcessingStatus.UNSUPPORTED
    (run,) = _runs(db_session, item_id)
    assert run.status == ExtractionRunStatus.ABSTAINED.value


def test_an_ambiguous_document_completes_rather_than_looking_broken(
    api: Api, db_session: Session
) -> None:
    """Processing genuinely finished — the document was read and analysed, and the
    finding is that its type is unclear.

    Deliberately not `PARTIALLY_COMPLETED`: that state already means "this is a scan
    with no text to read", and one state meaning two things with two different remedies
    is a state a user cannot act on.
    """
    item_id = _uploaded(api, "user_a", content=_fixture())

    outcome = _process(
        item_id, idempotency_key="a4", provider=_answering(ClassifiedCategory.AMBIGUOUS)
    )

    assert outcome.processing_status is EvidenceProcessingStatus.COMPLETED
    (run,) = _runs(db_session, item_id)
    assert run.status == ExtractionRunStatus.ABSTAINED.value
    assert run.classified_category == "AMBIGUOUS"


# --- the failures -----------------------------------------------------------------


def test_a_failed_analysis_keeps_the_text_and_says_so(api: Api, db_session: Session) -> None:
    """The ordering that makes this slice safe: text is stored *before* the model is
    asked anything, so M7's work never becomes contingent on M8's."""
    from app.evidence.domain import EvidenceFile, EvidenceFileText

    item_id = _uploaded(api, "user_a", content=_fixture())

    outcome = _process(
        item_id,
        idempotency_key="a5",
        provider=FakeProvider(responses=[failed(ModelRunStatus.TERMINAL)]),
    )

    assert outcome.processing_status is EvidenceProcessingStatus.PARTIALLY_COMPLETED
    (run,) = _runs(db_session, item_id)
    assert run.status == ExtractionRunStatus.FAILED.value
    assert run.classified_category is None, "a failed analysis must invent no category"

    file_id = db_session.execute(
        select(EvidenceFile.id).where(EvidenceFile.evidence_item_id == item_id)
    ).scalar_one()
    text = db_session.execute(
        select(EvidenceFileText).where(EvidenceFileText.evidence_file_id == file_id)
    ).scalar_one_or_none()
    assert text is not None and text.character_count > 0, "the deterministic reading was lost"


def test_a_document_never_ends_in_the_analysing_state(api: Api, db_session: Session) -> None:
    """The state a user could be stranded in. Whatever the provider does, the pipeline
    leaves a document somewhere terminal."""
    for key, provider in (
        ("b1", _answering(ClassifiedCategory.TRAVEL_SUPPORT)),
        ("b2", FakeProvider(responses=[failed(ModelRunStatus.FAILED)])),
        ("b3", FakeProvider(responses=[failed(ModelRunStatus.REFUSED)])),
        ("b4", FakeProvider(responses=[failed(ModelRunStatus.TIMED_OUT)])),
    ):
        item_id = _uploaded(api, "user_a", content=_fixture())
        outcome = _process(item_id, idempotency_key=key, provider=provider)
        assert outcome.processing_status is not EvidenceProcessingStatus.ANALYSING
        assert _item(db_session, item_id).processing_status != "ANALYSING"


def test_a_scan_is_never_sent_to_the_classifier(api: Api, db_session: Session) -> None:
    """A document with no text layer has nothing to classify. Asking anyway would spend
    money to be told the empty string is AMBIGUOUS — which would then read as a finding
    about the document rather than about there being nothing to look at."""
    provider = FakeProvider(responses=[])
    item_id = _uploaded(api, "user_a", content=_fixture("scan-no-text-layer.pdf"))

    outcome = _process(item_id, idempotency_key="c1", provider=provider)

    assert outcome.processing_status is EvidenceProcessingStatus.PARTIALLY_COMPLETED
    assert provider.calls == [], "a scan reached the model"
    assert _runs(db_session, item_id) == []


def test_an_unreadable_document_is_never_sent_to_the_classifier(
    api: Api, db_session: Session
) -> None:
    provider = FakeProvider(responses=[])
    item_id = _uploaded(api, "user_a", content=_fixture("password-protected.pdf"))

    _process(item_id, idempotency_key="c2", provider=provider)

    assert provider.calls == []
    assert _runs(db_session, item_id) == []


# --- what the model was given ------------------------------------------------------


def test_the_document_text_is_what_reaches_the_model(api: Api) -> None:
    provider = _answering(ClassifiedCategory.TRAVEL_SUPPORT)
    item_id = _uploaded(api, "user_a", content=_fixture())

    _process(item_id, idempotency_key="d1", provider=provider)

    (_capability, system_text, document) = provider.calls[0]
    assert "Amara Okonkwo" in document, "the model was not given the document's text"
    assert "Amara Okonkwo" not in system_text, "document content reached the instruction"


def test_the_filename_does_not_reach_the_model(api: Api) -> None:
    """MVP §8.10's misleading-filename criterion. The document is uploaded under a name
    that asserts the wrong category; the model never sees it."""
    provider = _answering(ClassifiedCategory.TRAVEL_SUPPORT)
    item_id = _uploaded(
        api, "user_a", content=_fixture(), original_filename="settled-status-grant.pdf"
    )

    _process(item_id, idempotency_key="d2", provider=provider)

    (_capability, system_text, document) = provider.calls[0]
    assert "settled-status-grant" not in document
    assert "settled-status-grant" not in system_text


def test_the_run_is_linked_to_its_processing_run_and_model_run(
    api: Api, db_session: Session
) -> None:
    """ADR-0025's join, end to end: one document's whole processing story is reachable
    without either table holding the other's concerns."""
    item_id = _uploaded(api, "user_a", content=_fixture())

    outcome = _process(
        item_id, idempotency_key="e1", provider=_answering(ClassifiedCategory.TRAVEL_SUPPORT)
    )

    (run,) = _runs(db_session, item_id)
    assert run.processing_run_id == outcome.run_id
    model_run = db_session.get(ModelRun, run.model_run_id)
    assert model_run is not None
    assert model_run.capability == "DocumentClassifier"


def _fixture(name: str = "travel-booking.pdf") -> bytes:
    from tests.evidence.conftest import fixture_bytes

    return fixture_bytes(name)
