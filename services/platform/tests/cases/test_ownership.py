"""Case-ownership boundary over the HTTP surface (Domain §3.1).

Locks constraint (1): the absent case and the unowned case are indistinguishable —
identical status and body — so case existence never leaks across the boundary.
"""

import uuid
from collections.abc import Callable

import pytest
from fastapi.testclient import TestClient

pytestmark = pytest.mark.integration

Api = Callable[[str], TestClient]


def _create_case(api: Api, user_id: str, title: str = "My case") -> str:
    resp = api(user_id).post("/api/v1/cases", json={"title": title})
    assert resp.status_code == 201
    return str(resp.json()["id"])


def test_create_returns_draft_case(api: Api) -> None:
    resp = api("user_a").post("/api/v1/cases", json={"title": "My case"})
    assert resp.status_code == 201
    body = resp.json()
    assert body["lifecycle_status"] == "DRAFT"
    assert body["support_status"] == "NOT_EVALUATED"
    assert body["current_phase"] == "SETTING_UP"
    assert body["route_key"] == "SECTION_6_1_STANDARD"
    assert body["revision"] == 1


def test_owner_can_list_and_get_their_case(api: Api) -> None:
    case_id = _create_case(api, "user_a")

    listed = api("user_a").get("/api/v1/cases")
    assert listed.status_code == 200
    assert [c["id"] for c in listed.json()] == [case_id]

    fetched = api("user_a").get(f"/api/v1/cases/{case_id}")
    assert fetched.status_code == 200
    assert fetched.json()["id"] == case_id


def test_list_is_isolated_per_owner(api: Api) -> None:
    _create_case(api, "user_a")
    assert api("user_b").get("/api/v1/cases").json() == []


def test_absent_and_unowned_cases_are_indistinguishable(api: Api) -> None:
    owned_by_a = _create_case(api, "user_a")

    unowned = api("user_b").get(f"/api/v1/cases/{owned_by_a}")
    absent = api("user_b").get(f"/api/v1/cases/{uuid.uuid4()}")

    # The whole point: user_b cannot tell "not yours" from "does not exist".
    assert unowned.status_code == absent.status_code == 404
    assert unowned.json() == absent.json()
