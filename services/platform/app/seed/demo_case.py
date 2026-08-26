"""The canonical synthetic demo case (SYNTHETIC_DEMO_CASE.md), seeded through the real
command path — the same service commands a request goes through, never raw SQL, so the
seed exercises real validation and versioning and cannot drift from product behaviour.

One fixture, one set of expected numbers (439, final-year 17, resolving 2027-04-25,
439 → 440 on the stale edit). All identities are fictional; synthetic data only.

At M3B every trip seeds as CONFIRMED + EXACT: trip 11's conflict (a competing document
value) needs the evidence model and is M4 (see the doc's M3B/M4 staging note).
"""

import uuid
from dataclasses import dataclass
from datetime import date

import httpx
from sqlalchemy.orm import Session

from app.applicants import service as applicants_service
from app.applicants.domain import StatusType
from app.applicants.schemas import RouteProfileDraftInput
from app.auth.schemas import CurrentUser
from app.cases import service as cases_service
from app.cases.domain import ApplicationCase
from app.core.storage import InMemoryStorage, StorageAdapter, get_storage
from app.evidence import links
from app.evidence import service as evidence_service
from app.evidence.domain import EvidenceCategory
from app.evidence.service import UploadGrant
from app.residence import service as residence_service
from app.residence.domain import (
    DateConfidence,
    TravelRecord,
    TravelRecordFields,
    TravelReviewState,
)

DEMO_CASE_TITLE = "Amara Okonkwo — demo"
DEMO_APPLICATION_DATE = date(2027, 4, 15)

DEMO_ROUTE_ANSWERS = RouteProfileDraftInput(
    date_of_birth=date(1988, 3, 14),
    status_type=StatusType.EU_SETTLED_STATUS,
    status_granted_on=date(2025, 3, 1),
    married_to_british_citizen=False,
    may_already_be_british=False,
)


@dataclass(frozen=True)
class DemoTrip:
    destination_label: str
    departure_date: date
    return_date: date


# The twelve trips (SYNTHETIC_DEMO_CASE.md §4), in order. Trip 11 returns 10 May 2026 at
# M3B (EXACT); the stale demo edits it to 11 May. Raw endpoints — the rules clip and count.
DEMO_TRIPS: tuple[DemoTrip, ...] = (
    DemoTrip("Spain", date(2022, 4, 14), date(2022, 4, 26)),
    DemoTrip("Portugal", date(2022, 8, 10), date(2022, 9, 20)),
    DemoTrip("France", date(2023, 2, 3), date(2023, 3, 1)),
    DemoTrip("United States", date(2023, 7, 1), date(2023, 9, 6)),
    DemoTrip("Germany", date(2024, 1, 15), date(2024, 2, 14)),
    DemoTrip("Greece", date(2024, 6, 5), date(2024, 7, 15)),
    DemoTrip("Japan", date(2024, 11, 2), date(2024, 12, 28)),
    DemoTrip("Italy", date(2025, 5, 4), date(2025, 6, 25)),
    DemoTrip("Canada", date(2025, 9, 1), date(2025, 10, 28)),
    DemoTrip("Spain", date(2026, 2, 1), date(2026, 3, 25)),
    DemoTrip("Italy", date(2026, 5, 4), date(2026, 5, 10)),  # trip 11 — the eventual conflict
    DemoTrip("United States", date(2026, 5, 16), date(2026, 5, 29)),
)

# Zero-based index of trip 11 in DEMO_TRIPS, for the stale-transition demo.
TRIP_11_INDEX = 10

# Zero-based index of trip 6 (Greece), the one trip deliberately left with no document
# attached (SYNTHETIC_DEMO_CASE §10). Named because the fixture's meaning now depends on
# it: a hole in otherwise complete coverage, rather than an artefact of an empty library.
TRIP_6_INDEX = 5

#: A minimal, valid, single-page PDF. Generated here rather than read from a fixture file
#: so the seed has no dependency on the test tree and nothing binary is committed
#: (CLAUDE.md §2.9 — every value in it is visible in reviewable source).
#:
#: Deliberately not a *convincing* booking. The seed's job is to make coverage real — a
#: document exists and is attached — and nothing in M7 reads it. Inventing plausible
#: reference numbers here would put fake-looking personal data in the repository for no
#: gain.
_SEED_PDF = (
    b"%PDF-1.4\n"
    b"1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
    b"2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n"
    b"3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 200 200]/Contents 4 0 R"
    b"/Resources<</Font<</F1 5 0 R>>>>>>endobj\n"
    b"4 0 obj<</Length 52>>stream\n"
    b"BT /F1 12 Tf 20 100 Td (Synthetic travel document) Tj ET\n"
    b"endstream endobj\n"
    b"5 0 obj<</Type/Font/Subtype/Type1/BaseFont/Helvetica>>endobj\n"
    b"trailer<</Root 1 0 R>>"
)


def seed_demo_case(session: Session, *, user_id: str) -> uuid.UUID:
    """Create the canonical case and return its id: confirm the supported route, select the
    application date, and add the twelve trusted trips — all via the real service commands.
    The caller owns the RLS tenant context (`set_tenant`) for `user_id`."""
    user = CurrentUser(user_id=user_id, session_id="seed", email=None)

    case = cases_service.create_case(session, user=user, title=DEMO_CASE_TITLE)
    applicants_service.save_draft(session, case=case, user=user, answers=DEMO_ROUTE_ANSWERS)
    outcome = applicants_service.confirm_route_profile(
        session, case=case, user=user, expected_revision=None
    )
    case = outcome.case  # now ACTIVE

    residence_service.select_application_date(
        session,
        case=case,
        user=user,
        application_date=DEMO_APPLICATION_DATE,
        expected_revision=None,
    )
    records = [
        residence_service.add_travel_record(
            session,
            case=case,
            user=user,
            fields=TravelRecordFields(
                destination_label=trip.destination_label,
                departure_date=trip.departure_date,
                return_date=trip.return_date,
                date_confidence=DateConfidence.EXACT,
                review_state=TravelReviewState.CONFIRMED,
            ),
        ).record
        for trip in DEMO_TRIPS
    ]
    _attach_travel_documents(session, case=case, user=user, records=records)
    return case.id


def _upload_bytes(storage: StorageAdapter, grant: UploadGrant, content: bytes) -> None:
    """Put the bytes where the grant says, as a client would.

    Against a real store that means POSTing to the presigned URL — the same request a
    browser makes, so `just seed` exercises the actual upload path against MinIO rather
    than a shortcut around it. The alternative was adding `put` to `StorageAdapter`, which
    would have given the API process a direct server-side write path to the bucket and
    invited someone to route real uploads through it later. The architecture says bytes go
    client-to-store and never through the web process (ADR-0018), and a protocol method
    exists to be used.

    The in-memory fake has no HTTP endpoint — its "URL" is `memory://` — so it gets the
    direct path. Narrowed by type, so this branch cannot silently take over for a real
    store whose presign happened to fail.
    """
    if isinstance(storage, InMemoryStorage):
        storage.put(str(grant.upload_fields["key"]), content)
        return
    # Every signed field, then the file last — exactly what the browser client does
    # (`useUploadEvidence.ts`). A presigned POST policy signs the field set, so dropping
    # one (`Content-Type` looked redundant beside the file's own type) makes the store
    # reject the whole request with a bare 403 that names nothing.
    response = httpx.post(
        grant.upload_url,
        data=dict(grant.upload_fields),
        files={"file": (str(grant.upload_fields["key"]), content, grant.media_type)},
        timeout=30.0,
    )
    response.raise_for_status()


def _attach_travel_documents(
    session: Session,
    *,
    case: ApplicationCase,
    user: CurrentUser,
    records: list[TravelRecord],
) -> None:
    """Give every trip but Greece a document, so the case shows one `MISSING_EVIDENCE`.

    Through the real upload and attach commands, not by inserting rows. The seed is what
    the demo is driven from, and a seed that wrote link rows directly could produce a
    state the product cannot actually reach — which is the one thing a demo fixture must
    never do.

    Works without MinIO. `get_storage()` returns whatever the settings configure, which is
    `InMemoryStorage` under the default test settings, so
    `tests/assessments/test_canonical_case.py` still needs only Postgres.

    The documents stay in `UPLOADED`: no worker runs here, so nothing reads them. That is
    the honest state and it is enough — attaching does not require a document to have been
    read, because a link is the user's assertion rather than a machine's verdict
    (ADR-0021).
    """
    storage = get_storage()
    for index, record in enumerate(records):
        if index == TRIP_6_INDEX:
            continue
        grant = evidence_service.start_upload(
            storage,
            case=case,
            media_type="application/pdf",
            declared_size_bytes=len(_SEED_PDF),
        )
        _upload_bytes(storage, grant, _SEED_PDF)
        item, _file = evidence_service.record_upload(
            session,
            storage,
            case=case,
            user=user,
            token=grant.upload_token,
            category=EvidenceCategory.TRAVEL_SUPPORT,
            display_name=f"{DEMO_TRIPS[index].destination_label} travel document",
            original_filename=f"{DEMO_TRIPS[index].destination_label.lower()}-travel.pdf",
        )
        links.attach_to_travel_record(
            session,
            case=case,
            user=user,
            travel_record_id=record.id,
            evidence_item_id=item.id,
        )


def _run() -> None:
    """`just seed [user_id]` entry point: seed the demo case into the local database.

    Defaults to the fixed `demo-user`, which is what the CLI walkthroughs (`just recalc`,
    `just inspect`) use. Pass a real signed-in user id to seed the case into an account you
    can actually open in the browser — the case is the ownership boundary, so a case owned
    by `demo-user` is correctly a 404 for anyone else.

    Requires the DB to be up and migrated (`just up` / `just migrate`). Not idempotent:
    each run creates a new case (the service commands commit per step), and a mid-seed failure
    leaves a partial case — a `SYNTHETIC_DEMO_CASE` reset is a distinct operation (M-later).

    The case data itself is synthetic regardless of owner (CLAUDE.md §2.9); only the owning
    account changes.
    """
    import sys

    from app.shared.db import get_sessionmaker
    from app.shared.tenant import set_tenant

    user_id = sys.argv[1] if len(sys.argv) > 1 else "demo-user"
    session = get_sessionmaker()()
    try:
        set_tenant(session, user_id)
        case_id = seed_demo_case(session, user_id=user_id)
        print(f"Seeded synthetic demo case {case_id} for {user_id}.")
    finally:
        session.close()


if __name__ == "__main__":
    _run()
