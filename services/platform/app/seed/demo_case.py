"""The canonical synthetic demo case, seeded through the real
command path — the same service commands a request goes through, never raw SQL, so the
seed exercises real validation and versioning and cannot drift from product behaviour.

One fixture, one set of expected numbers (439, final-year 17, resolving 2027-04-25,
439 → 440 on the stale edit). All identities are fictional; synthetic data only.

At M3B every trip seeds as CONFIRMED + EXACT: trip 11's conflict (a competing document
value) needs the evidence model and is M4 (see the doc's M3B/M4 staging note).
"""

import time
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
from app.evidence.domain import EvidenceCategory, EvidenceProcessingStatus
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
    #: The ISO code, set here rather than left None.
    #:
    #: The web form derives it from the label; the seed and the CSV import do not, so a
    #: seeded trip and a hand-entered one for the same place used to disagree — a codeless
    #: "Greece" beside a `GR` "Greece". §7.8's duplicate detection falls back to the label
    #: for exactly that mixed pair, so the detection still fires, but a fixture whose rows
    #: differ from what the product's own form produces is a fixture that tests something
    #: other than the product.
    destination_country_code: str | None = None
    #: What the application form's "Reason for trip" column will show. Not an assessed
    #: input (ADR-0035), so no figure in the fixture depends on it.
    reason: str | None = None
    #: Whether this trip's placeholder document states the return date. Trip 11's does not:
    #: its document is an outbound ticket, so the only return date a document gives for
    #: that trip is the one the demo uploads, and the demo's conflict stays the only one.
    document_states_return: bool = True


# The twelve trips, in order. Trip 11 returns 10 May 2026 at
# M3B (EXACT); the stale demo edits it to 11 May. Raw endpoints — the rules clip and count.
DEMO_TRIPS: tuple[DemoTrip, ...] = (
    DemoTrip("Spain", date(2022, 4, 14), date(2022, 4, 26), "ES", "Holiday"),
    DemoTrip("Portugal", date(2022, 8, 10), date(2022, 9, 20), "PT", "Visiting family"),
    DemoTrip("France", date(2023, 2, 3), date(2023, 3, 1), "FR", "Work"),
    DemoTrip("United States", date(2023, 7, 1), date(2023, 9, 6), "US", "Visiting family"),
    DemoTrip("Germany", date(2024, 1, 15), date(2024, 2, 14), "DE", "Work"),
    DemoTrip("Greece", date(2024, 6, 5), date(2024, 7, 15), "GR", "Holiday"),
    DemoTrip("Japan", date(2024, 11, 2), date(2024, 12, 28), "JP", "Holiday"),
    DemoTrip("Italy", date(2025, 5, 4), date(2025, 6, 25), "IT", "Work"),
    DemoTrip("Canada", date(2025, 9, 1), date(2025, 10, 28), "CA", "Visiting friends"),
    DemoTrip("Spain", date(2026, 2, 1), date(2026, 3, 25), "ES", "Work"),
    # Trip 11, the eventual conflict.
    DemoTrip(
        "Italy", date(2026, 5, 4), date(2026, 5, 10), "IT", "Holiday", document_states_return=False
    ),
    DemoTrip("United States", date(2026, 5, 16), date(2026, 5, 29), "US", "Visiting family"),
)

# Zero-based index of trip 11 in DEMO_TRIPS, for the stale-transition demo.
TRIP_11_INDEX = 10

# Zero-based index of trip 6 (Greece), the one trip deliberately left with no document
# attached. Named because the fixture's meaning now depends on
# it: a hole in otherwise complete coverage, rather than an artefact of an empty library.
TRIP_6_INDEX = 5


def _seed_pdf(trip: "DemoTrip") -> bytes:
    """A minimal, valid, single-page PDF naming one destination.

    Built here rather than read from a fixture file so the seed has no dependency on the
    test tree and nothing binary is committed — every value in it is visible in reviewable
    source (CLAUDE.md §2.9).

    **Per trip, not per destination and not one shared constant.** The first version
    returned the same bytes for all eleven, which the slice-4b checksum detection reported
    as eleven duplicates — correctly, because they *were* the same file. Keying on the
    destination fixed most of it and left six: the demo visits Spain, Italy and the United
    States twice each, so a document naming only the country is still the same document for
    both trips. The departure date is what makes it this trip's document.

    That is also the truthful shape. A booking is for a journey, not for a country.

    Still deliberately not a *convincing* booking: no reference numbers and no traveller
    name, which would put fake-looking personal data in the repository for no gain. It
    states the destination and the dates in words, so when the worker reads it the values
    it proposes are the trip's own, and `review_seeded_documents` can confirm them.
    """
    lines = [
        "Synthetic travel document",
        f"Destination: {trip.destination_label}",
        f"Outbound: {_long_date(trip.departure_date)}",
    ]
    if trip.document_states_return:
        lines.append(f"Return: {_long_date(trip.return_date)}")
    # One text object, a line per `T*`: the page reads top to bottom like a ticket, so a
    # reader (or the worker) sees each value on its own line with its label beside it.
    body = " T* ".join(f"({line}) Tj" for line in lines)
    stream = f"BT /F1 11 Tf 14 TL 20 170 Td {body} ET\n".encode()
    return (
        b"%PDF-1.4\n"
        b"1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
        b"2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n"
        b"3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 300 200]/Contents 4 0 R"
        b"/Resources<</Font<</F1 5 0 R>>>>>>endobj\n"
        # The length is computed, not hardcoded: a literal would silently disagree with the
        # stream the moment the text changed, and a parser reads the declared length.
        b"4 0 obj<</Length "
        + str(len(stream)).encode()
        + b">>stream\n"
        + stream
        + b"endstream endobj\n"
        b"5 0 obj<</Type/Font/Subtype/Type1/BaseFont/Helvetica>>endobj\n"
        b"trailer<</Root 1 0 R>>"
    )


def _long_date(value: date) -> str:
    """The month as a word ("4 May 2026"), the only form a person cannot misread."""
    return f"{value.day} {value.strftime('%B')} {value.year}"


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
                destination_country_code=trip.destination_country_code,
                departure_date=trip.departure_date,
                return_date=trip.return_date,
                date_confidence=DateConfidence.EXACT,
                review_state=TravelReviewState.CONFIRMED,
            ),
            reason=trip.reason,
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
        content = _seed_pdf(DEMO_TRIPS[index])
        grant = evidence_service.start_upload(
            storage,
            case=case,
            media_type="application/pdf",
            declared_size_bytes=len(content),
        )
        _upload_bytes(storage, grant, content)
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


#: Every state a document stops in once the worker is done with it.
_SETTLED = frozenset(
    {
        EvidenceProcessingStatus.AWAITING_CONFIRMATION,
        EvidenceProcessingStatus.COMPLETED,
        EvidenceProcessingStatus.PARTIALLY_COMPLETED,
        EvidenceProcessingStatus.FAILED,
        EvidenceProcessingStatus.UNSUPPORTED,
    }
)


def review_seeded_documents(
    session: Session, *, case_id: uuid.UUID, user_id: str, timeout_seconds: float = 180.0
) -> int:
    """Answer every value the worker proposed from the placeholder documents, as the
    applicant would, and return how many were answered.

    **This touches the trust model, on purpose.** Each answer goes through
    `facts.service.review`, the same command the review screen posts to, so every fact it
    creates carries the same provenance a person's decision would. It stands in for an
    applicant who has already reviewed their documents, which is the case the demo puts on
    screen. It answers only from this file: a blind date is typed from the trip the
    document was written for, never copied from the proposal, and a date the document does
    not state is rejected as not present.

    Needs the worker, because only the worker proposes values. Opt-in from the command line
    (`--review-documents`) for that reason, and never called by the tests, which seed with
    no worker running.
    """
    # Registers the table a claim's foreign key points at. The API and the worker import it
    # through their routes and tasks; this command line imports neither.
    import app.ai.extraction_run  # noqa: F401
    from app.cases.repository import CaseRepository
    from app.facts import service as facts_service
    from app.facts.domain import (
        HIGH_RISK_CLAIM_TYPES,
        ClaimStatus,
        ClaimType,
        RejectionReason,
        ReviewDecision,
    )

    deadline = time.monotonic() + timeout_seconds
    while True:
        session.expire_all()
        case = CaseRepository.get(session, case_id)
        if case is None:
            raise RuntimeError(f"case {case_id} not found")
        items = [item for item, _file in evidence_service.list_evidence(session, case=case)]
        waiting = [
            item
            for item in items
            if EvidenceProcessingStatus(item.processing_status) not in _SETTLED
        ]
        session.rollback()
        if not waiting:
            break
        if time.monotonic() > deadline:
            raise TimeoutError(
                f"{len(waiting)} documents were still being read after {timeout_seconds:.0f}s."
                " Is the worker running (just up)?"
            )
        time.sleep(2)

    # Which trip each document was written for: the record it is attached to, matched back
    # to the fixture by departure date, which is unique across the twelve trips.
    fixture_by_departure = {trip.departure_date: trip for trip in DEMO_TRIPS}
    departure_by_record = {
        outcome.record.id: outcome.version.departure_date
        for outcome in residence_service.list_travel_records(session, case=case)
    }
    trip_by_item: dict[uuid.UUID, DemoTrip] = {}
    for record_id, item_ids in links.coverage_for_case(session, case_id=case.id).items():
        trip = fixture_by_departure.get(departure_by_record[record_id])
        if trip is not None:
            trip_by_item.update({item_id: trip for item_id in item_ids})

    answered = 0
    for item in items:
        trip = trip_by_item.get(item.id)
        if trip is None:
            continue
        for claim, _decision in facts_service.document_claims(
            session, case=case, evidence_item_id=item.id
        ):
            if ClaimStatus(claim.status) is not ClaimStatus.PENDING_REVIEW:
                continue
            claim_type = ClaimType(claim.claim_type)
            if claim_type in HIGH_RISK_CLAIM_TYPES:
                stated = _stated_date(trip, claim_type)
                if stated is None:
                    facts_service.review(
                        session,
                        case=case,
                        claim_id=claim.id,
                        user_id=user_id,
                        decision=ReviewDecision.REJECT,
                        reason_code=RejectionReason.VALUE_NOT_PRESENT,
                    )
                else:
                    facts_service.review(
                        session,
                        case=case,
                        claim_id=claim.id,
                        user_id=user_id,
                        entered_value=stated.isoformat(),
                    )
            else:
                facts_service.review(
                    session,
                    case=case,
                    claim_id=claim.id,
                    user_id=user_id,
                    decision=ReviewDecision.CONFIRM,
                )
            session.commit()
            answered += 1
    return answered


def _stated_date(trip: DemoTrip, claim_type: str) -> date | None:
    """The date a trip's placeholder document states for a claim type, or None."""
    if claim_type == "travel.departure_date":
        return trip.departure_date
    if claim_type == "travel.return_date" and trip.document_states_return:
        return trip.return_date
    return None


def _run() -> None:
    """`just seed [user_id]` entry point: seed the demo case into the local database.

    Defaults to the fixed `demo-user`, which is what the CLI walkthroughs (`just recalc`,
    `just inspect`) use. Pass a real signed-in user id to seed the case into an account you
    can actually open in the browser — the case is the ownership boundary, so a case owned
    by `demo-user` is correctly a 404 for anyone else.

    Requires the DB to be up and migrated (`just up` / `just migrate`). Not idempotent:
    each run creates a new case (the service commands commit per step), and a mid-seed failure
    leaves a partial case. A reset of the demo case is a distinct operation (M-later).

    The case data itself is synthetic regardless of owner (CLAUDE.md §2.9); only the owning
    account changes.
    """
    import sys

    from app.shared.db import get_sessionmaker
    from app.shared.tenant import set_tenant

    args = [arg for arg in sys.argv[1:] if not arg.startswith("--")]
    review = "--review-documents" in sys.argv[1:]
    user_id = args[0] if args else "demo-user"
    session = get_sessionmaker()()
    try:
        set_tenant(session, user_id)
        case_id = seed_demo_case(session, user_id=user_id)
        print(f"Seeded synthetic demo case {case_id} for {user_id}.")
        if review:
            print("Waiting for the worker to read the documents...")
            answered = review_seeded_documents(session, case_id=case_id, user_id=user_id)
            print(f"Answered {answered} proposed values from the seeded documents.")
    finally:
        session.close()


if __name__ == "__main__":
    _run()
