"""Confirm the route profile: the decision, the immutable version, and provenance.

Covers the Slice 3 acceptance: a supported user reaches an ACTIVE case; spouse-route,
unsupported-status, and under-18 users are stopped in DRAFT; may-be-British is a
review outcome; confirmation creates an immutable version; and the decision is
recorded with reproducible provenance and no answer values.
"""

from collections.abc import Callable
from datetime import date
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.applicants.domain import ReviewState, RouteProfileVersion
from app.shared.records import DomainEventRecord

pytestmark = pytest.mark.integration

Api = Callable[[str], TestClient]

# A complete, supported answer set (adult, ILR, not spouse, not may-be-British).
SUPPORTED_ANSWERS = {
    "date_of_birth": "1990-05-01",
    "status_type": "ILR",
    "status_granted_on": "2019-01-01",
    "married_to_british_citizen": False,
    "may_already_be_british": False,
}


def _case_with_draft(api: Api, user: str, answers: dict[str, object]) -> str:
    case_id = str(api(user).post("/api/v1/cases", json={"title": "My case"}).json()["id"])
    saved = api(user).put(f"/api/v1/cases/{case_id}/route-profile", json=answers)
    assert saved.status_code == 200
    return case_id


def _confirm(api: Api, user: str, case_id: str) -> tuple[int, dict[str, Any]]:
    resp = api(user).post(f"/api/v1/cases/{case_id}/route-profile/confirm", json={})
    return resp.status_code, resp.json()


def test_supported_user_reaches_an_active_case(api: Api) -> None:
    case_id = _case_with_draft(api, "user_a", SUPPORTED_ANSWERS)
    status, body = _confirm(api, "user_a", case_id)
    assert status == 200
    assert body["support_status"] == "SUPPORTED"
    assert body["conclusion"] == "SUPPORTED"
    assert body["summary_code"] == "ROUTE_STANDARD_CONFIRMED"
    assert body["lifecycle_status"] == "ACTIVE"
    # The case itself now reports ACTIVE / SUPPORTED.
    case = api("user_a").get(f"/api/v1/cases/{case_id}").json()
    assert case["lifecycle_status"] == "ACTIVE"
    assert case["support_status"] == "SUPPORTED"


def test_spouse_route_is_stopped_in_draft(api: Api) -> None:
    case_id = _case_with_draft(
        api, "user_a", {**SUPPORTED_ANSWERS, "married_to_british_citizen": True}
    )
    status, body = _confirm(api, "user_a", case_id)
    assert status == 200
    assert body["support_status"] == "UNSUPPORTED"
    assert body["summary_code"] == "ROUTE_SPOUSE_UNSUPPORTED"
    assert body["lifecycle_status"] == "DRAFT"  # never activated
    assert api("user_a").get(f"/api/v1/cases/{case_id}").json()["lifecycle_status"] == "DRAFT"


def test_unsupported_status_is_stopped(api: Api) -> None:
    case_id = _case_with_draft(
        api, "user_a", {**SUPPORTED_ANSWERS, "status_type": "OTHER", "status_granted_on": None}
    )
    _status, body = _confirm(api, "user_a", case_id)
    assert body["support_status"] == "UNSUPPORTED"
    assert body["conclusion"] == "NOT_CURRENTLY_SATISFIED"
    assert body["lifecycle_status"] == "DRAFT"


def test_may_already_be_british_is_review_needed(api: Api) -> None:
    case_id = _case_with_draft(api, "user_a", {**SUPPORTED_ANSWERS, "may_already_be_british": True})
    _status, body = _confirm(api, "user_a", case_id)
    assert body["support_status"] == "REQUIRES_REVIEW"
    assert body["conclusion"] == "REQUIRES_JUDGEMENT"
    assert body["summary_code"] == "ROUTE_MAY_BE_BRITISH"
    assert body["lifecycle_status"] == "DRAFT"


def test_under_18_is_stopped(api: Api) -> None:
    today = date.today()
    minor_dob = today.replace(year=today.year - 10).isoformat()
    case_id = _case_with_draft(api, "user_a", {**SUPPORTED_ANSWERS, "date_of_birth": minor_dob})
    _status, body = _confirm(api, "user_a", case_id)
    assert body["support_status"] == "UNSUPPORTED"
    assert body["conclusion"] == "NOT_CURRENTLY_SATISFIED"


def test_confirm_reports_each_requirement_outcome(api: Api) -> None:
    case_id = _case_with_draft(api, "user_a", SUPPORTED_ANSWERS)
    _, body = _confirm(api, "user_a", case_id)
    keys = {r["requirement_key"]: r["conclusion"] for r in body["requirements"]}
    assert keys == {
        "route.adult_applicant": "SUPPORTED",
        "route.supported_status": "SUPPORTED",
        "route.standard_section_6_1": "SUPPORTED",
    }
    assert body["rule_set"] == "2026.07.0"
    assert body["semantic_version"] == "1.0.0"


def test_incomplete_profile_cannot_be_confirmed(api: Api) -> None:
    case_id = _case_with_draft(api, "user_a", {"date_of_birth": "1990-05-01"})
    resp = api("user_a").post(f"/api/v1/cases/{case_id}/route-profile/confirm", json={})
    assert resp.status_code == 422
    missing = resp.json()["missing_fields"]
    assert "status_type" in missing
    assert "married_to_british_citizen" in missing


def test_confirming_creates_an_immutable_version_and_preserves_the_draft(
    api: Api, db_session: Session
) -> None:
    case_id = _case_with_draft(api, "user_a", SUPPORTED_ANSWERS)
    _confirm(api, "user_a", case_id)

    versions = list(db_session.scalars(select(RouteProfileVersion)))
    states = sorted(v.review_state for v in versions)
    # The draft (v1) is preserved and a new CONFIRMED (v2) was created, never mutated.
    assert states == [ReviewState.CONFIRMED.value, ReviewState.DRAFT.value]
    confirmed = next(v for v in versions if v.review_state == ReviewState.CONFIRMED.value)
    draft = next(v for v in versions if v.review_state == ReviewState.DRAFT.value)
    assert confirmed.version_number == 2
    assert confirmed.supersedes_version_id == draft.id


def test_editing_after_confirm_starts_a_new_draft(api: Api, db_session: Session) -> None:
    case_id = _case_with_draft(
        api, "user_a", {**SUPPORTED_ANSWERS, "married_to_british_citizen": True}
    )
    _confirm(api, "user_a", case_id)  # UNSUPPORTED, case stays DRAFT

    # The user corrects the answer; a confirmed version must not be edited in place.
    fixed = api("user_a").put(
        f"/api/v1/cases/{case_id}/route-profile",
        json={**SUPPORTED_ANSWERS, "married_to_british_citizen": False},
    )
    assert fixed.status_code == 200
    assert fixed.json()["review_state"] == "DRAFT"
    assert fixed.json()["version_number"] == 3  # v1 draft, v2 confirmed, v3 new draft

    _status, body = _confirm(api, "user_a", case_id)
    assert body["support_status"] == "SUPPORTED"
    assert body["lifecycle_status"] == "ACTIVE"


def test_confirm_on_an_active_case_conflicts(api: Api) -> None:
    case_id = _case_with_draft(api, "user_a", SUPPORTED_ANSWERS)
    _confirm(api, "user_a", case_id)  # → ACTIVE
    # A second confirm on the now-active case is refused.
    again = api("user_a").post(f"/api/v1/cases/{case_id}/route-profile/confirm", json={})
    assert again.status_code == 409


def test_stale_revision_on_confirm_conflicts(api: Api) -> None:
    case_id = _case_with_draft(api, "user_a", SUPPORTED_ANSWERS)
    resp = api("user_a").post(
        f"/api/v1/cases/{case_id}/route-profile/confirm", json={"expected_revision": 1}
    )
    # The draft save already bumped the profile to revision 2, so 1 is stale.
    assert resp.status_code == 409


def test_confirm_records_provenance_without_answer_values(api: Api, db_session: Session) -> None:
    case_id = _case_with_draft(api, "user_a", SUPPORTED_ANSWERS)
    _confirm(api, "user_a", case_id)

    evaluated = db_session.scalar(
        select(DomainEventRecord).where(DomainEventRecord.event_type == "RouteSupportEvaluated")
    )
    assert evaluated is not None
    payload = evaluated.payload
    assert payload["support_status"] == "SUPPORTED"
    assert payload["composite_conclusion"] == "SUPPORTED"
    assert payload["rule_set"] == "2026.07.0"
    # Self-contained provenance: the exact input version and reference date are here.
    assert payload["route_profile_version_id"]
    assert payload["reference_date"] == date.today().isoformat()
    # §38.1: no answer values (DOB, status) anywhere in the payload.
    assert "1990-05-01" not in str(payload)
    assert "ILR" not in str(payload)

    confirmed_events = db_session.scalar(
        select(func.count())
        .select_from(DomainEventRecord)
        .where(DomainEventRecord.event_type == "RouteProfileConfirmed")
    )
    assert confirmed_events == 1


def test_other_user_cannot_confirm(api: Api) -> None:
    case_id = _case_with_draft(api, "user_a", SUPPORTED_ANSWERS)
    resp = api("user_b").post(f"/api/v1/cases/{case_id}/route-profile/confirm", json={})
    assert resp.status_code == 404
