"""Print one requirement's full detail — conclusion, currency, parameters, breakdown,
limitations, next actions, input-link provenance, and history. Mirrors
`GET /requirements/{key}` without the Clerk auth hop.

    just inspect <case_id> <requirement_key> [user_id]
"""

import sys
import uuid

from sqlalchemy import select

from app.assessments import service as assessments_service
from app.cases.domain import ApplicationCase
from app.shared.db import get_sessionmaker
from app.shared.tenant import set_tenant


def main() -> None:
    if len(sys.argv) < 3:
        print(
            "usage: python -m scripts.inspect <case_id> <requirement_key> [user_id]",
            file=sys.stderr,
        )
        raise SystemExit(2)
    case_id = uuid.UUID(sys.argv[1])
    key = sys.argv[2]
    user_id = sys.argv[3] if len(sys.argv) > 3 else "demo-user"

    session = get_sessionmaker()()
    try:
        set_tenant(session, user_id)
        case = session.scalar(select(ApplicationCase).where(ApplicationCase.id == case_id))
        if case is None:
            print(f"case {case_id} not found for tenant {user_id!r}", file=sys.stderr)
            raise SystemExit(1)

        view = assessments_service.get_requirement_detail(session, case=case, requirement_key=key)
        if view is None:
            print(f"requirement {key!r} is not catalogued", file=sys.stderr)
            raise SystemExit(1)

        print(f"# {view.definition.requirement_key} — {view.definition.title}")
        current = view.current
        if current is None:
            print("conclusion : NOT_YET_ASSESSED (no result yet)")
            return

        print(f"conclusion : {current.conclusion}")
        print(f"currency   : {current.currency}")
        print(f"summary    : {current.summary_code}")
        print(f"parameters : {current.summary_parameters}")
        if current.calculation_breakdown:
            print(f"breakdown  : {current.calculation_breakdown}")
        for limitation in current.limitations:
            print(f"limitation : {limitation.get('code')} ({limitation.get('severity')})")
        for action in current.next_actions:
            print(f"next action: {action.get('code')} {action.get('label_parameters')}")

        # Resolved inputs rather than bare link rows: M4 turned `input_links` into
        # `inputs`, each carrying the value that was read and whether that version is
        # still the current one. This capture is the oracle the screens are checked
        # against, so it prints what the screen prints.
        print("inputs read:")
        for link in view.inputs:
            key_note = f" [{link.input_key}]" if link.input_key else ""
            stale_note = "" if link.is_still_current else "  (superseded since)"
            counted = {True: "counted", False: "not counted", None: "n/a"}[link.counts_as_confirmed]
            print(
                f"  - {link.input_kind}{key_note}: {link.label} = {link.value}"
                f"  v{link.version_number}  {counted}{stale_note}"
            )

        print("history (newest first):")
        for row in view.history:
            print(f"  - {row.created_at:%Y-%m-%d %H:%M}  {row.conclusion:24} {row.currency}")
    finally:
        session.close()


if __name__ == "__main__":
    main()
