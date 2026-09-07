"""Deleting a document (Domain §51.1).

The command is four of the seven steps in one transaction; the purge is the other two,
asynchronously. What these tests hold is the boundary between them — because the failure
mode this slice exists to prevent is not "deletion does not work", it is "deletion works
and something that depended on the document goes on looking confident".
"""

import uuid
from collections.abc import Callable

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.storage import InMemoryStorage, StorageAdapter, get_storage
from app.evidence.domain import (
    EvidenceItem,
    EvidenceLifecycleStatus,
    EvidenceTravelLink,
    LinkAvailability,
)
from app.evidence.purge import PurgeOutcome, purge_evidence
from tests.evidence.conftest import fixture_bytes as _fixture
from tests.security.conftest import SUPPORTED_ANSWERS

pytestmark = pytest.mark.integration

Api = Callable[[str], TestClient]


def _case_with_trip(api: Api, user: str, *, title: str = "Deletion") -> tuple[str, str]:
    case_id = str(api(user).post("/api/v1/cases", json={"title": title}).json()["id"])
    api(user).put(f"/api/v1/cases/{case_id}/route-profile", json=SUPPORTED_ANSWERS)
    api(user).post(f"/api/v1/cases/{case_id}/route-profile/confirm", json={})
    api(user).post(
        f"/api/v1/cases/{case_id}/application-dates/select",
        json={"application_date": "2027-04-15"},
    )
    trip = api(user).post(
        f"/api/v1/cases/{case_id}/travel-records",
        json={
            "destination_label": "Greece",
            "destination_country_code": "GR",
            "departure_date": "2024-06-05",
            "return_date": "2024-07-15",
            "date_confidence": "EXACT",
            "review_state": "CONFIRMED",
        },
    )
    return case_id, str(trip.json()["id"])


def _document(api: Api, user: str, case_id: str, *, name: str = "Athens booking") -> str:
    content = _fixture("travel-booking.pdf")
    grant = (
        api(user)
        .post(
            f"/api/v1/cases/{case_id}/evidence/uploads",
            json={"media_type": "application/pdf", "declared_size_bytes": len(content)},
        )
        .json()
    )
    store = get_storage()
    assert isinstance(store, InMemoryStorage)
    store.put(str(grant["upload_fields"]["key"]), content)
    item = api(user).post(
        f"/api/v1/cases/{case_id}/evidence",
        json={
            "upload_token": grant["upload_token"],
            "category": "TRAVEL_SUPPORT",
            "display_name": name,
            "original_filename": "booking.pdf",
        },
    )
    return str(item.json()["id"])


def _currency(api: Api, case_id: str) -> dict[str, str]:
    rows = api("user_a").get(f"/api/v1/cases/{case_id}/requirements").json()
    return {row["requirement_key"]: row["currency"] for row in rows}


# --- what the user sees immediately -------------------------------------------------


def test_a_deleted_document_stops_being_reachable_at_once(api: Api, db_session: Session) -> None:
    """§51.1 step 1. Not "eventually, once the purge runs" — the bytes may take a moment to
    go, but the user is told the document is gone the instant they ask for it to be."""
    case_id, _ = _case_with_trip(api, "user_a")
    item_id = _document(api, "user_a", case_id)

    assert api("user_a").delete(f"/api/v1/cases/{case_id}/evidence/{item_id}").status_code == 204

    assert api("user_a").get(f"/api/v1/cases/{case_id}/evidence/{item_id}").status_code == 404
    assert (
        api("user_a").get(f"/api/v1/cases/{case_id}/evidence/{item_id}/content").status_code == 404
    )
    library = api("user_a").get(f"/api/v1/cases/{case_id}/evidence").json()
    assert library["items"] == []


def test_deleting_twice_is_a_conflict_not_a_second_deletion(api: Api, db_session: Session) -> None:
    """The first call dispatched a purge. Answering 204 again would imply a second one is
    safe, and a second purge is a second attempt to destroy bytes that are already gone."""
    case_id, _ = _case_with_trip(api, "user_a")
    item_id = _document(api, "user_a", case_id)
    api("user_a").delete(f"/api/v1/cases/{case_id}/evidence/{item_id}")

    second = api("user_a").delete(f"/api/v1/cases/{case_id}/evidence/{item_id}")

    # 404, not 409: the item is already unreachable, so the command cannot find it to
    # refuse it — and an id must not confirm that something exists in a state it is not in.
    assert second.status_code == 404


def test_a_retry_cannot_be_asked_for_on_a_deleted_document(api: Api, db_session: Session) -> None:
    """§14.5: "a deleted evidence item cannot be reprocessed"."""
    case_id, _ = _case_with_trip(api, "user_a")
    item_id = _document(api, "user_a", case_id)
    api("user_a").delete(f"/api/v1/cases/{case_id}/evidence/{item_id}")

    assert (
        api("user_a").post(f"/api/v1/cases/{case_id}/evidence/{item_id}/retry").status_code == 404
    )


def test_another_tenant_cannot_delete(api: Api, db_session: Session) -> None:
    case_id, _ = _case_with_trip(api, "user_a")
    item_id = _document(api, "user_a", case_id)

    assert api("user_b").delete(f"/api/v1/cases/{case_id}/evidence/{item_id}").status_code == 404

    # Through the owner's own API rather than the shared session: the point is that the
    # document is still there and still usable, which is what user_a can see.
    still_there = api("user_a").get(f"/api/v1/cases/{case_id}/evidence/{item_id}")
    assert still_there.status_code == 200
    assert still_there.json()["lifecycle_status"] == "ACTIVE"


# --- what it does to the assessment -------------------------------------------------


def test_deleting_a_document_withdraws_its_support_and_stales_the_verdict(
    api: Api, db_session: Session
) -> None:
    """Steps 4 and 5, and the reason this slice exists.

    A conclusion drawn while a document supported a trip must not go on standing unchanged
    once the document is gone. And the absence totals must not move: deleting a booking
    does not change how many days the user was abroad.
    """
    case_id, trip_id = _case_with_trip(api, "user_a")
    item_id = _document(api, "user_a", case_id)
    api("user_a").post(
        f"/api/v1/cases/{case_id}/travel-records/{trip_id}/evidence",
        json={"evidence_item_id": item_id},
    )
    api("user_a").post(f"/api/v1/cases/{case_id}/assessments/recalculate")
    assert _currency(api, case_id)["residence.travel_consistency"] == "CURRENT"

    api("user_a").delete(f"/api/v1/cases/{case_id}/evidence/{item_id}")

    after = _currency(api, case_id)
    assert after["residence.travel_consistency"] == "STALE"
    # STALE from `0035`: deleting the document withdraws the link, which can dissolve a
    # conflict and return a trip to the trusted total. `qualifying_period` reads only the
    # application date, so it is the one that stays — the check that this is still selective
    # invalidation and not the blunt residence-group sweep ADR-0008 got wrong.
    assert after["residence.total_absences"] == "STALE"
    assert after["residence.final_year_absences"] == "STALE"
    assert after["residence.qualifying_period"] == "CURRENT"

    db_session.expire_all()
    link = db_session.execute(
        select(EvidenceTravelLink).where(EvidenceTravelLink.case_id == uuid.UUID(case_id))
    ).scalar_one()
    # DELETED, not UNAVAILABLE: the document is gone, not merely detached from the trip.
    assert link.availability is LinkAvailability.DELETED


def test_the_stale_reason_names_the_documents(api: Api, db_session: Session) -> None:
    case_id, trip_id = _case_with_trip(api, "user_a")
    item_id = _document(api, "user_a", case_id)
    api("user_a").post(
        f"/api/v1/cases/{case_id}/travel-records/{trip_id}/evidence",
        json={"evidence_item_id": item_id},
    )
    api("user_a").post(f"/api/v1/cases/{case_id}/assessments/recalculate")

    api("user_a").delete(f"/api/v1/cases/{case_id}/evidence/{item_id}")

    detail = (
        api("user_a")
        .get(f"/api/v1/cases/{case_id}/requirements/residence.travel_consistency")
        .json()
    )
    assert detail["stale"]["reason_code"] == "EVIDENCE_SUPPORT_CHANGED"


def test_deleting_a_document_that_supported_nothing_stales_nothing(
    api: Api, db_session: Session
) -> None:
    """`mark_support_unavailable` skips invalidation when no link moved. A document nobody
    attached to anything cannot have influenced a conclusion, and staling the case for it
    would be over-firing — the user would be told to recheck work that did not change."""
    case_id, _ = _case_with_trip(api, "user_a")
    item_id = _document(api, "user_a", case_id)
    api("user_a").post(f"/api/v1/cases/{case_id}/assessments/recalculate")

    api("user_a").delete(f"/api/v1/cases/{case_id}/evidence/{item_id}")

    assert _currency(api, case_id)["residence.travel_consistency"] == "CURRENT"


def test_the_deletion_event_carries_no_storage_key_or_name(api: Api, db_session: Session) -> None:
    """§38.1's payload rule, and the point of a tombstone. `domain_events` is immutable, so
    a name or a key written there outlives the deletion meant to remove it."""
    from app.shared.records import DomainEventRecord

    case_id, _ = _case_with_trip(api, "user_a")
    item_id = _document(api, "user_a", case_id, name="Amara's Athens booking")
    api("user_a").delete(f"/api/v1/cases/{case_id}/evidence/{item_id}")

    db_session.expire_all()
    event = db_session.execute(
        select(DomainEventRecord).where(DomainEventRecord.event_type == "EvidenceDeleted")
    ).scalar_one()
    rendered = str(event.payload)
    assert "Athens" not in rendered
    assert "booking.pdf" not in rendered
    assert "storage_key" not in rendered


# --- the aggregate's own rules ------------------------------------------------------


def test_the_transitions_refuse_out_of_order() -> None:
    """Unit-level, because HTTP cannot reach these guards.

    Every route resolves an item through `get_active_for_case`, which excludes non-ACTIVE
    rows, so a second delete is a 404 before any transition is attempted — mutating the
    guards away turns no integration test red. That makes them untested rather than
    unnecessary: the purge and any future caller reach the aggregate directly, and
    `mark_deleted` in particular must never run on an item whose access was never blocked.
    """
    from app.evidence.domain import EvidenceCategory, utcnow
    from app.shared.errors import IllegalTransition

    item = EvidenceItem.uploaded(
        case_id=uuid.uuid4(),
        category=EvidenceCategory.TRAVEL_SUPPORT,
        display_name="A booking",
        created_by="user_a",
    )
    at = utcnow()

    # A document whose access was never blocked cannot be marked deleted.
    with pytest.raises(IllegalTransition):
        item.mark_deleted(at=at)

    item.request_deletion(at=at)
    # Comparing `.value` rather than using `is`: an identity assertion narrows the property
    # for mypy, and the narrowing does not widen again when `mark_deleted` mutates it — so
    # the DELETED check below reads as unreachable code.
    assert item.lifecycle_status.value == EvidenceLifecycleStatus.DELETION_PENDING.value
    assert item.deleted_at is None, "not deleted yet — the bytes are still there"

    # And it cannot be requested twice.
    with pytest.raises(IllegalTransition):
        item.request_deletion(at=at)

    item.mark_deleted(at=at)
    assert item.lifecycle_status.value == EvidenceLifecycleStatus.DELETED.value
    assert item.deleted_at == at


# --- the purge ----------------------------------------------------------------------
#
# The storage *security* property — that a URL signed before the deletion 404s afterwards —
# is not asserted here. It lives in `test_storage_minio.py`, where slice 1 built it in
# anticipation of exactly this slice, and it must: §7.2's rule is that the in-memory fake
# asserts behaviour only and may never carry a security claim.
#
# So the division is deliberate. These tests hold "the purge deletes the object it should
# and records what it should", against the fake. That one holds "and nothing can reach a
# deleted object", against a real store. Neither is sufficient alone.


def _purge(evidence_item_id: uuid.UUID, *, storage: StorageAdapter | None = None) -> PurgeOutcome:
    """Run the purge on its own session, as the worker does.

    Not on `db_session`, for the reason `test_processing.py` records: sync endpoints run in
    a threadpool, so the TestClient mutates the shared session from another thread, and a
    versioned aggregate updated from both produces intermittent `StaleDataError`.
    """
    from app.shared.db import get_sessionmaker
    from app.shared.tenant import set_tenant

    with get_sessionmaker()() as session:
        set_tenant(session, "user_a")
        return purge_evidence(
            session,
            storage or get_storage(),
            evidence_item_id=evidence_item_id,
        )


def _store() -> InMemoryStorage:
    store = get_storage()
    assert isinstance(store, InMemoryStorage)
    return store


def test_the_purge_destroys_the_object_and_leaves_a_tombstone(
    api: Api, db_session: Session
) -> None:
    """§51.1 steps 3 and 7."""
    from app.evidence.domain import EvidenceFile, EvidenceFileText

    case_id, _ = _case_with_trip(api, "user_a")
    item_id = _document(api, "user_a", case_id, name="Amara's Athens booking")
    db_session.expire_all()
    file = db_session.execute(
        select(EvidenceFile).where(EvidenceFile.evidence_item_id == uuid.UUID(item_id))
    ).scalar_one()
    key = file.storage_key
    assert _store().head(key) is not None

    api("user_a").delete(f"/api/v1/cases/{case_id}/evidence/{item_id}")
    outcome = _purge(uuid.UUID(item_id))

    assert outcome.purged is True
    assert _store().head(key) is None, "the bytes are gone"

    db_session.expire_all()
    item = db_session.get(EvidenceItem, uuid.UUID(item_id))
    assert item is not None
    assert item.lifecycle_status.value == EvidenceLifecycleStatus.DELETED.value
    assert item.display_name == ""
    db_session.refresh(file)
    assert file.original_filename is None
    assert file.checksum == "", "a content fingerprint is exactly what a deletion removes"
    assert file.deleted_at is not None
    # The key survives: it identifies nothing the row does not already carry, and it is
    # what lets an operator re-check the object if a purge is ever suspected of failing.
    assert file.storage_key == key
    assert (
        db_session.execute(
            select(EvidenceFileText).where(EvidenceFileText.evidence_file_id == file.id)
        ).scalar_one_or_none()
        is None
    ), "there is no minimal non-sensitive version of a document's text"


def test_a_redelivered_purge_changes_nothing(api: Api, db_session: Session) -> None:
    """The relay is at-least-once, so the second pass is expected rather than exceptional.

    It must not raise, and it must not try to re-read a name or a checksum to decide what
    to do — on the second pass those are gone.
    """
    case_id, _ = _case_with_trip(api, "user_a")
    item_id = _document(api, "user_a", case_id)
    api("user_a").delete(f"/api/v1/cases/{case_id}/evidence/{item_id}")
    _purge(uuid.UUID(item_id))

    again = _purge(uuid.UUID(item_id))

    assert again.purged is False
    assert again.reason == "already_purged"


def test_the_purge_refuses_a_document_nobody_asked_to_delete(api: Api, db_session: Session) -> None:
    """The guard that matters most in this module.

    Destroying the content of a document a user can still reach would be the worst bug
    this code could have, so the only state it will act on is the one the delete command
    produces. It returns rather than raising: retrying cannot make an unrequested deletion
    correct.
    """
    from app.evidence.domain import EvidenceFile

    case_id, _ = _case_with_trip(api, "user_a")
    item_id = _document(api, "user_a", case_id)
    db_session.expire_all()
    key = (
        db_session.execute(
            select(EvidenceFile).where(EvidenceFile.evidence_item_id == uuid.UUID(item_id))
        )
        .scalar_one()
        .storage_key
    )

    outcome = _purge(uuid.UUID(item_id))

    assert outcome.purged is False
    assert outcome.reason == "not_pending"
    assert _store().head(key) is not None, "the bytes are untouched"
    assert api("user_a").get(f"/api/v1/cases/{case_id}/evidence/{item_id}").status_code == 200


def test_an_unreachable_store_leaves_the_document_pending_not_deleted(
    api: Api, db_session: Session
) -> None:
    """The honest incomplete state: access blocked, nothing depending on it, bytes still
    present. Marking DELETED here would be recording a destruction that did not happen."""
    from app.core.storage import StorageError

    case_id, _ = _case_with_trip(api, "user_a")
    item_id = _document(api, "user_a", case_id)
    api("user_a").delete(f"/api/v1/cases/{case_id}/evidence/{item_id}")

    class Unreachable(InMemoryStorage):
        def delete(self, key: str) -> None:
            raise StorageError("connection reset")

    with pytest.raises(StorageError):
        _purge(uuid.UUID(item_id), storage=Unreachable())

    db_session.expire_all()
    item = db_session.get(EvidenceItem, uuid.UUID(item_id))
    assert item is not None
    assert item.lifecycle_status.value == EvidenceLifecycleStatus.DELETION_PENDING.value
    assert item.display_name != "", "the tombstone is not written until the bytes are gone"


def test_deleting_an_unattached_document_still_reconciles_the_queue(
    api: Api, db_session: Session
) -> None:
    """A document supporting nothing stales no conclusion — but it still moves the queue.

    `mark_support_unavailable` withdraws no links, so it invalidates nothing, so nothing
    reconciles: reconciliation rides on invalidation. The desired issue set changed anyway,
    because any `DUPLICATE_EVIDENCE` item naming the document is now about something that
    does not exist.

    Found by a mutation that failed to turn a test red — the test was reading a queue
    nothing had re-derived, and passed for the wrong reason. Same shape as the fix
    `record_upload` needed in 4a.
    """
    case_id, _ = _case_with_trip(api, "user_a")
    first = _document(api, "user_a", case_id, name="One")
    _document(api, "user_a", case_id, name="Two")

    def duplicates() -> list[dict[str, object]]:
        queue = api("user_a").get(f"/api/v1/cases/{case_id}/issues").json()
        return [
            issue
            for group in queue["groups"]
            for issue in group["issues"]
            if issue["issue_type"] == "DUPLICATE_EVIDENCE"
        ]

    assert len(duplicates()) == 2, "identical bytes, so both copies are flagged"

    api("user_a").delete(f"/api/v1/cases/{case_id}/evidence/{first}")

    assert duplicates() == [], "one copy left, so nothing duplicates anything"


# --- the reviewers' two violations --------------------------------------------------


def test_deleting_the_case_does_not_cancel_a_pending_purge(api: Api, db_session: Session) -> None:
    """The user asked twice. Both times must be honoured.

    `purge_evidence`'s `CaseNoLongerWritable` branch used to return early, on the stated
    grounds that "the case is being deleted, and its own purge owns the bytes now". No
    such owner exists: `CaseDeletionRequested` is in `NO_CONSUMER` until M11, so the work
    was not handed over — it was dropped, with no log line and no retry. The object stayed
    in the bucket, and so did the display name, the filename, the checksum and the whole
    extracted text.

    The window is ordinary rather than exotic: any lag between deleting a document and
    deleting the case, which is exactly what a slow or restarting worker produces.
    """
    from app.evidence.domain import EvidenceFile

    case_id, _ = _case_with_trip(api, "user_a")
    item_id = _document(api, "user_a", case_id)
    db_session.expire_all()
    key = (
        db_session.execute(
            select(EvidenceFile).where(EvidenceFile.evidence_item_id == uuid.UUID(item_id))
        )
        .scalar_one()
        .storage_key
    )

    api("user_a").delete(f"/api/v1/cases/{case_id}/evidence/{item_id}")
    # The case goes before the relay dispatched the purge.
    assert api("user_a").delete(f"/api/v1/cases/{case_id}").status_code in (200, 204)

    # Through the **task**, not `purge_evidence` directly. The gate is in `case_task`, so
    # a test that calls the pipeline function bypasses the very thing it is checking —
    # which this one did on its first draft, and passed with the defect restored.
    from worker.tasks import purge_evidence as purge_task

    result = purge_task.apply(
        kwargs={"outbox_event_id": str(uuid.uuid4()), "aggregate_id": item_id}
    ).get()

    assert result["purged"] is True, "a deleted case must not cancel a deletion"
    assert _store().head(key) is None, "the bytes are gone"

    db_session.expire_all()
    item = db_session.get(EvidenceItem, uuid.UUID(item_id))
    assert item is not None
    assert item.lifecycle_status.value == EvidenceLifecycleStatus.DELETED.value
    assert item.display_name == ""


def test_the_purged_document_name_does_not_survive_in_the_issue_queue(
    api: Api, db_session: Session
) -> None:
    """The tombstone's argument does not stop at a table boundary.

    `display_name` is cleared from `evidence_items` because it is the user's own words for
    their document. `DUPLICATE_EVIDENCE` copies that string into `message_parameters` —
    twice, since the surviving twin carries it as `other_name` — and resolving an issue
    touches only status and `resolved_at`. So the name outlived the document it named.
    """
    from app.issues.domain import Issue, IssueType

    case_id, _ = _case_with_trip(api, "user_a")
    first = _document(api, "user_a", case_id, name="Amara Athens booking")
    # A name that is not a substring of the first, or the assertions below pass by accident.
    second = _document(api, "user_a", case_id, name="Second upload")

    api("user_a").delete(f"/api/v1/cases/{case_id}/evidence/{first}")
    _purge(uuid.UUID(first))

    db_session.expire_all()
    parameters = [
        issue.message_parameters
        for issue in db_session.execute(
            select(Issue).where(
                Issue.case_id == uuid.UUID(case_id),
                Issue.issue_type == IssueType.DUPLICATE_EVIDENCE.value,
            )
        ).scalars()
    ]

    assert parameters, "the duplicate issues must exist for this to be testing anything"
    for row in parameters:
        assert row.get("display_name") != "Amara Athens booking"
        assert row.get("other_name") != "Amara Athens booking"

    # The surviving document keeps its own name: this clears what was destroyed, not the
    # queue's ability to name what is still there.
    survivor = api("user_a").get(f"/api/v1/cases/{case_id}/evidence/{second}").json()
    assert survivor["display_name"] == "Second upload"


def test_deletion_leaves_no_fingerprint_of_the_analysed_document(
    api: Api, db_session: Session
) -> None:
    """`purge.py` already clears `checksum` because it is a content fingerprint — anyone
    with database access could hash a document they suspect and confirm it was uploaded
    here, which is the question deletion exists to stop answering.

    `extraction_runs.input_hash` is that same fingerprint over the same document, one
    table over, and `classification_reasoning` is model prose the classifier prompt
    explicitly permits to quote from the document. Slice 2 added both and did not extend
    the purge; both slice-2 reviews caught it independently.
    """
    from app.ai.extraction_run import ExtractionRun
    from tests.evidence.test_processing import _process, classifying

    case_id, _ = _case_with_trip(api, "user_a")
    item_id = uuid.UUID(_document(api, "user_a", case_id))
    _process(item_id, idempotency_key="purge-1", provider=classifying())

    def _classifier_run() -> ExtractionRun:
        db_session.expire_all()
        runs = db_session.execute(
            select(ExtractionRun).where(ExtractionRun.evidence_item_id == item_id)
        ).scalars()
        return next(r for r in runs if r.classified_category)

    before = _classifier_run()
    assert before.input_hash and before.classification_reasoning

    api("user_a").delete(f"/api/v1/cases/{case_id}/evidence/{item_id}")
    _purge(item_id)

    after = _classifier_run()
    assert after.input_hash == "", "a content fingerprint survived deletion"
    assert after.classification_reasoning is None, "model prose about the document survived"
    # What identifies nothing stays, so the spend ledger still joins to a run that says
    # an analysis happened. Erasing it would make a deleted document indistinguishable
    # from one that was never analysed — a different claim than deletion should make.
    assert after.classified_category == "TRAVEL_SUPPORT"
    assert after.model_run_id is not None


def test_deletion_erases_the_document_words_a_claim_was_holding(
    api: Api, db_session: Session
) -> None:
    """A claim quotes the document, so a purge that skipped it kept the document.

    `proposed_raw` is verbatim: the traveller's name as printed, the booking reference,
    the date in the words the page used. `evidence_file_texts` is deleted outright
    because there is no minimal non-sensitive version of a document's text — and a claim
    holds the same text in a second table, cut into the fields that matter most.
    """
    from app.facts.domain import ExtractedClaim
    from tests.evidence.test_processing import _process, classifying

    case_id, _ = _case_with_trip(api, "user_a")
    item_id = uuid.UUID(_document(api, "user_a", case_id))
    _process(item_id, idempotency_key="purge-2", provider=classifying())

    def _claims() -> list[ExtractedClaim]:
        db_session.expire_all()
        return list(
            db_session.execute(
                select(ExtractedClaim).where(ExtractedClaim.evidence_item_id == item_id)
            ).scalars()
        )

    before = _claims()
    assert before, "the fixture produced no claims, so this test proves nothing"
    assert any(c.proposed_raw == "OKONKWO / AMARA MS" for c in before)

    api("user_a").delete(f"/api/v1/cases/{case_id}/evidence/{item_id}")
    _purge(item_id)

    after = _claims()
    assert len(after) == len(before), "claims were deleted rather than cleared"
    for claim in after:
        assert claim.proposed_raw == "", "the document's own words survived deletion"
        assert claim.proposed_iso is None
        assert claim.normalised_value is None
        assert claim.source_locator is None
        # The row survives because a confirmed fact's provenance runs decision → claim.
        # What is left names no document and no person.
        assert claim.claim_type
        assert claim.extraction_run_id


def test_deleting_a_document_withdraws_the_support_under_a_confirmed_fact(
    api: Api, db_session: Session
) -> None:
    """CLAUDE.md §9: *"deleting evidence cannot leave its support state as available."*

    Written because the mutation table found nothing guarding it. Making the fact-link
    sweep in `mark_support_unavailable` a no-op left the whole suite green: every
    existing deletion test covers `EvidenceTravelLink`, which M7 built, and the fact
    links slice 3a added had no equivalent.

    Both halves matter and they pull opposite ways. The fact **survives** — RFC §19 is
    explicit that deleting a document does not delete a value a human confirmed, and the
    trip date is still the trip date. What must not survive is the claim that the value
    is *evidenced*: a fact still showing an available link to a destroyed file is the
    product asserting support that cannot be produced.
    """
    from app.facts.domain import FactEvidenceLink, FactVersion, LinkAvailability
    from tests.evidence.test_processing import _process, classifying

    case_id, _ = _case_with_trip(api, "user_a")
    item_id = uuid.UUID(_document(api, "user_a", case_id))
    _process(item_id, idempotency_key="fact-link-1", provider=classifying())

    queue = api("user_a").get(f"/api/v1/cases/{case_id}/claims").json()["items"]
    departure = next(c for c in queue if c["claim_type"] == "travel.departure_date")
    confirmed = api("user_a").post(
        f"/api/v1/cases/{case_id}/claims/{departure['id']}/review",
        json={"decision": "CONFIRM", "entered_value": "4 May 2026"},
    )
    assert confirmed.status_code == 201, confirmed.text

    db_session.expire_all()
    link = db_session.execute(select(FactEvidenceLink)).scalar_one()
    assert link.availability_status == LinkAvailability.AVAILABLE.value

    api("user_a").delete(f"/api/v1/cases/{case_id}/evidence/{item_id}")

    db_session.expire_all()
    link = db_session.execute(select(FactEvidenceLink)).scalar_one()
    assert link.availability_status == LinkAvailability.DELETED.value, (
        "a confirmed fact still claims support from a document that is being destroyed"
    )
    assert link.withdrawn_at is not None
    version = db_session.execute(select(FactVersion)).scalar_one()
    # ISO, because a blind date entry is parsed to a calendar date before it is stored —
    # the words are the document's, and the date is the user's.
    assert version.raw_value == "2026-05-04", "the value the user confirmed was destroyed too"


def test_deleting_a_document_closes_the_claims_nobody_had_decided_about(
    api: Api, db_session: Session
) -> None:
    """The offer to create a fact ends when the document does — and at deletion, not at
    purge.

    Blind confirmation asks the user to read the page and type what it says. Once access
    is blocked they cannot, so a claim still `PENDING_REVIEW` would present an empty box
    beside a source region that 404s, and whatever was typed would become a trusted fact
    backed by nothing. Purge is asynchronous and retryable, so waiting for it leaves a
    window in which the review endpoint still answers.
    """
    from app.facts.domain import ClaimStatus, ExtractedClaim
    from tests.evidence.test_processing import _process, classifying

    case_id, _ = _case_with_trip(api, "user_a")
    item_id = uuid.UUID(_document(api, "user_a", case_id))
    _process(item_id, idempotency_key="purge-3", provider=classifying())

    queue = api("user_a").get(f"/api/v1/cases/{case_id}/claims").json()["items"]
    assert queue, "no pending claims to invalidate"
    claim_id = queue[0]["id"]

    api("user_a").delete(f"/api/v1/cases/{case_id}/evidence/{item_id}")

    db_session.expire_all()
    statuses = {
        c.status
        for c in db_session.execute(
            select(ExtractedClaim).where(ExtractedClaim.evidence_item_id == item_id)
        ).scalars()
    }
    assert statuses == {ClaimStatus.INVALIDATED.value}
    assert api("user_a").get(f"/api/v1/cases/{case_id}/claims").json()["items"] == []

    # Before the purge has run — the window this test exists to close.
    refused = api("user_a").post(
        f"/api/v1/cases/{case_id}/claims/{claim_id}/review",
        json={"decision": "CONFIRM", "entered_value": "4 May 2026"},
    )
    assert refused.status_code == 409
