"""How many cases one user may hold.

The last rung of the ladder that bounds AI spend. `ai_case_daily_call_limit` bounds one
case, `ai_user_daily_call_limit` bounds one user — and neither bounds how many cases a
user *opens*, which is storage, processing, and rows in every case-scoped table as well
as a way around anything counted per case.
"""

import pytest
from sqlalchemy.orm import Session

from app.cases.repository import CaseRepository
from app.core.config import Settings, get_settings
from app.main import app
from tests.conftest import Api, ApiResponse

pytestmark = pytest.mark.integration


def _limit_of(count: int) -> Settings:
    return Settings(environment="test", ai_provider="fake", max_cases_per_user=count)


def _create(api: Api, user: str, title: str = "A case") -> ApiResponse:
    return api(user).post("/api/v1/cases", json={"title": title})


@pytest.fixture(autouse=True)
def _restore() -> object:
    yield
    app.dependency_overrides.pop(get_settings, None)
    get_settings.cache_clear()


def test_a_user_can_open_cases_up_to_the_limit(api: Api, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.cases.service.get_settings", lambda: _limit_of(3))

    for index in range(3):
        assert _create(api, "user_a", f"Case {index}").status_code == 201


def test_the_case_after_the_limit_is_refused_with_the_numbers(
    api: Api, monkeypatch: pytest.MonkeyPatch
) -> None:
    """409, matching `CaseNotActive`: the request is well-formed and the caller's account
    state is what refuses it. The body carries both numbers so a client can say "3 of 3"
    without keeping a copy of the server's limit in step with it."""
    monkeypatch.setattr("app.cases.service.get_settings", lambda: _limit_of(3))
    for index in range(3):
        _create(api, "user_a", f"Case {index}")

    response = _create(api, "user_a", "One too many")

    assert response.status_code == 409
    body = response.json()
    assert body["code"] == "TOO_MANY_CASES"
    assert body["held"] == 3
    assert body["limit"] == 3
    # The sentence has to say what to do. "Too many cases" alone leaves someone stuck
    # with no idea that deleting one is the way out.
    assert "Delete a case" in body["detail"]


def test_one_users_cases_do_not_count_against_another(
    api: Api, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A shared counter would let one busy account lock everyone else out of creating a
    case at all — which is the failure this limit exists to prevent, not to cause."""
    monkeypatch.setattr("app.cases.service.get_settings", lambda: _limit_of(2))
    for index in range(2):
        _create(api, "user_a", f"A's case {index}")

    assert _create(api, "user_a", "A's third").status_code == 409
    assert _create(api, "user_b", "B's first").status_code == 201


def test_deleting_a_case_makes_room_for_another(api: Api, monkeypatch: pytest.MonkeyPatch) -> None:
    """The remedy the error message promises. A limit whose only escape is support is a
    dead end, and the sentence would be a lie."""
    monkeypatch.setattr("app.cases.service.get_settings", lambda: _limit_of(2))
    first = _create(api, "user_a", "Keep").json()
    _create(api, "user_a", "Discard")
    assert _create(api, "user_a", "Blocked").status_code == 409

    api("user_a").delete(f"/api/v1/cases/{first['id']}")

    assert _create(api, "user_a", "Now allowed").status_code == 201


def test_a_case_being_deleted_stops_counting_before_the_purge_finishes(
    api: Api, db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The count and the listing deliberately disagree for one state, and this is it.

    Deleting sets `DELETION_PENDING`; the purge worker sets `DELETED` afterwards. The
    listing still shows the case — a deletion in progress is a thing that is happening
    and the user should see it — but it stops counting immediately, because the slot
    exists to bound storage and processing that the case is already releasing, and the
    user can neither use it nor hurry it along.

    The first version matched the listing exactly, on the tidier-sounding reasoning that
    a limit should be checkable against what is on screen. It made the refusal message
    ("delete a case to open another") false until a background worker ran.
    """
    monkeypatch.setattr("app.cases.service.get_settings", lambda: _limit_of(5))
    kept = _create(api, "user_a", "Kept").json()
    _create(api, "user_a", "Given up")

    api("user_a").delete(f"/api/v1/cases/{kept['id']}")

    listed = api("user_a").get("/api/v1/cases").json()
    assert len(listed) == 2, "a case mid-deletion should still be visible"
    assert CaseRepository.count_for_owner(db_session, "user_a") == 1


def test_the_default_limit_is_far_above_ordinary_use() -> None:
    """A limit people meet by working normally is a workflow constraint wearing a safety
    label. A case is one intended application, and comparing two application dates is
    what the date simulator is for — so the number a real person needs is one or two."""
    assert Settings().max_cases_per_user >= 10
