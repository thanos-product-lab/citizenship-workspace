"""A confirmed document date that disagrees with the trip, through the real command path.

`test_conflicts.py` proves the comparison. This proves the *wiring*, and specifically the
half that a partial implementation would drop: RULES_SPEC §6.1 excludes a `CONFLICTING`
trip from the trusted total, so the figure is **held back**, not quietly built from a date
two sources disagree about.
"""

import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

pytestmark = pytest.mark.integration

Api = Callable[[str], TestClient]

SUPPORTED_ANSWERS = {
    "date_of_birth": "1990-05-01",
    "status_type": "ILR",
    "status_granted_on": "2019-01-01",
    "married_to_british_citizen": False,
    "may_already_be_british": False,
}

#: One trip well inside the qualifying window and clear of the presence anchor, so the only
#: thing that can move its contribution is the conflict under test.
#:
#: 29 absent days, not 30: the departure and return days are UK days and never count
#: (RULES_SPEC §5.1), so `1 June → 1 July` is the 29 days between them.
DEPARTURE = "2023-06-01"
RECORDED_RETURN = "2023-07-01"
ABSENT_DAYS = 29


def _case_with_trip(api: Api) -> tuple[str, str]:
    case_id = str(api("user_a").post("/api/v1/cases", json={"title": "Conflict"}).json()["id"])
    api("user_a").put(f"/api/v1/cases/{case_id}/route-profile", json=SUPPORTED_ANSWERS)
    api("user_a").post(f"/api/v1/cases/{case_id}/route-profile/confirm", json={})
    api("user_a").post(
        f"/api/v1/cases/{case_id}/application-dates/select",
        json={"application_date": "2027-04-15"},
    )
    trip_id = str(
        api("user_a")
        .post(
            f"/api/v1/cases/{case_id}/travel-records",
            json={
                "destination_label": "Rome",
                "departure_date": DEPARTURE,
                "return_date": RECORDED_RETURN,
                "date_confidence": "EXACT",
                "review_state": "CONFIRMED",
            },
        )
        .json()["id"]
    )
    return case_id, trip_id


def _attach_document(api: Api, case_id: str, trip_id: str) -> str:
    from app.core.storage import InMemoryStorage, get_storage
    from tests.evidence.conftest import fixture_bytes

    content = fixture_bytes("travel-booking.pdf")
    grant = (
        api("user_a")
        .post(
            f"/api/v1/cases/{case_id}/evidence/uploads",
            json={"media_type": "application/pdf", "declared_size_bytes": len(content)},
        )
        .json()
    )
    store = get_storage()
    assert isinstance(store, InMemoryStorage)
    store.put(str(grant["upload_fields"]["key"]), content)
    item_id = str(
        api("user_a")
        .post(
            f"/api/v1/cases/{case_id}/evidence",
            json={
                "upload_token": grant["upload_token"],
                "category": "TRAVEL_SUPPORT",
                "display_name": "Rome booking",
                "original_filename": "booking.pdf",
            },
        )
        .json()["id"]
    )
    api("user_a").post(
        f"/api/v1/cases/{case_id}/travel-records/{trip_id}/evidence",
        json={"evidence_item_id": item_id},
    )
    return item_id


def _propose(session: Session, case_id: str, item_id: str, *, raw: str) -> uuid.UUID:
    """A pending `travel.return_date` claim on that document.

    Built through the domain rather than by running a model: this file asks what happens
    *after* a value is confirmed, and driving a provider to get a claim would make it depend
    on a network and a budget to answer that.
    """
    from app.ai.domain import Capability
    from app.ai.extraction_run import ExtractionRun, ExtractionRunStatus
    from app.evidence.domain import (
        PIPELINE_VERSION,
        EvidenceFile,
        EvidenceProcessingRun,
        ProcessingRunStatus,
    )
    from app.facts.domain import ClaimType, ExtractedClaim
    from app.facts.values import ProposedValue, ValueSchema

    item = uuid.UUID(item_id)
    file = session.scalar(select(EvidenceFile).where(EvidenceFile.evidence_item_id == item))
    assert file is not None
    processing = EvidenceProcessingRun(
        evidence_item_id=item,
        evidence_file_id=file.id,
        status=ProcessingRunStatus.SUCCEEDED.value,
        pipeline_version=PIPELINE_VERSION,
        completed_at=datetime.now(UTC),
        idempotency_key=f"conflict-{uuid.uuid4()}",
    )
    session.add(processing)
    session.flush()
    run = ExtractionRun.record(
        case_id=uuid.UUID(case_id),
        evidence_item_id=item,
        evidence_file_id=file.id,
        processing_run_id=processing.id,
        capability=Capability.TRAVEL_RECORD_EXTRACTOR.value,
        status=ExtractionRunStatus.SUCCEEDED,
        input_text="a booking",
        started_at=datetime.now(UTC),
    )
    session.add(run)
    session.flush()
    claim = ExtractedClaim.propose(
        case_id=uuid.UUID(case_id),
        evidence_item_id=item,
        evidence_file_id=file.id,
        extraction_run_id=run.id,
        claim_type=ClaimType.TRAVEL_RETURN_DATE,
        value=ProposedValue(schema=ValueSchema.DATE_V1, raw=raw, model_iso=None),
    )
    session.add(claim)
    session.flush()
    session.commit()
    return claim.id


def _detail(api: Api, case_id: str, key: str) -> dict[str, Any]:
    body: dict[str, Any] = api("user_a").get(f"/api/v1/cases/{case_id}/requirements/{key}").json()
    return body


def _conflicting_case(api: Api, session: Session) -> tuple[str, str]:
    """A case whose booking has been confirmed as 2 July while the trip says 1 July."""
    case_id, trip_id = _case_with_trip(api)
    item_id = _attach_document(api, case_id, trip_id)
    claim_id = _propose(session, case_id, item_id, raw="2 July 2023")
    api("user_a").post(
        f"/api/v1/cases/{case_id}/claims/{claim_id}/review",
        json={"entered_value": "2 July 2023"},
    )
    return case_id, trip_id


def test_a_disputed_trip_is_held_back_from_the_trusted_total(api: Api, db_session: Session) -> None:
    """**Mutation-table row 15**, and the half of §6.1 a partial implementation drops.

    *"Anything else — UNCERTAIN, ESTIMATED, CONFLICTING, DRAFT — is excluded from trusted
    totals."* Marking the trip `CONFLICTING` for the consistency verdict while still
    counting its days would apply half of §6.1 and contradict the other half inside one
    evaluation — the user would be told the date is disputed and shown a confirmed figure
    built from it.

    `provisional_days` still carries the trip, which is what makes the difference legible:
    the days did not vanish, they stopped being *confirmed*.
    """
    case_id, _trip_id = _conflicting_case(api, db_session)
    api("user_a").post(f"/api/v1/cases/{case_id}/assessments/recalculate")

    total = _detail(api, case_id, "residence.total_absences")

    assert total["summary_parameters"]["days"] == 0, "a disputed trip counted as confirmed"
    assert total["summary_parameters"]["provisional_days"] == ABSENT_DAYS


def test_the_consistency_verdict_says_the_sources_disagree(api: Api, db_session: Session) -> None:
    """§7.8's `CONFLICTING_SOURCE_DATES` → `INCONSISTENT`, reached for the first time by
    something other than a test. Not one line of the rule changed to make this work."""
    case_id, _trip_id = _conflicting_case(api, db_session)
    api("user_a").post(f"/api/v1/cases/{case_id}/assessments/recalculate")

    consistency = _detail(api, case_id, "residence.travel_consistency")

    assert consistency["conclusion"] == "INCONSISTENT"
    codes = [limitation["code"] for limitation in consistency["limitations"]]
    assert "CONFLICTING_SOURCE_DATES" in codes


def test_confirming_a_value_stales_what_depended_on_it(api: Api, db_session: Session) -> None:
    """**Mutation-table row 17.** The `CASE_FACT` seam slice 3a shipped without.

    In the review's own transaction (Domain §41.2): a user told their value was accepted
    must not then be able to read a conclusion that predates it.
    """
    case_id, trip_id = _case_with_trip(api)
    item_id = _attach_document(api, case_id, trip_id)
    api("user_a").post(f"/api/v1/cases/{case_id}/assessments/recalculate")
    assert _detail(api, case_id, "residence.travel_consistency")["currency"] == "CURRENT"

    claim_id = _propose(db_session, case_id, item_id, raw="2 July 2023")
    api("user_a").post(
        f"/api/v1/cases/{case_id}/claims/{claim_id}/review",
        json={"entered_value": "2 July 2023"},
    )

    consistency = _detail(api, case_id, "residence.travel_consistency")
    assert consistency["currency"] == "STALE"
    # Nested, and present only while STALE — a CURRENT result carries no stale block at all,
    # so a client cannot render a stale notice over a conclusion that is still good.
    assert consistency["stale"]["reason_code"] == "CASE_FACT_CHANGED"


def test_a_value_that_agrees_changes_nothing(api: Api, db_session: Session) -> None:
    """Corroboration is not conflict (RFC §16). The trip stays trusted and the verdict stays
    clean — otherwise every confirmed booking would make its own trip look disputed."""
    case_id, trip_id = _case_with_trip(api)
    item_id = _attach_document(api, case_id, trip_id)
    claim_id = _propose(db_session, case_id, item_id, raw="1 July 2023")
    api("user_a").post(
        f"/api/v1/cases/{case_id}/claims/{claim_id}/review",
        json={"entered_value": "1 July 2023"},
    )
    api("user_a").post(f"/api/v1/cases/{case_id}/assessments/recalculate")

    assert (
        _detail(api, case_id, "residence.total_absences")["summary_parameters"]["days"]
        == ABSENT_DAYS
    )
    assert _detail(api, case_id, "residence.travel_consistency")["conclusion"] == "SUPPORTED"


def test_a_confirmed_value_on_an_unattached_document_conflicts_with_nothing(
    api: Api, db_session: Session
) -> None:
    """The link is the authority (RFC §42.1). A booking the user has not filed against a
    trip must not argue with one — on a case with a dozen trips, comparing against all of
    them would turn one unfiled document into a dozen conflicts."""
    case_id, trip_id = _case_with_trip(api)
    item_id = _attach_document(api, case_id, trip_id)
    # Detach it again, so the document is live and the trip is live and nothing joins them.
    detached = api("user_a").delete(
        f"/api/v1/cases/{case_id}/travel-records/{trip_id}/evidence/{item_id}"
    )
    assert detached.status_code == 200, detached.text
    claim_id = _propose(db_session, case_id, item_id, raw="2 July 2023")
    api("user_a").post(
        f"/api/v1/cases/{case_id}/claims/{claim_id}/review",
        json={"entered_value": "2 July 2023"},
    )
    api("user_a").post(f"/api/v1/cases/{case_id}/assessments/recalculate")

    assert (
        _detail(api, case_id, "residence.total_absences")["summary_parameters"]["days"]
        == ABSENT_DAYS
    )
    assert _detail(api, case_id, "residence.travel_consistency")["conclusion"] != "INCONSISTENT"


def _issues(api: Api, case_id: str) -> list[dict[str, Any]]:
    """Every open issue, flattened out of the action groups the queue returns."""
    body: dict[str, Any] = api("user_a").get(f"/api/v1/cases/{case_id}/issues").json()
    return [issue for group in body["groups"] for issue in group["issues"]]


def _conflicts(api: Api, case_id: str) -> list[dict[str, Any]]:
    return [i for i in _issues(api, case_id) if i["issue_type"] == "CONFLICTING_CLAIMS"]


def test_the_queue_names_both_values_and_the_document(api: Api, db_session: Session) -> None:
    """`IssueType.CONFLICTING_CLAIMS`, deferred since M3A waiting for evidence to disagree
    with, reached at last.

    Both values in the message, because "these disagree" without saying what disagrees
    sends the user hunting for the comparison the product has already made.
    """
    case_id, trip_id = _conflicting_case(api, db_session)
    api("user_a").post(f"/api/v1/cases/{case_id}/assessments/recalculate")

    conflicts = [
        item for item in _issues(api, case_id) if item["issue_type"] == "CONFLICTING_CLAIMS"
    ]

    assert len(conflicts) == 1, "one item per trip, not one per disagreeing field"
    issue = conflicts[0]
    assert issue["affected_object_id"] == trip_id
    assert "Rome" in issue["title"]
    assert "Rome booking" in issue["title"]
    # Formatted, not ISO. `format_date` exists because UI/UX §13.3 says an ISO string in
    # a sentence reads as machine output, and this card's whole job is making two
    # human-entered dates comparable.
    assert "1 July 2023" in issue["body"]
    assert "2 July 2023" in issue["body"]


def test_a_conflict_cannot_be_dismissed(api: Api, db_session: Session) -> None:
    """**Mutation-table row 19.** MVP §8.11: *"conflicting claims remain unresolved until
    the user chooses or provides another source."*

    A Dismiss control would let the queue go quiet while two sources still disagree — and
    while a trip is being held back from the confirmed total because of it, which is the
    part a quiet queue would make inexplicable.
    """
    case_id, _trip_id = _conflicting_case(api, db_session)
    api("user_a").post(f"/api/v1/cases/{case_id}/assessments/recalculate")

    issue = next(iter(_conflicts(api, case_id)))
    assert issue["dismissibility"] == "NOT_DISMISSIBLE"

    refused = api("user_a").post(f"/api/v1/cases/{case_id}/issues/{issue['id']}/dismiss")
    assert refused.status_code == 409


def test_rejecting_the_claim_clears_the_conflict(api: Api, db_session: Session) -> None:
    """One of the two existing outs the issue points at, and it needs no new code.

    If the record is right, the model misread the document — and rejecting the value is
    already a command. The fact stops being confirmed, so nothing disagrees with the trip
    and the days come back into the confirmed total.
    """
    case_id, trip_id = _case_with_trip(api)
    item_id = _attach_document(api, case_id, trip_id)
    claim_id = _propose(db_session, case_id, item_id, raw="2 July 2023")
    api("user_a").post(
        f"/api/v1/cases/{case_id}/claims/{claim_id}/review",
        json={"decision": "REJECT", "reason_code": "WRONG_DOCUMENT"},
    )
    api("user_a").post(f"/api/v1/cases/{case_id}/assessments/recalculate")

    assert (
        _detail(api, case_id, "residence.total_absences")["summary_parameters"]["days"]
        == ABSENT_DAYS
    )
    assert not _conflicts(api, case_id)


def _adopt(api: Api, case_id: str, trip_id: str) -> Any:
    return api("user_a").post(
        f"/api/v1/cases/{case_id}/travel-records/{trip_id}/adopt-document-dates"
    )


def test_adopting_the_document_date_resolves_the_conflict_and_moves_the_total(
    api: Api, db_session: Session
) -> None:
    """SYNTHETIC_DEMO_CASE §7, in miniature: the whole sequence the milestone exists to show.

    Confirm → held back → adopt → recalculate → the figure moves and the conclusion does
    not. The one-day change is the point: `conclusion` and `currency` are separate
    dimensions (ADR-0001), and a fixture where the band also flipped would conflate them.
    """
    case_id, trip_id = _conflicting_case(api, db_session)
    api("user_a").post(f"/api/v1/cases/{case_id}/assessments/recalculate")
    before = _detail(api, case_id, "residence.total_absences")
    assert before["summary_parameters"]["days"] == 0, "the disputed trip was counted"

    adopted = _adopt(api, case_id, trip_id)
    assert adopted.status_code == 200, adopted.text

    # Staled by the trip write, in that command's own transaction.
    assert _detail(api, case_id, "residence.total_absences")["currency"] == "STALE"

    api("user_a").post(f"/api/v1/cases/{case_id}/assessments/recalculate")
    after = _detail(api, case_id, "residence.total_absences")

    # 30, not 29: the trip is a day longer now, and trusted again because nothing disagrees.
    assert after["summary_parameters"]["days"] == ABSENT_DAYS + 1
    assert after["currency"] == "CURRENT"
    assert after["conclusion"] == before["conclusion"], "the conclusion moved; the band should not"
    assert not _conflicts(api, case_id)
    assert _detail(api, case_id, "residence.travel_consistency")["conclusion"] == "SUPPORTED"


def test_adopting_records_that_the_dates_came_from_a_document(
    api: Api, db_session: Session
) -> None:
    """`EntrySource.CONFIRMED_CLAIM`, whose first producer this is.

    It is what lets a later reader tell a date the user typed from one they took off a
    document they had already confirmed — and the previous version is retained, so the
    history says what the trip used to claim.
    """
    from app.residence.domain import EntrySource, TravelRecordVersion

    case_id, trip_id = _conflicting_case(api, db_session)
    _adopt(api, case_id, trip_id)

    db_session.expire_all()
    versions = sorted(
        db_session.scalars(
            select(TravelRecordVersion).where(
                TravelRecordVersion.travel_record_id == uuid.UUID(trip_id)
            )
        ),
        key=lambda v: v.version_number,
    )

    assert len(versions) == 2, "the previous version was not retained"
    assert versions[0].entry_source == EntrySource.MANUAL.value
    assert versions[0].return_date.isoformat() == RECORDED_RETURN
    assert versions[1].entry_source == EntrySource.CONFIRMED_CLAIM.value
    assert versions[1].return_date.isoformat() == "2023-07-02"
    assert versions[1].supersedes_version_id == versions[0].id


def test_adopting_when_nothing_is_in_conflict_is_refused(api: Api, db_session: Session) -> None:
    """**Mutation-table row 20.** An action that silently does nothing is how a user comes
    to believe they resolved something — and this one is offered from a queue that can be a
    few seconds stale, so arriving with nothing to do is expected, not exceptional."""
    case_id, trip_id = _case_with_trip(api)
    _attach_document(api, case_id, trip_id)

    refused = _adopt(api, case_id, trip_id)

    assert refused.status_code == 409
    assert refused.json()["code"] == "NO_CONFLICT_TO_RESOLVE"


def test_adopting_twice_is_refused_the_second_time(api: Api, db_session: Session) -> None:
    """The double-click case, and the reason the refusal is a 409 rather than a silent
    success: after the first adoption the two sources agree, so there is genuinely nothing
    left to resolve and saying so is more honest than writing an identical version."""
    case_id, trip_id = _conflicting_case(api, db_session)
    assert _adopt(api, case_id, trip_id).status_code == 200

    assert _adopt(api, case_id, trip_id).status_code == 409
