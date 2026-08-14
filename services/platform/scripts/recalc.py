"""Recalculate a case and print its requirement conclusions — a dev convenience for the
M3B walkthrough, running the same command the `POST /assessments/recalculate` route calls
but without the Clerk auth hop.

    just recalc <case_id> [user_id]

`user_id` defaults to `demo-user` (what `just seed` uses); it is the RLS tenant the case is
read under, so it must own the case. Requires the DB up and migrated.
"""

import sys
import uuid

from sqlalchemy import select

from app.assessments import service as assessments_service
from app.auth.schemas import CurrentUser
from app.cases.domain import ApplicationCase
from app.shared.db import get_sessionmaker
from app.shared.tenant import set_tenant


def main() -> None:
    if len(sys.argv) < 2:
        print("usage: python -m scripts.recalc <case_id> [user_id]", file=sys.stderr)
        raise SystemExit(2)
    case_id = uuid.UUID(sys.argv[1])
    user_id = sys.argv[2] if len(sys.argv) > 2 else "demo-user"

    session = get_sessionmaker()()
    try:
        set_tenant(session, user_id)
        case = session.scalar(select(ApplicationCase).where(ApplicationCase.id == case_id))
        if case is None:
            print(f"case {case_id} not found for tenant {user_id!r}", file=sys.stderr)
            raise SystemExit(1)

        user = CurrentUser(user_id=user_id, session_id="cli", email=None)
        outcome = assessments_service.recalculate(session, case=case, user=user)

        print(f"run {outcome.run.id}  mode={outcome.run.mode}  results={outcome.result_count}\n")
        print(f"{'requirement':40} {'conclusion':26} {'currency':10} figure")
        print("-" * 90)
        for definition, result in outcome.requirements:
            if result is None:
                print(f"{definition.requirement_key:40} {'NOT_YET_ASSESSED':26} {'-':10}")
                continue
            figure = (
                result.summary_parameters.get("days")
                or result.summary_parameters.get("resolving_application_date")
                or ""
            )
            print(
                f"{definition.requirement_key:40} {result.conclusion:26} "
                f"{result.currency:10} {figure}"
            )
    finally:
        session.close()


if __name__ == "__main__":
    main()
