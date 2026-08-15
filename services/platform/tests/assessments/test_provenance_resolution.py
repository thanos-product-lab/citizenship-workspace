"""Resolving input links into readable inputs, against the canonical case.

The interesting assertions are not "it renders a label". They are:

- a link keeps pointing at the version the rule **actually read**, even after the record
  is edited, and the resolution says so (`is_still_current` flips);
- a record that did not pass the §6.1 trust gate is marked as not counting, so a long
  list of travel inputs cannot read as a long list of corroboration;
- an unresolvable link is kept and labelled rather than silently dropped.
"""

from collections.abc import Callable

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.assessments.domain import AssessmentInputLink
from app.assessments.provenance import resolve_input_links
from app.assessments.repository import AssessmentRepository, RequirementCatalogRepository

pytestmark = pytest.mark.integration

Api = Callable[[str], TestClient]

SUPPORTED_ANSWERS = {
    "date_of_birth": "1990-05-01",
    "status_type": "ILR",
    "status_granted_on": "2019-01-01",
    "married_to_british_citizen": False,
    "may_already_be_british": False,
}


def _assessed_case(api: Api, user: str) -> str:
    case_id = str(api(user).post("/api/v1/cases", json={"title": "My case"}).json()["id"])
    api(user).put(f"/api/v1/cases/{case_id}/route-profile", json=SUPPORTED_ANSWERS)
    api(user).post(f"/api/v1/cases/{case_id}/route-profile/confirm", json={})
    api(user).post(
        f"/api/v1/cases/{case_id}/application-dates/select",
        json={"application_date": "2027-04-15"},
    )
    api(user).post(
        f"/api/v1/cases/{case_id}/travel-records",
        json={
            "destination_label": "Italy",
            "departure_date": "2026-05-04",
            "return_date": "2026-05-10",
        },
    )
    api(user).post(f"/api/v1/cases/{case_id}/assessments/recalculate")
    return case_id


def _links_for(
    db_session: Session, case_id: str, requirement_key: str
) -> list[AssessmentInputLink]:
    import uuid as _uuid

    definition = RequirementCatalogRepository.get_definition_by_key(db_session, requirement_key)
    assert definition is not None
    result = AssessmentRepository.get_supersedable_for_requirement(
        db_session, _uuid.UUID(case_id), definition.id
    )
    assert result is not None
    return AssessmentRepository.list_input_links(db_session, result.id)


def test_a_travel_link_resolves_to_a_readable_trip(api: Api, db_session: Session) -> None:
    case_id = _assessed_case(api, "user_a")
    links = _links_for(db_session, case_id, "residence.total_absences")

    resolved = resolve_input_links(db_session, links)
    trip = next(r for r in resolved if r.input_kind == "TRAVEL_RECORD_VERSION")

    assert trip.label == "Trip to Italy"
    assert trip.value == "4 May 2026 to 10 May 2026"
    assert trip.detail == "Confirmed · exact dates"
    assert trip.counts_as_confirmed is True
    assert trip.is_still_current is True
    assert trip.provenance_kind == "user_confirmed"


def test_the_application_date_resolves_and_the_trust_gate_does_not_apply(
    api: Api, db_session: Session
) -> None:
    case_id = _assessed_case(api, "user_a")
    links = _links_for(db_session, case_id, "residence.total_absences")

    date_input = next(
        r
        for r in resolve_input_links(db_session, links)
        if r.input_kind == "APPLICATION_DATE_VERSION"
    )
    assert date_input.label == "Proposed application date"
    assert date_input.value == "15 April 2027"
    # The §6.1 gate is about travel records. Reporting the date as "confirmed" or
    # "not confirmed" would invent a distinction the domain does not make here.
    assert date_input.counts_as_confirmed is None


def test_a_profile_link_resolves_to_the_exact_field_the_rule_read(
    api: Api, db_session: Session
) -> None:
    case_id = _assessed_case(api, "user_a")
    links = _links_for(db_session, case_id, "route.adult_applicant")

    resolved = resolve_input_links(db_session, links)
    dob = next(r for r in resolved if r.input_key == "date_of_birth")
    assert dob.label == "Date of birth"
    assert dob.value == "1 May 1990"


def test_editing_a_trip_flips_is_still_current_on_the_old_result(
    api: Api, db_session: Session
) -> None:
    """The heart of it. The result keeps pointing at the version it read; the record now
    has a newer one. That difference is what lets the screen name the input that moved,
    rather than only saying the result is stale."""
    case_id = _assessed_case(api, "user_a")
    before = resolve_input_links(
        db_session, _links_for(db_session, case_id, "residence.total_absences")
    )
    assert all(r.is_still_current for r in before)

    records = api("user_a").get(f"/api/v1/cases/{case_id}/travel-records").json()
    record = records[0]
    api("user_a").patch(
        f"/api/v1/cases/{case_id}/travel-records/{record['id']}",
        json={
            "destination_label": "Italy",
            "departure_date": "2026-05-04",
            "return_date": "2026-05-11",
            "expected_revision": record["revision"],
        },
    )
    db_session.expire_all()

    after = resolve_input_links(
        db_session, _links_for(db_session, case_id, "residence.total_absences")
    )
    trip = next(r for r in after if r.input_kind == "TRAVEL_RECORD_VERSION")
    assert trip.is_still_current is False
    # The value shown is still the one the rule read, not the edited one — the result was
    # reached from these inputs, and rewriting them would falsify the provenance.
    assert trip.value == "4 May 2026 to 10 May 2026"

    # The application date did not move, so it must not be implicated.
    date_input = next(r for r in after if r.input_kind == "APPLICATION_DATE_VERSION")
    assert date_input.is_still_current is True


def test_an_unconfirmed_trip_is_marked_as_not_counting(api: Api, db_session: Session) -> None:
    """A trip that fails the §6.1 gate is still an input the rule read — it shapes the
    provisional figure — but it did not contribute to the trusted one, and the list has to
    say so or twelve rows read as twelve pieces of corroboration."""
    case_id = _assessed_case(api, "user_a")
    api("user_a").post(
        f"/api/v1/cases/{case_id}/travel-records",
        json={
            "destination_label": "Greece",
            "departure_date": "2026-07-01",
            "return_date": "2026-07-20",
            "date_confidence": "ESTIMATED",
        },
    )
    api("user_a").post(f"/api/v1/cases/{case_id}/assessments/recalculate")

    resolved = resolve_input_links(
        db_session, _links_for(db_session, case_id, "residence.total_absences")
    )
    greece = next(r for r in resolved if r.label == "Trip to Greece")
    assert greece.counts_as_confirmed is False
    assert greece.detail == "Confirmed · estimated dates"
    assert greece.provenance_kind != "user_confirmed"

    italy = next(r for r in resolved if r.label == "Trip to Italy")
    assert italy.counts_as_confirmed is True


def test_an_unresolvable_link_is_kept_and_labelled_not_dropped(
    api: Api, db_session: Session
) -> None:
    """A provenance list that silently omits an input it cannot explain is worse than one
    that admits the gap: the reader would count the rows and conclude fewer inputs were
    read than actually were."""
    import uuid

    orphan = AssessmentInputLink(
        assessment_result_id=uuid.uuid4(),
        input_kind="TRAVEL_RECORD_VERSION",
        input_version_id=uuid.uuid4(),
        input_key=None,
        contribution_role="CONTEXTUAL",
    )
    resolved = resolve_input_links(db_session, [orphan])
    assert len(resolved) == 1
    assert resolved[0].unavailable is True
    assert resolved[0].value == "No longer available"
    assert resolved[0].provenance_kind == "unavailable"


def test_resolution_preserves_link_order(api: Api, db_session: Session) -> None:
    case_id = _assessed_case(api, "user_a")
    links = _links_for(db_session, case_id, "residence.total_absences")
    resolved = resolve_input_links(db_session, links)
    assert [r.input_version_id for r in resolved] == [link.input_version_id for link in links]


def test_a_removed_record_is_marked_removed_and_stops_counting(
    api: Api, db_session: Session
) -> None:
    """Removal is a tombstone: the record keeps pointing at its last version, so
    `is_still_current` stays true and only the lifecycle reveals the deletion.

    Before the §6.1 gate was shared, the display path checked CONFIRMED + EXACT but not
    ACTIVE, so a deleted trip rendered as current, confirmed, and counting towards the
    figure — the failure CLAUDE.md §9 names directly ("deleting evidence cannot leave its
    support state as available")."""
    case_id = _assessed_case(api, "user_a")
    records = api("user_a").get(f"/api/v1/cases/{case_id}/travel-records").json()
    record = records[0]

    removed = api("user_a").delete(
        f"/api/v1/cases/{case_id}/travel-records/{record['id']}",
        params={"expected_revision": record["revision"]},
    )
    assert removed.status_code == 200, removed.text
    db_session.expire_all()

    resolved = resolve_input_links(
        db_session, _links_for(db_session, case_id, "residence.total_absences")
    )
    trip = next(r for r in resolved if r.input_kind == "TRAVEL_RECORD_VERSION")

    assert trip.is_removed is True
    assert trip.counts_as_confirmed is False
    # The value shown is still what the rule read — the result was reached from it.
    assert trip.value == "4 May 2026 to 10 May 2026"


def test_the_trust_gate_has_one_definition(api: Api, db_session: Session) -> None:
    """The assessment service and the provenance resolver must agree on which records count.
    Two copies of the §6.1 rule is how the removed-record bug happened, so this pins that
    the displayed `counts_as_confirmed` matches the gate the evaluator actually applied."""
    from app.residence.domain import counts_toward_trusted_total
    from app.residence.repository import TravelRecordRepository

    case_id = _assessed_case(api, "user_a")
    api("user_a").post(
        f"/api/v1/cases/{case_id}/travel-records",
        json={
            "destination_label": "Greece",
            "departure_date": "2026-07-01",
            "return_date": "2026-07-20",
            "date_confidence": "ESTIMATED",
        },
    )
    api("user_a").post(f"/api/v1/cases/{case_id}/assessments/recalculate")

    resolved = resolve_input_links(
        db_session, _links_for(db_session, case_id, "residence.total_absences")
    )
    for item in (r for r in resolved if r.input_kind == "TRAVEL_RECORD_VERSION"):
        found = TravelRecordRepository.get_record_for_version(db_session, item.input_version_id)
        assert found is not None
        record, version = found
        assert item.counts_as_confirmed == counts_toward_trusted_total(record, version)
