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
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.assessments.domain import AssessmentResult, AssessmentRun
from app.assessments.invalidation import resolve_affected_requirements
from app.assessments.simulation import simulate_application_date
from app.cases.domain import ApplicationCase
from app.issues.domain import Issue, IssueResolution
from app.requirements.models import DependencyInputKind
from app.requirements.rules_core import absence_union, physical_presence_date
from app.seed.demo_case import DEMO_TRIPS, seed_demo_case
from app.shared.db import Base
from tests.conftest import _REFERENCE_TABLES

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
    """Everything a simulation must not touch.

    Two layers. Row counts over *every* table, derived from the metadata so the check
    cannot fall behind a table added later — that is what would catch a read path that
    writes only an audit row or an outbox event, which the detailed rows below and the
    `session.new` check would both miss (a unit-of-work commit clears `session.new`).
    Then the fields a stray `invalidate_for_input_change` would actually move: currency,
    `marked_stale_at`, `superseded_by_result_id`."""
    session.expire_all()  # read committed state, not the identity map
    counts = {
        table.name: session.execute(select(func.count()).select_from(table)).scalar_one()
        for table in Base.metadata.sorted_tables
        if table.name not in _REFERENCE_TABLES
    }
    return {
        "row_counts": counts,
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
    """Forty-six distinct candidates spanning more than a year either side, byte-identical
    case state.

    Once would prove the happy path. The spread is aimed at the failure this test exists to
    catch — a write that lands on only some branch, such as the presence rule's forward
    search finding a resolving date on one candidate and not another, or the leap-day clamp.
    An earlier version generated fifty candidates that were thirty distinct dates all inside
    one April, and crossed no month, year or leap boundary at all."""
    case_id = _assessed_case(api, db_session)
    before = _case_snapshot(db_session)

    candidates = [date(2027, 4, 15) + timedelta(days=step) for step in range(-380, 380, 17)]
    candidates.append(date(2028, 2, 29))  # the clamp branch (RULES_SPEC §4.1)
    assert len(set(candidates)) == len(candidates)
    for candidate in candidates:
        assert _simulate(api, case_id, candidate.isoformat()).status_code == 200

    assert _case_snapshot(db_session) == before


def test_simulating_never_marks_a_result_stale_or_reconciles_the_queue(
    api: Api, db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The two seams a preview must not reach, wired to explode.

    `invalidate_for_input_change` ends with an unconditional `issues_service.reconcile`, so
    reaching either one reaches both — and reconcile flushes the session, which would turn
    any accidental pending write into a real one."""
    case_id = _assessed_case(api, db_session)

    def explode(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("a simulation reached a write path")

    # Patched at the *binding*, not on the defining module. `app/residence/service.py` does
    # `from app.assessments.invalidation import invalidate_for_input_change`, so the name it
    # calls is its own — setting the attribute on `app.assessments.invalidation` is never
    # consulted and the seam would look guarded while being wide open.
    monkeypatch.setattr("app.residence.service.invalidate_for_input_change", explode)
    monkeypatch.setattr("app.assessments.service.issues_service.reconcile", explode)

    assert _simulate(api, case_id, RESOLVING_DATE).status_code == 200

    # The patches are live: the same write path a simulation must avoid does explode.
    with pytest.raises(AssertionError, match="write path"):
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

    for key, row in _by_key(body).items():
        after = row["after"]
        detail = api("user_a").get(f"/api/v1/cases/{case_id}/requirements/{key}").json()
        assert after["conclusion"] == detail["conclusion"], key
        assert after["summary_code"] == detail["summary_code"], key
        assert after["summary"]["text"] == detail["summary"]["text"], key
        # The two fields the rendered text does not cover, and the ones the UI's
        # breakdown component reads. Without these the "field for field" claim is three
        # fields wide and `window_start`, `threshold` and `trip_count` could all drift
        # unseen.
        assert after["summary_parameters"] == detail["summary_parameters"], key
        assert after["calculation_breakdown"] == detail["calculation_breakdown"], key
        assert [item["code"] for item in after["limitations"]] == [
            item["code"] for item in detail["limitations"]
        ], key
        assert row["changed"]["any"] is False, key


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
    assert presence["changed"]["conclusion"] is True

    # 439 - 10: trip 1's absent set (15-25 Apr 2022) is now wholly before the window,
    # and the final-year trips stay inside it, so nothing enters to replace those days.
    total = rows["residence.total_absences"]
    assert total["before"]["summary_parameters"]["days"] == 439
    assert total["after"]["summary_parameters"]["days"] == 429
    # Still 21 days below the 450 limit, so still the same band — the figure moved, the
    # conclusion did not, and the response must not imply otherwise.
    assert total["before"]["conclusion"] == "NEAR_THRESHOLD"
    assert total["after"]["conclusion"] == "NEAR_THRESHOLD"
    assert total["changed"]["conclusion"] is False
    assert total["changed"]["summary_parameters"] is True  # the figure moved even so
    assert total["changed"]["any"] is True

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


def test_the_response_can_express_a_change_that_is_not_a_change_of_conclusion(
    api: Api, db_session: Session
) -> None:
    """`residence.travel_consistency` is a data-quality rule with no eligibility conclusion
    of its own (RULES_SPEC §7.8) — its entire output is limitations. Moving past the trip
    that covered the presence anchor swaps `NEAR_STANDARD_THRESHOLD` for
    `TRAVEL_OUTSIDE_WINDOW` while conclusion and summary code both stay put.

    So this is the one requirement in the fixture that proves the response can say
    something moved without the conclusion moving. Before `limitations` was carried, the
    API reported "nothing changed" for the rule whose whole job is surfacing exactly this.
    """
    case_id = _assessed_case(api, db_session)
    row = _by_key(_simulate(api, case_id, RESOLVING_DATE).json())["residence.travel_consistency"]

    assert row["before"]["conclusion"] == row["after"]["conclusion"] == "SUPPORTED"
    assert row["before"]["summary_code"] == row["after"]["summary_code"]
    assert row["changed"]["conclusion"] is False

    before_codes = {item["code"] for item in row["before"]["limitations"]}
    after_codes = {item["code"] for item in row["after"]["limitations"]}
    # Trip 1 covered the anchor at 15 Apr; at 25 Apr it is wholly outside the window.
    assert "NEAR_STANDARD_THRESHOLD" in before_codes
    assert "NEAR_STANDARD_THRESHOLD" not in after_codes
    assert "TRAVEL_OUTSIDE_WINDOW" in after_codes

    assert row["changed"]["limitations"] is True
    assert row["changed"]["any"] is True


def test_a_leap_day_candidate_states_the_assumption_it_rests_on(
    api: Api, db_session: Session
) -> None:
    """RULES_SPEC §4.1 commits to clamping 29 Feb to 28 Feb and requires the assumption to
    be visible rather than hidden, because it moves the presence anchor by a day and the
    anchor is where this case turns.

    Nothing implemented that limitation until the simulator made 29 February reachable by
    typing — a saved date is chosen once and deliberately; a preview field invites trying
    dates. The §4.1 table gives 2028-02-29 → 2023-02-28 → qualifying start 2023-03-01."""
    case_id = _assessed_case(api, db_session)
    body = _simulate(api, case_id, "2028-02-29").json()

    assert body["windows_after"]["qualifying_period_start"] == "2023-03-01"

    row = _by_key(body)["residence.qualifying_period"]
    limitation = next(
        item
        for item in row["after"]["limitations"]
        if item["code"] == "LEAP_DAY_BOUNDARY_ASSUMPTION"
    )
    assert limitation["severity"] == "INFORMATION"
    assert "29 February" in (limitation["text"] or "")
    # A date one day later carries no such assumption.
    assert not [
        item
        for item in _by_key(_simulate(api, case_id, "2028-03-01").json())[
            "residence.qualifying_period"
        ]["after"]["limitations"]
        if item["code"] == "LEAP_DAY_BOUNDARY_ASSUMPTION"
    ]


def test_the_before_windows_come_from_the_persisted_result_not_the_current_date(
    api: Api, db_session: Session
) -> None:
    """The whole before side has to be one snapshot.

    `/select` marks results STALE without recalculating, so between a date change and the
    recalculation the persisted figures were computed against the *previous* window.
    Deriving `windows_before` from the case's current date would then draw a window beside
    a total that window never produced."""
    case_id = _assessed_case(api, db_session)
    revision = api("user_a").get(f"/api/v1/cases/{case_id}/application-dates").json()["revision"]
    moved = api("user_a").post(
        f"/api/v1/cases/{case_id}/application-dates/select",
        json={"application_date": "2027-06-01", "expected_revision": revision},
    )
    assert moved.status_code == 200

    body = _simulate(api, case_id, RESOLVING_DATE).json()
    assert body["current_application_date"] == "2027-06-01"  # the case has moved on
    # ...but the stored figures still describe the window they were computed in.
    assert body["windows_before"]["qualifying_period_start"] == "2022-04-16"
    rows = _by_key(body)
    assert rows["residence.total_absences"]["before"]["summary_parameters"]["window_start"] == (
        "2022-04-16"
    )
    assert rows["residence.total_absences"]["before"]["stale"]["reason_code"] == (
        "APPLICATION_DATE_CHANGED"
    )


def test_a_never_assessed_case_reports_no_before_windows(api: Api, db_session: Session) -> None:
    """No result, no stored window — and none invented from the current date."""
    case_id = str(seed_demo_case(db_session, user_id="user_a"))
    body = _simulate(api, case_id, RESOLVING_DATE).json()

    assert body["windows_before"] is None
    assert body["windows_after"]["qualifying_period_start"] == "2022-04-26"


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

    Honest about its oracle: `absence_union` and `physical_presence_date` are the same
    `rules_core` primitives the evaluator calls, so this cannot catch an error *inside*
    them — `tests/rules/test_rules_core.py` covers those against the guidance's own worked
    example. What it does check independently is everything between: the trust gate, the
    evaluator's branching, the trip flattening, and the simulation's own wiring.
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


def test_a_case_still_onboarding_cannot_be_simulated(api: Api) -> None:
    """A DRAFT case has no confirmed route profile, so there is nothing to evaluate. The
    lifecycle gate runs before any input is read, so the caller gets the same 409 the other
    commands give rather than a `CASE_NOT_ASSESSABLE` about a missing date it was never
    asked for."""
    case_id = str(api("user_a").post("/api/v1/cases", json={"title": "draft"}).json()["id"])

    response = _simulate(api, case_id, RESOLVING_DATE)
    assert response.status_code == 409
    assert response.json()["code"] == "CASE_NOT_ACTIVE"


@pytest.mark.property
@settings(
    max_examples=12,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
@given(offset=st.integers(min_value=-60, max_value=120))
def test_a_preview_equals_the_save_it_previews(api: Api, db_session: Session, offset: int) -> None:
    """**The anti-fork property.** Preview a date, then actually select it and recalculate,
    and the persisted figures must equal the previewed ones — for an arbitrary date.

    Both paths call `evaluate_case`, so this holds structurally, and
    `test_simulating_the_current_date_reproduces_the_persisted_results` pins it at one
    point. But that point is `D = current_date`, where the two agree nearly by definition.
    This is the version that would catch a fork introduced anywhere the override changes
    behaviour — which is the whole surface a date simulator adds.

    Deliberately expensive and deliberately few examples: each one runs a full
    recalculation. Twelve is enough to cross the anchor-covering trip, the resolving date,
    and both ends of the window.
    """
    case_id = str(seed_demo_case(db_session, user_id="user_a"))
    assert api("user_a").post(f"/api/v1/cases/{case_id}/assessments/recalculate").status_code == 200
    candidate = (date(2027, 4, 15) + timedelta(days=offset)).isoformat()

    previewed = {
        key: (row["after"]["conclusion"], row["after"]["summary_parameters"])
        for key, row in _by_key(_simulate(api, case_id, candidate).json()).items()
    }

    revision = api("user_a").get(f"/api/v1/cases/{case_id}/application-dates").json()["revision"]
    assert (
        api("user_a")
        .post(
            f"/api/v1/cases/{case_id}/application-dates/select",
            json={"application_date": candidate, "expected_revision": revision},
        )
        .status_code
        == 200
    )
    assert api("user_a").post(f"/api/v1/cases/{case_id}/assessments/recalculate").status_code == 200

    saved = {
        row["requirement_key"]: row
        for row in api("user_a").get(f"/api/v1/cases/{case_id}/requirements").json()
    }
    for key, (conclusion, parameters) in previewed.items():
        assert saved[key]["conclusion"] == conclusion, f"{key} at {candidate}"
        detail = api("user_a").get(f"/api/v1/cases/{case_id}/requirements/{key}").json()
        assert detail["summary_parameters"] == parameters, f"{key} at {candidate}"
