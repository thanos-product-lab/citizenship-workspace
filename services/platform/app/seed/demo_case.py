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

from sqlalchemy.orm import Session

from app.applicants import service as applicants_service
from app.applicants.domain import StatusType
from app.applicants.schemas import RouteProfileDraftInput
from app.auth.schemas import CurrentUser
from app.cases import service as cases_service
from app.residence import service as residence_service
from app.residence.domain import DateConfidence, TravelRecordFields, TravelReviewState

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
    for trip in DEMO_TRIPS:
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
        )
    return case.id


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
