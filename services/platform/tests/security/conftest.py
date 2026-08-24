"""Fixtures shared by the row-level-security suite.

`seeded_case` populates every case-scoped table in one arrangement, through the real
HTTP commands rather than raw inserts, so the rows have the shape the product actually
writes. Each step exists to reach a specific table:

    create case                  -> cases, case_memberships
    put + confirm route profile  -> route_profiles, route_profile_versions
    select application date      -> proposed_application_dates, ..._versions
    add travel record            -> travel_records, travel_record_versions
    recalculate                  -> assessment_runs, assessment_results,
                                    assessment_input_links
    add a second travel record   -> issues            (STALE_ASSESSMENT opens)
    recalculate again            -> issue_resolutions (the same issues resolve)
    upload a document            -> evidence_items, evidence_files
    validate it                  -> evidence_processing_runs

A table with no row proves nothing about its policy, so `assert_populated` is called
before the isolation assertions rather than trusting the arrangement.
"""

import uuid
from collections.abc import Callable, Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

Api = Callable[[str], TestClient]

# The tables whose rows belong to exactly one case, and therefore to exactly one user.
# Every one of them carries an RLS policy; this suite is what proves it.
CASE_SCOPED_TABLES: tuple[str, ...] = (
    "cases",
    "case_memberships",
    "route_profiles",
    "route_profile_versions",
    "proposed_application_dates",
    "proposed_application_date_versions",
    "travel_records",
    "travel_record_versions",
    "assessment_runs",
    "assessment_results",
    "assessment_input_links",
    "issues",
    "issue_resolutions",
    "evidence_items",
    "evidence_files",
    "evidence_processing_runs",
)

SUPPORTED_ANSWERS = {
    "date_of_birth": "1990-05-01",
    "status_type": "ILR",
    "status_granted_on": "2019-01-01",
    "married_to_british_citizen": False,
    "may_already_be_british": False,
}


@pytest.fixture
def seeded_case(api: Api) -> str:
    """A fully assessed case owned by `user_a`, with at least one row in every table in
    `CASE_SCOPED_TABLES`. Returns the case id."""
    user = "user_a"
    case_id = str(api(user).post("/api/v1/cases", json={"title": "A's case"}).json()["id"])
    api(user).put(f"/api/v1/cases/{case_id}/route-profile", json=SUPPORTED_ANSWERS)
    api(user).post(f"/api/v1/cases/{case_id}/route-profile/confirm", json={})
    api(user).post(
        f"/api/v1/cases/{case_id}/application-dates/select",
        json={"application_date": "2027-04-15"},
    )
    _add_trip(api, user, case_id, "2023-06-01", "2023-07-02")
    api(user).post(f"/api/v1/cases/{case_id}/assessments/recalculate")
    # Staling the results opens STALE_ASSESSMENT issues; recalculating resolves them,
    # which is the only path that writes an issue_resolutions row.
    _add_trip(api, user, case_id, "2024-02-01", "2024-02-20")
    api(user).post(f"/api/v1/cases/{case_id}/assessments/recalculate")
    _upload_document(api, user, case_id)
    return case_id


def _upload_document(api: Api, user: str, case_id: str) -> None:
    """Put one document in the case, through the real two-call upload path.

    The bytes go into the in-process store rather than MinIO — this suite is about row
    visibility, not about storage. Nothing here asserts a storage security property;
    those live in `tests/evidence/test_storage_minio.py`.
    """
    from app.core.storage import InMemoryStorage, get_storage
    from app.shared.db import get_sessionmaker
    from app.shared.tenant import set_tenant

    grant = (
        api(user)
        .post(
            f"/api/v1/cases/{case_id}/evidence/uploads",
            json={"media_type": "application/pdf", "declared_size_bytes": 32},
        )
        .json()
    )

    store = get_storage()
    assert isinstance(store, InMemoryStorage)
    store.put(
        str(grant["upload_url"]).removeprefix("memory://put/").split("?", 1)[0], b"%PDF-1.7 x"
    )

    item = (
        api(user)
        .post(
            f"/api/v1/cases/{case_id}/evidence",
            json={
                "upload_token": grant["upload_token"],
                "category": "TRAVEL_SUPPORT",
                "display_name": "A document",
                "original_filename": "doc.pdf",
            },
        )
        .json()
    )

    # Run validation inline rather than through the broker: this suite is about row
    # visibility, and a processing run is one of the rows. Whether Celery can reach
    # Redis is a different question, asked in `tests/evidence/`.
    from app.evidence import processing

    session = get_sessionmaker()()
    try:
        set_tenant(session, user)
        processing.validate_evidence(
            session,
            get_storage(),
            evidence_item_id=uuid.UUID(item["id"]),
            idempotency_key=f"seed-{item['id']}",
            trace_id=None,
        )
    finally:
        session.close()


def _add_trip(api: Api, user: str, case_id: str, departure: str, return_: str) -> None:
    api(user).post(
        f"/api/v1/cases/{case_id}/travel-records",
        json={
            "destination_label": "Trip",
            "departure_date": departure,
            "return_date": return_,
            "date_confidence": "EXACT",
            "review_state": "CONFIRMED",
        },
    )


def count_rows(session: Session, table: str) -> int:
    """Row count under whatever tenant context the session currently holds."""
    count: int = session.execute(text(f'SELECT count(*) FROM "{table}"')).scalar_one()
    return count


@pytest.fixture
def owner_session(db_session: Session) -> Iterator[Session]:
    """A second session on the owner connection, used to check what *actually* exists
    independently of any policy. `db_session` is left alone: it owns the TRUNCATE
    teardown and re-pointing its role would break it."""
    from app.shared.db import get_sessionmaker

    session = get_sessionmaker()()
    try:
        yield session
    finally:
        session.rollback()
        session.close()
