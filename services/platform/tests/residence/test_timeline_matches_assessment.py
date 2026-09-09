"""The timeline and the assessment must publish the same figure.

Both surfaces answer "how many days outside the UK, from confirmed records". Until M8 they
answered it from one implementation of the §6.1 gate by coincidence: `timeline.get_timeline`
called `counts_toward_trusted_total` off the stored row, and so did the assessment service.

Slice 4 gave a trip a second way to fail that gate — a confirmed document date disputing it —
and applied it in `assessments.service.gather_trips` only. The projection never saw it, so on
a case with a conflict the timeline reported the trip as counted and the assessment reported
it held back. **The whole backend suite stayed green**, because no test compared the two.

That is what this file is: not a second oracle, but an equality. `test_timeline.py` asserts
figures transcribed by hand from `SYNTHETIC_DEMO_CASE.md`, which is right and which passed
throughout the divergence — a hand-transcribed number cannot notice that a *different*
surface disagrees with it. Asserting the two surfaces against each other catches the next
divergence without anyone remembering to add a case for it.
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


def _case_with_trip(
    api: Api, *, departs: str = "2023-06-01", returns: str = "2023-07-01"
) -> tuple[str, str]:
    case_id = str(api("user_a").post("/api/v1/cases", json={"title": "Surfaces"}).json()["id"])
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
                "departure_date": departs,
                "return_date": returns,
                "date_confidence": "EXACT",
                "review_state": "CONFIRMED",
            },
        )
        .json()["id"]
    )
    return case_id, trip_id


def _dispute_the_trip(api: Api, session: Session, case_id: str, trip_id: str) -> None:
    """Attach a booking to the trip and confirm a return date one day later than recorded.

    Built through the domain rather than by running a model, for the reason
    `test_conflict_assessment.py` gives: this file asks what happens *after* a value is
    confirmed, and driving a provider to get there would make it depend on a network.
    """
    from app.ai.domain import Capability
    from app.ai.extraction_run import ExtractionRun, ExtractionRunStatus
    from app.core.storage import InMemoryStorage, get_storage
    from app.evidence.domain import (
        PIPELINE_VERSION,
        EvidenceFile,
        EvidenceProcessingRun,
        ProcessingRunStatus,
    )
    from app.facts.domain import ClaimType, ExtractedClaim
    from app.facts.values import ProposedValue, ValueSchema
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

    item = uuid.UUID(item_id)
    file = session.scalar(select(EvidenceFile).where(EvidenceFile.evidence_item_id == item))
    assert file is not None
    processing = EvidenceProcessingRun(
        evidence_item_id=item,
        evidence_file_id=file.id,
        status=ProcessingRunStatus.SUCCEEDED.value,
        pipeline_version=PIPELINE_VERSION,
        completed_at=datetime.now(UTC),
        idempotency_key=f"surfaces-{uuid.uuid4()}",
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
        value=ProposedValue(schema=ValueSchema.DATE_V1, raw="2 July 2023", model_iso=None),
    )
    session.add(claim)
    session.flush()
    session.commit()

    api("user_a").post(
        f"/api/v1/cases/{case_id}/claims/{claim.id}/review",
        json={"entered_value": "2 July 2023"},
    )


def _surfaces(api: Api, case_id: str) -> tuple[Any, dict[str, Any]]:
    api("user_a").post(f"/api/v1/cases/{case_id}/assessments/recalculate")
    timeline = api("user_a").get(f"/api/v1/cases/{case_id}/timeline").json()
    requirements = {
        key: api("user_a").get(f"/api/v1/cases/{case_id}/requirements/{key}").json()
        for key in (
            "residence.total_absences",
            "residence.final_year_absences",
            "residence.physical_presence_start_date",
        )
    }
    return timeline, requirements


def _assert_surfaces_agree(timeline: Any, requirements: dict[str, Any]) -> None:
    """The invariant, stated once and reused by every case below."""
    totals = timeline["totals"]
    total_absences = requirements["residence.total_absences"]["summary_parameters"]
    final_year = requirements["residence.final_year_absences"]["summary_parameters"]

    assert totals["qualifying_period_days"] == total_absences["days"], (
        "the timeline and residence.total_absences disagree about the confirmed figure"
    )
    assert totals["final_year_days"] == final_year["days"]
    # And the provisional pair, which is the same gate read the other way round.
    assert (
        totals["qualifying_period_days_including_all_records"]
        == (total_absences["provisional_days"])
    )
    assert totals["final_year_days_including_all_records"] == final_year["provisional_days"]

    # The presence anchor is a membership test over the same two sets, so it moves with them.
    presence = requirements["residence.physical_presence_start_date"]
    if timeline["presence_anchor_is_absent"]:
        assert presence["conclusion"] == "NOT_CURRENTLY_SATISFIED"
    elif timeline["presence_anchor_is_absent_including_all_records"]:
        # In the provisional set only: the rule cannot settle it, and the timeline must not
        # state the user was in the UK on the strength of a record being held back.
        assert presence["conclusion"] == "INCOMPLETE"
    else:
        assert presence["conclusion"] == "SUPPORTED"


def test_the_two_surfaces_agree_on_an_ordinary_case(api: Api, db_session: Session) -> None:
    case_id, _ = _case_with_trip(api)
    _assert_surfaces_agree(*_surfaces(api, case_id))


def test_the_two_surfaces_agree_when_a_document_disputes_a_trip(
    api: Api, db_session: Session
) -> None:
    """The case that was broken. The trip is confirmed with exact dates and still held back,
    so a surface deciding trust from the stored row reports it as counted."""
    case_id, trip_id = _case_with_trip(api)
    _dispute_the_trip(api, db_session, case_id, trip_id)

    timeline, requirements = _surfaces(api, case_id)
    _assert_surfaces_agree(timeline, requirements)

    # And the timeline says *why*, rather than silently dropping the trip from its total.
    assert timeline["totals"]["held_back_trip_count"] == 1
    assert timeline["totals"]["conflicted_trip_count"] == 1
    trip = next(t for t in timeline["trips"] if t["travel_record_id"] == trip_id)
    assert trip["is_trusted"] is False
    assert trip["date_confidence"] == "CONFLICTING"
    # The record itself is untouched: the conflict is derived, never stored (RFC §42).
    assert trip["review_state"] == "CONFIRMED"


def test_the_two_surfaces_agree_when_a_disputed_trip_covers_the_presence_anchor(
    api: Api, db_session: Session
) -> None:
    """The reassuring direction, pinned.

    A trip covering the anchor and then disputed leaves the *trusted* absent set, so
    `presence_anchor_is_absent` flips false — and the view renders that as "you were in the
    UK on this day". The provisional flag is what stops that being asserted on the strength
    of a record the totals are refusing to count.
    """
    # The anchor is 16 April 2022 — the first day of the window for a 15 April 2027
    # application. Departing on the 10th and returning on the 25th puts it inside the trip's
    # absent set, which is exclusive of both travel days (RULES_SPEC §5.1).
    case_id, trip_id = _case_with_trip(api, departs="2022-04-10", returns="2022-04-25")
    _dispute_the_trip(api, db_session, case_id, trip_id)

    timeline, requirements = _surfaces(api, case_id)
    _assert_surfaces_agree(timeline, requirements)

    assert timeline["presence_anchor_is_absent"] is False
    assert timeline["presence_anchor_is_absent_including_all_records"] is True
    assert requirements["residence.physical_presence_start_date"]["conclusion"] == "INCOMPLETE"


def test_the_two_surfaces_agree_once_the_conflict_is_resolved(
    api: Api, db_session: Session
) -> None:
    """Adopting the document's dates must bring both surfaces back together, not just one."""
    case_id, trip_id = _case_with_trip(api)
    _dispute_the_trip(api, db_session, case_id, trip_id)
    api("user_a").post(f"/api/v1/cases/{case_id}/assessments/recalculate")

    api("user_a").post(
        f"/api/v1/cases/{case_id}/travel-records/{trip_id}/adopt-document-dates", json={}
    )

    timeline, requirements = _surfaces(api, case_id)
    _assert_surfaces_agree(timeline, requirements)
    assert timeline["totals"]["held_back_trip_count"] == 0
    assert timeline["totals"]["conflicted_trip_count"] == 0


def test_the_travel_records_api_says_a_disputed_trip_is_not_trusted(
    api: Api, db_session: Session
) -> None:
    """The fourth reader, closed at the boundary rather than in the client.

    The Case data page computed `review_state === "CONFIRMED" && date_confidence ===
    "EXACT"` in TypeScript. That was the §6.1 gate, and it was right until a confirmed
    document date could dispute a trip — the stored row still reads EXACT/CONFIRMED because
    the conflict is derived and never written (RFC §42), so the page showed a held-back trip
    as plainly "Confirmed", on the page where the user had just attached the document.

    Asserted here rather than only in the component test because the fix is that the *API*
    decides: a client cannot re-derive what it is handed.
    """
    case_id, trip_id = _case_with_trip(api)
    _dispute_the_trip(api, db_session, case_id, trip_id)

    row = next(
        r
        for r in api("user_a").get(f"/api/v1/cases/{case_id}/travel-records").json()
        if r["id"] == trip_id
    )

    assert row["is_trusted"] is False
    assert row["is_disputed_by_document"] is True
    # The ingredients are unchanged, and must be: `date_confidence` is the value the user
    # entered, and the edit form offers it back to them. Overwriting it here would put a
    # state in that form which they never chose.
    assert row["date_confidence"] == "EXACT"
    assert row["review_state"] == "CONFIRMED"


def test_an_ordinary_confirmed_trip_is_trusted_and_not_disputed(
    api: Api, db_session: Session
) -> None:
    """The other half of the gate, so the field cannot be hardcoded false."""
    case_id, trip_id = _case_with_trip(api)

    row = next(
        r
        for r in api("user_a").get(f"/api/v1/cases/{case_id}/travel-records").json()
        if r["id"] == trip_id
    )

    assert row["is_trusted"] is True
    assert row["is_disputed_by_document"] is False


def test_adopting_the_document_dates_returns_a_trusted_record(
    api: Api, db_session: Session
) -> None:
    """The command's own response, not just the next list read.

    Every response path carries the decision because `TravelRecordOutcome.of` computes it,
    so a client acting on the command's answer sees the same thing a refetch would.
    """
    case_id, trip_id = _case_with_trip(api)
    _dispute_the_trip(api, db_session, case_id, trip_id)

    adopted = api("user_a").post(
        f"/api/v1/cases/{case_id}/travel-records/{trip_id}/adopt-document-dates", json={}
    )

    assert adopted.status_code == 200
    assert adopted.json()["is_trusted"] is True
    assert adopted.json()["is_disputed_by_document"] is False
