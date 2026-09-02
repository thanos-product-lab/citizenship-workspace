"""CSV travel-history import: dry-run validation, atomic commit, per-row diagnostics.

Covers the Slice 3 acceptance (MVP §8.4): import errors identify the exact affected
rows; a user can correct before committing; the commit is all-or-nothing (one bad row
writes nothing); imported rows become CSV_IMPORT versions; and the write is gated on an
ACTIVE case and the case owner.
"""

from collections.abc import Callable
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.residence.domain import TravelRecord, TravelRecordVersion
from app.shared.records import DomainEventRecord
from tests.conftest import ApiResponse

pytestmark = pytest.mark.integration

Api = Callable[[str], TestClient]

SUPPORTED_ANSWERS = {
    "date_of_birth": "1990-05-01",
    "status_type": "ILR",
    "status_granted_on": "2019-01-01",
    "married_to_british_citizen": False,
    "may_already_be_british": False,
}

HEADER = ",".join(
    (
        "destination_label",
        "destination_country_code",
        "departure_date",
        "return_date",
        "date_confidence",
        "review_state",
        "notes",
    )
)


def _row(
    label: str = "Spain",
    code: str = "ES",
    dep: str = "2022-04-14",
    ret: str = "2022-04-26",
    conf: str = "EXACT",
    review: str = "CONFIRMED",
    notes: str = "",
) -> str:
    return f"{label},{code},{dep},{ret},{conf},{review},{notes}"


def _csv(*rows: str, header: str = HEADER) -> str:
    return "\n".join([header, *rows]) + "\n"


def _active_case(api: Api, user: str) -> str:
    case_id = str(api(user).post("/api/v1/cases", json={"title": "My case"}).json()["id"])
    assert (
        api(user).put(f"/api/v1/cases/{case_id}/route-profile", json=SUPPORTED_ANSWERS).status_code
        == 200
    )
    assert (
        api(user)
        .post(f"/api/v1/cases/{case_id}/route-profile/confirm", json={})
        .json()["lifecycle_status"]
        == "ACTIVE"
    )
    return case_id


def _url(case_id: str) -> str:
    return f"/api/v1/cases/{case_id}/travel-records"


def _validate(api: Api, user: str, case_id: str, content: str) -> dict[str, Any]:
    result: dict[str, Any] = (
        api(user).post(f"{_url(case_id)}/import/validate", json={"content": content}).json()
    )
    return result


def _commit(api: Api, user: str, case_id: str, content: str) -> ApiResponse:
    resp: ApiResponse = api(user).post(f"{_url(case_id)}/import", json={"content": content})
    return resp


def test_validate_flags_the_exact_bad_row_and_previews_the_good_one(api: Api) -> None:
    case_id = _active_case(api, "user_a")
    content = _csv(_row(label="Spain"), _row(label="Italy", dep="14/04/2022"))  # row 3 bad date
    body = _validate(api, "user_a", case_id, content)

    assert (body["total"], body["valid_count"], body["error_count"], body["all_valid"]) == (
        2,
        1,
        1,
        False,
    )
    good, bad = body["rows"]
    assert good["row_number"] == 2 and good["valid"] is True
    assert good["value"]["destination_label"] == "Spain"  # normalised preview
    assert bad["row_number"] == 3 and bad["valid"] is False
    assert bad["errors"][0]["field"] == "departure_date"
    assert bad["errors"][0]["code"] == "DATE_INVALID_FORMAT"


def test_validate_writes_nothing(api: Api, db_session: Session) -> None:
    case_id = _active_case(api, "user_a")
    _validate(api, "user_a", case_id, _csv(_row()))
    assert db_session.scalar(select(func.count()).select_from(TravelRecord)) == 0


def test_commit_imports_every_row_as_a_csv_version(api: Api) -> None:
    case_id = _active_case(api, "user_a")
    content = _csv(
        _row(label="Spain", dep="2022-04-14", ret="2022-04-26"),
        _row(label="Italy", code="it", dep="2023-05-01", ret="2023-05-10"),
    )
    resp = _commit(api, "user_a", case_id, content)
    assert resp.status_code == 201
    body = resp.json()
    assert body["imported_count"] == 2
    assert {r["entry_source"] for r in body["records"]} == {"CSV_IMPORT"}
    assert all(r["version_number"] == 1 for r in body["records"])

    listed = api("user_a").get(_url(case_id)).json()
    assert [r["destination_label"] for r in listed] == ["Spain", "Italy"]  # chronological
    assert (
        next(r for r in listed if r["destination_label"] == "Italy")["destination_country_code"]
        == "IT"
    )


def test_commit_is_atomic_and_reports_the_bad_row(api: Api, db_session: Session) -> None:
    case_id = _active_case(api, "user_a")
    content = _csv(_row(label="Spain"), _row(label="Italy", dep="2023-05-10", ret="2023-05-01"))
    resp = _commit(api, "user_a", case_id, content)

    assert resp.status_code == 422
    body = resp.json()
    assert body["code"] == "CSV_IMPORT_INVALID"
    bad = next(r for r in body["rows"] if not r["valid"])
    assert bad["row_number"] == 3
    assert bad["errors"][0]["code"] == "DATE_ORDER_INVALID"
    # All-or-nothing: not even the valid row was written.
    assert db_session.scalar(select(func.count()).select_from(TravelRecord)) == 0
    assert api("user_a").get(_url(case_id)).json() == []


def test_correct_then_commit_succeeds(api: Api) -> None:
    case_id = _active_case(api, "user_a")
    bad = _csv(_row(dep="2022-04-30", ret="2022-04-01"))  # departure after return
    assert _commit(api, "user_a", case_id, bad).status_code == 422
    fixed = _csv(_row(dep="2022-04-01", ret="2022-04-30"))
    assert _commit(api, "user_a", case_id, fixed).status_code == 201


def test_missing_required_column_is_malformed(api: Api) -> None:
    case_id = _active_case(api, "user_a")
    header = "destination_label,return_date,date_confidence"  # no departure_date
    resp = _commit(api, "user_a", case_id, _csv("Spain,2022-04-26,EXACT", header=header))
    assert resp.status_code == 422
    assert resp.json()["code"] == "CSV_IMPORT_MALFORMED"


def test_header_only_file_is_malformed(api: Api) -> None:
    case_id = _active_case(api, "user_a")
    resp = api("user_a").post(f"{_url(case_id)}/import", json={"content": HEADER + "\n"})
    assert resp.status_code == 422
    assert resp.json()["code"] == "CSV_IMPORT_MALFORMED"


def test_blank_required_cell_is_a_row_error(api: Api) -> None:
    case_id = _active_case(api, "user_a")
    body = _validate(api, "user_a", case_id, _csv(_row(conf="")))  # empty date_confidence
    assert body["rows"][0]["errors"][0]["code"] == "DATE_CONFIDENCE_INVALID"


def test_blank_review_state_defaults_to_confirmed(api: Api) -> None:
    case_id = _active_case(api, "user_a")
    resp = _commit(api, "user_a", case_id, _csv(_row(review="")))
    assert resp.status_code == 201
    assert resp.json()["records"][0]["review_state"] == "CONFIRMED"


def test_over_long_destination_is_a_row_error_not_a_500(api: Api) -> None:
    case_id = _active_case(api, "user_a")
    long_label = "X" * 121  # one over the varchar(120) boundary
    # The dry-run must flag it (agreeing with the commit)...
    body = _validate(api, "user_a", case_id, _csv(_row(label=long_label)))
    assert body["rows"][0]["errors"][0]["code"] == "DESTINATION_TOO_LONG"
    # ...and the commit returns a clean 422, never a 500 at the DB boundary.
    assert _commit(api, "user_a", case_id, _csv(_row(label=long_label))).status_code == 422


def test_too_many_rows_is_malformed(api: Api) -> None:
    from app.residence.csv_import import MAX_IMPORT_ROWS

    case_id = _active_case(api, "user_a")
    content = _csv(*[_row() for _ in range(MAX_IMPORT_ROWS + 1)])
    resp = _commit(api, "user_a", case_id, content)
    assert resp.status_code == 422
    assert resp.json()["code"] == "CSV_IMPORT_MALFORMED"


def test_import_on_a_non_active_case_is_a_domain_error_not_a_404(api: Api) -> None:
    case_id = str(api("user_a").post("/api/v1/cases", json={"title": "Draft"}).json()["id"])
    resp = _commit(api, "user_a", case_id, _csv(_row()))
    assert resp.status_code == 409
    assert resp.json()["code"] == "CASE_NOT_ACTIVE"


def test_other_user_cannot_validate_or_import(api: Api) -> None:
    case_id = _active_case(api, "user_a")
    assert (
        api("user_b")
        .post(f"{_url(case_id)}/import/validate", json={"content": _csv(_row())})
        .status_code
        == 404
    )
    assert _commit(api, "user_b", case_id, _csv(_row())).status_code == 404


def test_commit_emits_one_import_event_per_record(api: Api, db_session: Session) -> None:
    case_id = _active_case(api, "user_a")
    _commit(api, "user_a", case_id, _csv(_row(label="Spain"), _row(label="Italy")))

    events = list(
        db_session.scalars(
            select(DomainEventRecord).where(DomainEventRecord.event_type == "TravelRecordCreated")
        )
    )
    assert len(events) == 2
    assert all(e.payload["entry_source"] == "CSV_IMPORT" for e in events)
    # Two records, two versions — one v1 each.
    assert db_session.scalar(select(func.count()).select_from(TravelRecordVersion)) == 2
