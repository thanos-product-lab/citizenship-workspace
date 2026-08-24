"""Route-profile draft capture, resume, in-place update, and concurrency.

Covers the Slice 2 acceptance: answers persist, a returning user resumes them, the
draft updates in place (no version proliferation), and a stale revision conflicts
rather than silently overwriting.
"""

from collections.abc import Callable

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.applicants.domain import RouteProfileVersion
from app.shared.records import DomainEventRecord, OutboxEventRecord

pytestmark = pytest.mark.integration

Api = Callable[[str], TestClient]


def _create_case(api: Api, user_id: str) -> str:
    resp = api(user_id).post("/api/v1/cases", json={"title": "My case"})
    assert resp.status_code == 201
    return str(resp.json()["id"])


def test_get_returns_null_before_onboarding_starts(api: Api) -> None:
    case_id = _create_case(api, "user_a")
    resp = api("user_a").get(f"/api/v1/cases/{case_id}/route-profile")
    assert resp.status_code == 200
    assert resp.json() is None


def test_saving_a_draft_persists_and_resumes(api: Api) -> None:
    case_id = _create_case(api, "user_a")

    saved = api("user_a").put(
        f"/api/v1/cases/{case_id}/route-profile",
        json={"date_of_birth": "1990-05-01", "status_type": "ILR"},
    )
    assert saved.status_code == 200
    body = saved.json()
    assert body["review_state"] == "DRAFT"
    assert body["version_number"] == 1
    assert body["revision"] == 2  # started at 1, bumped by the save

    # A returning user resumes exactly what they entered.
    resumed = api("user_a").get(f"/api/v1/cases/{case_id}/route-profile").json()
    assert resumed["date_of_birth"] == "1990-05-01"
    assert resumed["status_type"] == "ILR"
    assert resumed["married_to_british_citizen"] is None


def test_draft_updates_in_place_without_proliferation(api: Api, db_session: Session) -> None:
    case_id = _create_case(api, "user_a")
    url = f"/api/v1/cases/{case_id}/route-profile"

    r1 = api("user_a").put(url, json={"status_type": "ILR", "expected_revision": 1})
    assert r1.status_code == 200
    r2 = api("user_a").put(
        url, json={"status_type": "EU_SETTLED_STATUS", "expected_revision": r1.json()["revision"]}
    )
    assert r2.status_code == 200

    # Exactly one version row exists; the answer was overwritten in place.
    count = db_session.scalar(select(func.count()).select_from(RouteProfileVersion))
    assert count == 1
    assert api("user_a").get(f"/api/v1/cases/{case_id}/route-profile").json()["status_type"] == (
        "EU_SETTLED_STATUS"
    )


def test_stale_revision_conflicts_instead_of_overwriting(api: Api) -> None:
    case_id = _create_case(api, "user_a")
    first = api("user_a").put(f"/api/v1/cases/{case_id}/route-profile", json={"status_type": "ILR"})
    assert first.status_code == 200  # revision now 2

    # A second client still holding revision 1 tries to write.
    stale = api("user_a").put(
        f"/api/v1/cases/{case_id}/route-profile",
        json={"status_type": "OTHER", "expected_revision": 1},
    )
    assert stale.status_code == 409
    # The stale write did not take effect.
    assert api("user_a").get(f"/api/v1/cases/{case_id}/route-profile").json()["status_type"] == (
        "ILR"
    )


def test_each_save_emits_one_event_and_outbox_row(api: Api, db_session: Session) -> None:
    case_id = _create_case(api, "user_a")
    api("user_a").put(f"/api/v1/cases/{case_id}/route-profile", json={"status_type": "ILR"})

    events = list(
        db_session.scalars(
            select(DomainEventRecord).where(
                DomainEventRecord.event_type == "RouteProfileDraftSaved"
            )
        )
    )
    assert len(events) == 1
    payload = events[0].payload
    assert payload["version_number"] == 1
    assert payload["answered_fields"] == ["status_type"]
    # §38.1: the value ("ILR") never appears in the event payload.
    assert "ILR" not in str(payload)

    outbox = db_session.scalar(
        select(func.count())
        .select_from(OutboxEventRecord)
        .where(OutboxEventRecord.event_type == "RouteProfileDraftSaved")
    )
    assert outbox == 1


def test_future_date_of_birth_is_rejected(api: Api) -> None:
    case_id = _create_case(api, "user_a")
    resp = api("user_a").put(
        f"/api/v1/cases/{case_id}/route-profile", json={"date_of_birth": "3000-01-01"}
    )
    assert resp.status_code == 422


def test_other_user_cannot_read_or_write_the_draft(api: Api) -> None:
    case_id = _create_case(api, "user_a")
    api("user_a").put(f"/api/v1/cases/{case_id}/route-profile", json={"status_type": "ILR"})

    assert api("user_b").get(f"/api/v1/cases/{case_id}/route-profile").status_code == 404
    assert (
        api("user_b")
        .put(f"/api/v1/cases/{case_id}/route-profile", json={"status_type": "OTHER"})
        .status_code
        == 404
    )
