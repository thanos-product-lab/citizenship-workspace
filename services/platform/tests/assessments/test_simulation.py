"""Provisional mode: a real calculation that leaves the case exactly as it found it.

Domain §10.3 — *"Previewing another date does not change the case or mark assessments
stale"* — and §42.2, which requires a provisional result to be structurally incapable of
being read as current. Both are invariants rather than features, so they are asserted
directly rather than inferred from a happy path.

The expected figures are transcribed by hand from `SYNTHETIC_DEMO_CASE.md` §8 and the
`RULES_SPEC` §5 working, never recomputed from the code under test. **429** is derived
here for the first time and belongs in the fixture doc: moving the application date to
25 Apr 2027 starts the window on 26 Apr 2022, and trip 1's absent set (15-25 Apr 2022)
then falls entirely outside it, so its 10 counted days leave and nothing enters —
439 - 10 = 429.
"""

from collections.abc import Callable
from datetime import date, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.assessments.domain import AssessmentResult, AssessmentRun
from app.assessments.invalidation import resolve_affected_requirements
from app.assessments.simulation import simulate_application_date
from app.cases.domain import ApplicationCase
from app.issues.domain import Issue, IssueResolution
from app.requirements.models import DependencyInputKind
from app.requirements.rules_core import absence_union, physical_presence_date
from app.seed.demo_case import DEMO_TRIPS, seed_demo_case

pytestmark = pytest.mark.integration

Api = Callable[[str], TestClient]

CURRENT_DATE = "2027-04-15"
RESOLVING_DATE = "2027-04-25"  # SYNTHETIC_DEMO_CASE.md §8, derived from trip 1's return
LAST_FAILING_DATE = "2027-04-24"  # anchor 25 Apr 2022 — still the last day of trip 1's set


def _assessed_case(api: Api, db_session: Session) -> str:
    case_id = str(seed_demo_case(db_session, user_id="user_a"))
    assert api("user_a").post(f"/api/v1/cases/{case_id}/assessments/recalculate").status_code == 200
    return case_id


def _simulate(api: Api, case_id: str, candidate: str, user: str = "user_a") -> Any:
    return api(user).post(
        f"/api/v1/cases/{case_id}/application-dates/simulate",
        json={"candidate_application_date": candidate},
    )


def _by_key(body: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {row["requirement_key"]: row for row in body["requirements"]}


def _case_snapshot(session: Session) -> dict[str, Any]:
    """Everything a simulation must not touch: the immutable assessment graph and the
    queue derived from it. Currency and `marked_stale_at` are in here explicitly — those
    are what a stray `invalidate_for_input_change` would move."""
    session.expire_all()  # read committed state, not the identity map
    return {
        "runs": sorted(
            (str(r.id), r.status, r.mode, r.trigger_type)
            for r in session.scalars(select(AssessmentRun))
        ),
        "results": sorted(
            (
                str(r.id),
                r.conclusion,
                r.currency,
                str(r.marked_stale_at),
                str(r.superseded_by_result_id),
                r.summary_code or "",
            )
            for r in session.scalars(select(AssessmentResult))
        ),
        "issues": sorted(
            (str(i.id), i.status, i.issue_type, str(i.resolved_at))
            for i in session.scalars(select(Issue))
        ),
        "resolutions": sorted(str(r.id) for r in session.scalars(select(IssueResolution))),
    }


# --- The invariant: nothing moves --------------------------------------------


def test_simulating_many_dates_changes_nothing_about_the_case(
    api: Api, db_session: Session
) -> None:
    """Fifty simulations, fifty different dates, byte-identical case state.

    Once would prove the happy path. The repetition is aimed at the failure this test
    exists to catch — a write that only lands on some branch, such as the presence rule's
    forward search finding a resolving date on one candidate and not another."""
    case_id = _assessed_case(api, db_session)
    before = _case_snapshot(db_session)

    for offset in range(50):
        candidate = date(2027, 4, 1).replace(day=1 + offset % 30)
        assert _simulate(api, case_id, candidate.isoformat()).status_code == 200

    assert _case_snapshot(db_session) == before


def test_simulating_never_marks_a_result_stale_or_reconciles_the_queue(
    api: Api, db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The two seams a preview must not reach, wired to explode.

    `invalidate_for_input_change` ends with an unconditional `issues_service.reconcile`, so
    reaching either one reaches both — and reconcile flushes the session, which would turn
    any accidental pending write into a real one."""
    from app.assessments import invalidation
    from app.issues import service as issues_service

    case_id = _assessed_case(api, db_session)

    def explode(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("a simulation reached a write path")

    monkeypatch.setattr(invalidation, "invalidate_for_input_change", explode)
    monkeypatch.setattr(issues_service, "reconcile", explode)

    assert _simulate(api, case_id, RESOLVING_DATE).status_code == 200


def test_a_simulation_leaves_no_pending_work_on_the_session(api: Api, db_session: Session) -> None:
    """Nothing added, nothing dirtied, nothing deleted. The API shares this session, so a
    stray `session.add` would show up here — and would be committed by whatever ran next."""
    case_id = _assessed_case(api, db_session)
    assert _simulate(api, case_id, RESOLVING_DATE).status_code == 200

    # `IdentitySet`, not `set` — compare emptiness, not equality.
    assert not db_session.new, f"a simulation added {list(db_session.new)}"
    assert not db_session.dirty, f"a simulation modified {list(db_session.dirty)}"
    assert not db_session.deleted, f"a simulation deleted {list(db_session.deleted)}"


# --- The invariant: the arithmetic cannot fork -------------------------------


def test_simulating_the_current_date_reproduces_the_persisted_results(
    api: Api, db_session: Session
) -> None:
    """The property that makes "the preview is what a save would give you" true.

    Both paths call `evaluate_case`, so this holds structurally — and it goes red the
    moment anyone reimplements a window or a total for preview, which is the only way the
    demo's numbers could quietly diverge from the case's own."""
    case_id = _assessed_case(api, db_session)
    body = _simulate(api, case_id, CURRENT_DATE).json()

    persisted = {
        row["requirement_key"]: row
        for row in api("user_a").get(f"/api/v1/cases/{case_id}/requirements").json()
    }
    for key, row in _by_key(body).items():
        after = row["after"]
        assert after["conclusion"] == persisted[key]["conclusion"], key
        assert after["summary_code"] == persisted[key]["summary_code"], key
        assert after["summary"]["text"] == persisted[key]["summary"]["text"], key
        assert row["conclusion_changed"] is False, key


def test_a_simulation_covers_every_requirement_an_application_date_change_invalidates(
    api: Api, db_session: Session
) -> None:
    """Tied to the dependency declarations rather than to a list.

    ADR-0014 resolves the affected set of an input change from `rule_dependency_definitions`
    closed over the composition edges. If a rule ever declares a dependency on the
    application date that the simulator does not evaluate, the preview would be silently
    incomplete — showing the user an unchanged conclusion that a save would move."""
    case_id = _assessed_case(api, db_session)
    body = _simulate(api, case_id, RESOLVING_DATE).json()

    affected = resolve_affected_requirements(
        db_session, input_kind=DependencyInputKind.PROPOSED_APPLICATION_DATE
    )
    missing = affected - set(_by_key(body))
    assert missing == set(), f"the simulation does not evaluate {missing}"


# --- The canonical case: the demo's own numbers ------------------------------


def test_moving_to_the_resolving_date_flips_presence_and_shifts_the_window(
    api: Api, db_session: Session
) -> None:
    """SYNTHETIC_DEMO_CASE.md §8, as an interaction. Hand-derived values only."""
    case_id = _assessed_case(api, db_session)
    body = _simulate(api, case_id, RESOLVING_DATE).json()

    assert body["saved"] is False
    assert body["mode"] == "PROVISIONAL"
    assert body["current_application_date"] == CURRENT_DATE
    assert body["candidate_application_date"] == RESOLVING_DATE

    # The whole window moves — ADR-0002. Not one day, and not just the anchor.
    assert body["windows_before"] == {
        "qualifying_period_start": "2022-04-16",
        "qualifying_period_end": "2027-04-15",
        "final_year_start": "2026-04-16",
        "final_year_end": "2027-04-15",
        "presence_anchor": "2022-04-16",
    }
    assert body["windows_after"] == {
        "qualifying_period_start": "2022-04-26",
        "qualifying_period_end": "2027-04-25",
        "final_year_start": "2026-04-26",
        "final_year_end": "2027-04-25",
        "presence_anchor": "2022-04-26",
    }

    rows = _by_key(body)

    presence = rows["residence.physical_presence_start_date"]
    assert presence["before"]["conclusion"] == "NOT_CURRENTLY_SATISFIED"
    assert presence["before"]["currency"] == "CURRENT"
    assert presence["after"]["conclusion"] == "SUPPORTED"
    assert presence["after"]["currency"] == "PROVISIONAL"
    assert presence["conclusion_changed"] is True

    # 439 - 10: trip 1's absent set (15-25 Apr 2022) is now wholly before the window,
    # and the final-year trips stay inside it, so nothing enters to replace those days.
    total = rows["residence.total_absences"]
    assert total["before"]["summary_parameters"]["days"] == 439
    assert total["after"]["summary_parameters"]["days"] == 429
    # Still 21 days below the 450 limit, so still the same band — the figure moved, the
    # conclusion did not, and the response must not imply otherwise.
    assert total["before"]["conclusion"] == "NEAR_THRESHOLD"
    assert total["after"]["conclusion"] == "NEAR_THRESHOLD"
    assert total["conclusion_changed"] is False

    final_year = rows["residence.final_year_absences"]
    assert final_year["before"]["summary_parameters"]["days"] == 17
    assert final_year["after"]["summary_parameters"]["days"] == 17


def test_the_day_before_the_resolving_date_still_fails_presence(
    api: Api, db_session: Session
) -> None:
    """ADR-0002, asserted rather than described.

    Clearing an absent anchor means moving past the whole trip that covers it. Trip 1
    returns 26 Apr 2022, so its absent set runs 15-25 Apr and every application date from
    15 to 24 April 2027 has an anchor inside it. A one-day move fixes nothing, and neither
    does a nine-day one."""
    case_id = _assessed_case(api, db_session)

    for candidate in ("2027-04-16", "2027-04-20", LAST_FAILING_DATE):
        rows = _by_key(_simulate(api, case_id, candidate).json())
        presence = rows["residence.physical_presence_start_date"]
        assert presence["after"]["conclusion"] == "NOT_CURRENTLY_SATISFIED", candidate


def test_the_simulation_surfaces_the_resolving_date_the_rule_found(
    api: Api, db_session: Session
) -> None:
    """The value that turns a refusal into an action (RULES_SPEC §7.5), lifted out of the
    rule's parameters to the top of the response so the client never has to go looking."""
    case_id = _assessed_case(api, db_session)

    assert _simulate(api, case_id, CURRENT_DATE).json()["resolving_application_date"] == (
        RESOLVING_DATE
    )
    # Once the date resolves, there is nothing left to resolve to.
    assert _simulate(api, case_id, RESOLVING_DATE).json()["resolving_application_date"] is None


# --- Boundaries --------------------------------------------------------------


def test_a_stale_before_side_is_reported_as_stale(api: Api, db_session: Session) -> None:
    """The comparison is against what the case concluded, not against what it would
    conclude if rerun. Recomputing the baseline would let a preview quietly launder a stale
    result into a fresh-looking one."""
    case_id = _assessed_case(api, db_session)
    api("user_a").post(
        f"/api/v1/cases/{case_id}/travel-records",
        json={
            "destination_label": "Trip",
            "departure_date": "2023-06-01",
            "return_date": "2023-07-02",
            "date_confidence": "EXACT",
            "review_state": "CONFIRMED",
        },
    )

    rows = _by_key(_simulate(api, case_id, RESOLVING_DATE).json())
    assert rows["residence.total_absences"]["before"]["currency"] == "STALE"
    assert rows["residence.total_absences"]["before"]["conclusion"] == "NEAR_THRESHOLD"


def test_a_case_with_no_application_date_cannot_be_simulated(api: Api) -> None:
    """No "before" side exists, so a comparison would be half a comparison. 409 with the
    code the client uses to send the user to the missing step."""
    case_id = str(api("user_a").post("/api/v1/cases", json={"title": "c"}).json()["id"])
    api("user_a").put(
        f"/api/v1/cases/{case_id}/route-profile",
        json={
            "date_of_birth": "1990-05-01",
            "status_type": "ILR",
            "status_granted_on": "2019-01-01",
            "married_to_british_citizen": False,
            "may_already_be_british": False,
        },
    )
    api("user_a").post(f"/api/v1/cases/{case_id}/route-profile/confirm", json={})

    response = _simulate(api, case_id, RESOLVING_DATE)
    assert response.status_code == 409
    assert response.json()["code"] == "CASE_NOT_ASSESSABLE"


def test_a_never_assessed_case_compares_against_no_conclusion(
    api: Api, db_session: Session
) -> None:
    """Seeded but never recalculated: the "before" side is the absence of a conclusion, and
    says so with a null currency rather than a manufactured one."""
    case_id = str(seed_demo_case(db_session, user_id="user_a"))

    rows = _by_key(_simulate(api, case_id, RESOLVING_DATE).json())
    presence = rows["residence.physical_presence_start_date"]
    assert presence["before"]["conclusion"] == "NOT_YET_ASSESSED"
    assert presence["before"]["currency"] is None
    assert presence["after"]["conclusion"] == "SUPPORTED"


def test_a_simulation_is_not_visible_to_another_user(api: Api, db_session: Session) -> None:
    case_id = _assessed_case(api, db_session)
    assert _simulate(api, case_id, RESOLVING_DATE, user="user_b").status_code == 404


# --- The property ------------------------------------------------------------


@pytest.mark.property
@settings(
    max_examples=40, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture]
)
@given(offset=st.integers(min_value=-400, max_value=400))
def test_simulated_presence_agrees_with_the_rule_definition(
    api: Api, db_session: Session, offset: int
) -> None:
    """For any candidate date, presence is SUPPORTED exactly when the anchor is not an
    absent day — checked against an independent computation from `rules_core`, not against
    the evaluator's own answer.

    Driven through the service rather than HTTP so the example count is affordable. The
    range spans more than a year either side of the demo's date, so it crosses the trips
    that sit at both ends of the window as well as the anchor-covering trip 1.
    """
    case = db_session.get(ApplicationCase, seed_demo_case(db_session, user_id="user_a"))
    assert case is not None
    candidate = date(2027, 4, 15) + timedelta(days=offset)

    view = simulate_application_date(db_session, case=case, candidate_date=candidate)
    conclusion = next(
        row.after.conclusion
        for row in view.requirements
        if row.definition.requirement_key == "residence.physical_presence_start_date"
    )

    trusted_absent = absence_union((trip.departure_date, trip.return_date) for trip in DEMO_TRIPS)
    expected_supported = physical_presence_date(candidate) not in trusted_absent
    assert (conclusion == "SUPPORTED") is expected_supported, candidate
