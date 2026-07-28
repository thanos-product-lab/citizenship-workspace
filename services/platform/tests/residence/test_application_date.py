"""Select a proposed application date: versioning, concurrency, the ACTIVE gate.

Covers the Slice 1 acceptance: a date can be selected and changed on an ACTIVE case;
each selection is a new immutable version (old versions never mutate); the case
pointer is authoritative and there is one current date per case; a stale revision
conflicts; a non-active case is refused with a clear domain error, not a 404; and the
value is stored as a DATE with self-contained provenance in the event.
"""

from collections.abc import Callable
from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.cases.domain import ApplicationCase
from app.residence.domain import ProposedApplicationDate, ProposedApplicationDateVersion
from app.shared.db import get_sessionmaker
from app.shared.records import DomainEventRecord, OutboxEventRecord
from app.shared.tenant import set_tenant

pytestmark = pytest.mark.integration

Api = Callable[[str], TestClient]

SUPPORTED_ANSWERS = {
    "date_of_birth": "1990-05-01",
    "status_type": "ILR",
    "status_granted_on": "2019-01-01",
    "married_to_british_citizen": False,
    "may_already_be_british": False,
}


def _draft_case(api: Api, user: str) -> str:
    return str(api(user).post("/api/v1/cases", json={"title": "My case"}).json()["id"])


def _active_case(api: Api, user: str) -> str:
    """A case driven all the way to ACTIVE through the real onboarding + confirm flow."""
    case_id = _draft_case(api, user)
    assert (
        api(user).put(f"/api/v1/cases/{case_id}/route-profile", json=SUPPORTED_ANSWERS).status_code
        == 200
    )
    confirmed = api(user).post(f"/api/v1/cases/{case_id}/route-profile/confirm", json={})
    assert confirmed.json()["lifecycle_status"] == "ACTIVE"
    return case_id


def _url(case_id: str) -> str:
    return f"/api/v1/cases/{case_id}/application-dates"


def test_get_returns_null_before_a_date_is_selected(api: Api) -> None:
    case_id = _active_case(api, "user_a")
    resp = api("user_a").get(_url(case_id))
    assert resp.status_code == 200
    assert resp.json() is None


def test_selecting_a_date_creates_the_current_version(api: Api) -> None:
    case_id = _active_case(api, "user_a")
    resp = api("user_a").post(_url(case_id) + "/select", json={"application_date": "2027-04-15"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["application_date"] == "2027-04-15"
    assert body["version_number"] == 1
    assert body["review_state"] == "CONFIRMED"
    assert body["source"] == "USER_ENTERED"
    assert body["is_current"] is True
    # Creating the root and pointing it at v1 in one commit bumps the token 1→2
    # (version_id_col), matching the M2 route-profile convention.
    assert body["revision"] == 2

    # A returning read reflects the selection.
    assert api("user_a").get(_url(case_id)).json()["application_date"] == "2027-04-15"


def test_first_selection_sets_the_authoritative_case_pointer(api: Api, db_session: Session) -> None:
    case_id = _active_case(api, "user_a")
    api("user_a").post(_url(case_id) + "/select", json={"application_date": "2027-04-15"})

    root = db_session.scalar(select(ProposedApplicationDate))
    case = db_session.get(ApplicationCase, root.case_id)
    # The case pointer (Domain §10.3 authoritative) targets the root; is_current mirrors it.
    assert case.current_proposed_application_date_id == root.id
    assert root.is_current is True


def test_changing_the_date_appends_an_immutable_version(api: Api, db_session: Session) -> None:
    case_id = _active_case(api, "user_a")
    first = (
        api("user_a")
        .post(_url(case_id) + "/select", json={"application_date": "2027-04-15"})
        .json()
    )

    changed = api("user_a").post(
        _url(case_id) + "/select",
        json={"application_date": "2027-04-25", "expected_revision": first["revision"]},
    )
    assert changed.status_code == 200
    assert changed.json()["version_number"] == 2
    assert changed.json()["application_date"] == "2027-04-25"

    versions = list(
        db_session.scalars(
            select(ProposedApplicationDateVersion).order_by(
                ProposedApplicationDateVersion.version_number
            )
        )
    )
    # Two versions; v1 is untouched, v2 supersedes it — no version ever mutated.
    assert [v.application_date for v in versions] == [date(2027, 4, 15), date(2027, 4, 25)]
    assert versions[1].supersedes_version_id == versions[0].id

    # Still exactly one root, still current, now pointing at v2.
    root = db_session.scalar(select(ProposedApplicationDate))
    assert db_session.scalar(select(func.count()).select_from(ProposedApplicationDate)) == 1
    assert root.current_version_id == versions[1].id
    assert api("user_a").get(_url(case_id)).json()["application_date"] == "2027-04-25"


def test_dates_are_stored_as_calendar_dates(api: Api, db_session: Session) -> None:
    case_id = _active_case(api, "user_a")
    api("user_a").post(_url(case_id) + "/select", json={"application_date": "2028-02-29"})
    version = db_session.scalar(select(ProposedApplicationDateVersion))
    # A DATE, not a timestamp — the M3B +1-day window depends on lossless calendar dates.
    assert isinstance(version.application_date, date)
    assert version.application_date == date(2028, 2, 29)


def test_stale_revision_conflicts_instead_of_overwriting(api: Api) -> None:
    case_id = _active_case(api, "user_a")
    first = (
        api("user_a")
        .post(_url(case_id) + "/select", json={"application_date": "2027-04-15"})
        .json()
    )

    # A valid change using the current revision moves the date on (and staleifies it).
    api("user_a").post(
        _url(case_id) + "/select",
        json={"application_date": "2027-04-20", "expected_revision": first["revision"]},
    )
    # A client still holding the now-stale revision tries to write again.
    stale = api("user_a").post(
        _url(case_id) + "/select",
        json={"application_date": "2027-05-01", "expected_revision": first["revision"]},
    )
    assert stale.status_code == 409
    # The stale write did not take effect.
    assert api("user_a").get(_url(case_id)).json()["application_date"] == "2027-04-20"


def test_selecting_on_a_non_active_case_is_a_domain_error_not_a_404(api: Api) -> None:
    # A DRAFT case (onboarding not confirmed) is real and owned but not assessable.
    case_id = _draft_case(api, "user_a")
    resp = api("user_a").post(_url(case_id) + "/select", json={"application_date": "2027-04-15"})
    assert resp.status_code == 409
    body = resp.json()
    assert body["code"] == "CASE_NOT_ACTIVE"
    assert body["lifecycle_status"] == "DRAFT"


def test_selecting_a_date_emits_one_event_and_outbox_row(api: Api, db_session: Session) -> None:
    case_id = _active_case(api, "user_a")
    api("user_a").post(_url(case_id) + "/select", json={"application_date": "2027-04-15"})

    events = list(
        db_session.scalars(
            select(DomainEventRecord).where(
                DomainEventRecord.event_type == "ProposedApplicationDateSelected"
            )
        )
    )
    assert len(events) == 1
    payload = events[0].payload
    assert payload["version_number"] == 1
    # The date is planning provenance, carried intentionally (ADR-0004).
    assert payload["application_date"] == "2027-04-15"
    assert payload["source"] == "USER_ENTERED"

    outbox = db_session.scalar(
        select(func.count())
        .select_from(OutboxEventRecord)
        .where(OutboxEventRecord.event_type == "ProposedApplicationDateSelected")
    )
    assert outbox == 1


def test_changing_the_date_emits_a_changed_event(api: Api, db_session: Session) -> None:
    case_id = _active_case(api, "user_a")
    first = (
        api("user_a")
        .post(_url(case_id) + "/select", json={"application_date": "2027-04-15"})
        .json()
    )
    api("user_a").post(
        _url(case_id) + "/select",
        json={"application_date": "2027-04-25", "expected_revision": first["revision"]},
    )
    changed = db_session.scalar(
        select(func.count())
        .select_from(DomainEventRecord)
        .where(DomainEventRecord.event_type == "ProposedApplicationDateChanged")
    )
    assert changed == 1


def test_other_user_cannot_read_or_select(api: Api) -> None:
    case_id = _active_case(api, "user_a")
    assert api("user_b").get(_url(case_id)).status_code == 404
    assert (
        api("user_b")
        .post(_url(case_id) + "/select", json={"application_date": "2027-04-15"})
        .status_code
        == 404
    )


def test_rls_hides_proposed_dates_from_another_tenant(api: Api, db_session: Session) -> None:
    case_id = _active_case(api, "user_a")
    api("user_a").post(_url(case_id) + "/select", json={"application_date": "2027-04-15"})

    other = get_sessionmaker()()
    try:
        set_tenant(other, "user_b")
        assert other.scalar(select(func.count()).select_from(ProposedApplicationDate)) == 0
        assert other.scalar(select(func.count()).select_from(ProposedApplicationDateVersion)) == 0

        set_tenant(other, "user_a")
        assert other.scalar(select(func.count()).select_from(ProposedApplicationDate)) == 1
    finally:
        other.close()
