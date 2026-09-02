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
    validate and read it         -> evidence_processing_runs, evidence_file_texts

A table with no row proves nothing about its policy, so `assert_populated` is called
before the isolation assertions rather than trusting the arrangement.
"""

import uuid
from collections.abc import Callable, Iterator
from datetime import UTC, datetime

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
    "evidence_file_texts",
    "evidence_travel_links",
    "extraction_runs",
)

SUPPORTED_ANSWERS = {
    "date_of_birth": "1990-05-01",
    "status_type": "ILR",
    "status_granted_on": "2019-01-01",
    "married_to_british_citizen": False,
    "may_already_be_british": False,
}


@pytest.fixture
def seeded_case(api: Api, db_session: Session) -> str:
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
    item_id = _upload_document(api, user, case_id, db_session)
    _attach_document_to_a_trip(api, user, case_id, item_id)
    return case_id


def _attach_document_to_a_trip(api: Api, user: str, case_id: str, item_id: str) -> None:
    """Put one row in `evidence_travel_links`, through the real command.

    Through the route rather than by direct insert, unlike the processing rows above: the
    attach command is cheap, synchronous, and has no worker-style multi-commit shape, so
    none of the `StaleDataError` reasoning that forced direct inserts there applies here.
    """
    trips = api(user).get(f"/api/v1/cases/{case_id}/travel-records").json()
    api(user).post(
        f"/api/v1/cases/{case_id}/travel-records/{trips[0]['id']}/evidence",
        json={"evidence_item_id": item_id},
    )


def _upload_document(api: Api, user: str, case_id: str, session: Session) -> str:
    """Put one document in the case, through the real two-call upload path.

    The bytes go into the in-process store rather than MinIO — this suite is about row
    visibility, not about storage. Nothing here asserts a storage security property;
    those live in `tests/evidence/test_storage_minio.py`.
    """
    from app.core.storage import InMemoryStorage, get_storage

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
    # A *real* PDF, because the arrangement now has to reach `evidence_file_texts` and a
    # parser has to be able to open it. `b"%PDF-1.7 x"` passes the magic-byte check and
    # is not a document.
    from tests.evidence.conftest import fixture_bytes

    store.put(str(grant["upload_fields"]["key"]), fixture_bytes("travel-booking.pdf"))

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

    # The processing rows are inserted directly rather than by running the pipeline.
    #
    # This suite asks one question — is every case-scoped row invisible to another
    # tenant — and its arrangement's only job is to put one row in each table. Driving
    # the worker pipeline inline to get there meant an HTTP-created aggregate and a
    # worker-style multi-commit update sharing one engine, which the product never does:
    # in production those are different processes on different connections. It produced
    # an intermittent `StaleDataError` on `evidence_items` reported at the setup or
    # teardown of whichever test came next — a flake that says nothing about RLS.
    #
    # The pipeline is exercised properly in `tests/evidence/test_processing.py` and end
    # to end against the real worker. Here, two inserts are the honest arrangement.
    from app.ai.classifier import ClassifiedCategory
    from app.ai.domain import Capability
    from app.ai.extraction_run import ExtractionRun, ExtractionRunStatus
    from app.evidence.domain import (
        PIPELINE_VERSION,
        EvidenceFileText,
        EvidenceProcessingRun,
        ProcessingRunStatus,
    )

    file_id = session.execute(
        text("SELECT id FROM evidence_files WHERE evidence_item_id = :i"),
        {"i": uuid.UUID(item["id"])},
    ).scalar_one()

    processing_run = EvidenceProcessingRun(
        evidence_item_id=uuid.UUID(item["id"]),
        evidence_file_id=file_id,
        status=ProcessingRunStatus.SUCCEEDED.value,
        pipeline_version=PIPELINE_VERSION,
        completed_at=datetime.now(UTC),
        idempotency_key=f"seed-{item['id']}",
    )
    session.add(processing_run)
    # Flushed before the extraction run references it: `id` is assigned by the ORM's
    # default at flush, so a `SELECT` for it beforehand finds nothing.
    session.flush()
    session.add(
        EvidenceFileText(
            evidence_file_id=file_id,
            page_count=1,
            pages_read=1,
            character_count=17,
            content="synthetic content",
            pipeline_version=PIPELINE_VERSION,
        )
    )
    # The classifier's run, inserted for the same reason and with no model call: a
    # `ClassifiedCategory` on a row is what makes the table non-empty, and asking a
    # provider for one would make this suite depend on a network and a budget to answer
    # a question about row visibility.
    session.add(
        ExtractionRun.record(
            case_id=uuid.UUID(case_id),
            evidence_item_id=uuid.UUID(item["id"]),
            evidence_file_id=file_id,
            processing_run_id=processing_run.id,
            capability=Capability.DOCUMENT_CLASSIFIER.value,
            status=ExtractionRunStatus.SUCCEEDED,
            input_text="synthetic content",
            started_at=datetime.now(UTC),
            classified_category=ClassifiedCategory.TRAVEL_SUPPORT.value,
            classification_confidence=0.97,
            classification_reasoning="synthetic",
        )
    )
    session.commit()
    session.expire_all()
    return str(item["id"])


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
