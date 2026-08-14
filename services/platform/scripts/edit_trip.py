"""Edit the return date of the active travel record with a given departure date, through the
real residence command — which fires the same-transaction blunt stale invalidation. Use it to
drive the M3B stale demo (edit trip 11's return 10 May → 11 May), then re-run `just recalc`.

    just edit-trip <case_id> <departure_date> <new_return_date> [user_id]

Dates are ISO (YYYY-MM-DD). The other trip fields are preserved.
"""

import sys
import uuid
from datetime import date

from sqlalchemy import select

from app.auth.schemas import CurrentUser
from app.cases.domain import ApplicationCase
from app.residence import service as residence_service
from app.residence.domain import DateConfidence, TravelRecordFields, TravelReviewState
from app.residence.repository import TravelRecordRepository
from app.shared.db import get_sessionmaker
from app.shared.tenant import set_tenant


def main() -> None:
    if len(sys.argv) < 4:
        print(
            "usage: python -m scripts.edit_trip <case_id> <departure> <new_return> [user_id]",
            file=sys.stderr,
        )
        raise SystemExit(2)
    case_id = uuid.UUID(sys.argv[1])
    departure = date.fromisoformat(sys.argv[2])
    new_return = date.fromisoformat(sys.argv[3])
    user_id = sys.argv[4] if len(sys.argv) > 4 else "demo-user"

    session = get_sessionmaker()()
    try:
        set_tenant(session, user_id)
        case = session.scalar(select(ApplicationCase).where(ApplicationCase.id == case_id))
        if case is None:
            print(f"case {case_id} not found for tenant {user_id!r}", file=sys.stderr)
            raise SystemExit(1)

        match = next(
            (
                (record, version)
                for record, version in TravelRecordRepository.list_active_with_current_version(
                    session, case_id
                )
                if version.departure_date == departure
            ),
            None,
        )
        if match is None:
            print(f"no active trip departing {departure} in this case", file=sys.stderr)
            raise SystemExit(1)
        record, version = match

        user = CurrentUser(user_id=user_id, session_id="cli", email=None)
        residence_service.edit_travel_record(
            session,
            case=case,
            user=user,
            travel_record_id=record.id,
            fields=TravelRecordFields(
                destination_label=version.destination_label,
                departure_date=version.departure_date,
                return_date=new_return,
                date_confidence=DateConfidence(version.date_confidence),
                review_state=TravelReviewState(version.review_state),
                destination_country_code=version.destination_country_code,
                notes=version.notes,
            ),
            expected_revision=None,
        )
        print(
            f"edited trip departing {departure}: return {version.return_date} -> {new_return}.\n"
            f"residence results are now STALE — run `just recalc {case_id}` to refresh."
        )
    finally:
        session.close()


if __name__ == "__main__":
    main()
