"""status.holding_period (§7.3) and residence.travel_consistency (§7.8) evaluators. Pure."""

import uuid
from datetime import date

from app.requirements.domain import Conclusion
from app.requirements.evaluation import (
    KEY_TRAVEL_CONSISTENCY,
    EvaluatedResult,
    ResidenceAssessmentInputs,
    RouteAssessmentInputs,
    TripInput,
    evaluate_residence_requirements,
    evaluate_status_holding_period,
)

_APP = date(2027, 4, 15)


def _status_inputs(granted: date | None, app: date = _APP) -> RouteAssessmentInputs:
    return RouteAssessmentInputs(
        date_of_birth=date(1990, 5, 1),
        status_type="ILR",
        status_granted_on=granted,
        married_to_british_citizen=False,
        may_already_be_british=False,
        application_date=app,
        route_profile_version_id=uuid.uuid4(),
        application_date_version_id=uuid.uuid4(),
    )


def test_holding_period_supported_with_clear_margin() -> None:
    result = evaluate_status_holding_period(_status_inputs(date(2025, 3, 1)))
    # earliest = 2026-03-01; app 2027-04-15 is well past earliest + 7 days.
    assert result.conclusion == Conclusion.SUPPORTED.value
    assert result.summary_code == "STATUS_PERIOD_SATISFIED"
    assert result.summary_parameters["earliest_application_date"] == "2026-03-01"


def test_holding_period_narrow_margin_is_supported_with_caution() -> None:
    # earliest = 2026-04-16; app 2026-04-20 is inside the 7-day caution band.
    result = evaluate_status_holding_period(
        _status_inputs(date(2025, 4, 16), app=date(2026, 4, 20))
    )
    assert result.conclusion == Conclusion.SUPPORTED.value
    assert result.summary_code == "STATUS_PERIOD_NARROW_MARGIN"
    assert result.limitations[0].severity.value == "CAUTION"


def test_holding_period_not_yet_met_returns_earliest_date() -> None:
    # earliest = 2027-05-01; app 2027-04-15 is before it.
    result = evaluate_status_holding_period(_status_inputs(date(2026, 5, 1), app=date(2027, 4, 15)))
    assert result.conclusion == Conclusion.NOT_CURRENTLY_SATISFIED.value
    assert result.summary_code == "STATUS_PERIOD_NOT_YET_MET"
    assert result.next_actions[0].label_parameters["earliest_application_date"] == "2027-05-01"


def test_holding_period_incomplete_when_grant_date_missing() -> None:
    result = evaluate_status_holding_period(_status_inputs(None))
    assert result.conclusion == Conclusion.INCOMPLETE.value


def _consistency(*trips: TripInput) -> EvaluatedResult:
    inputs = ResidenceAssessmentInputs(
        application_date=_APP, application_date_version_id=uuid.uuid4(), trips=tuple(trips)
    )
    return {r.requirement_key: r for r in evaluate_residence_requirements(inputs)}[
        KEY_TRAVEL_CONSISTENCY
    ]


def _trip(dep: date, ret: date, *, confidence: str = "EXACT", trusted: bool = True) -> TripInput:
    return TripInput(dep, ret, uuid.uuid4(), trusted, confidence)


def test_consistency_supported_with_clean_records() -> None:
    result = _consistency(_trip(date(2023, 1, 1), date(2023, 1, 20)))
    assert result.conclusion == Conclusion.SUPPORTED.value
    assert result.summary_code == "TRAVEL_RECORDS_CONSISTENT"


def test_conflicting_date_is_inconsistent() -> None:
    result = _consistency(_trip(date(2023, 1, 1), date(2023, 1, 20), confidence="CONFLICTING"))
    assert result.conclusion == Conclusion.INCONSISTENT.value
    assert result.summary_code == "TRAVEL_RECORDS_CONFLICT"
    assert result.limitations[0].code == "CONFLICTING_SOURCE_DATES"


def test_overlapping_trips_are_inconsistent() -> None:
    result = _consistency(
        _trip(date(2023, 1, 1), date(2023, 1, 20)),
        _trip(date(2023, 1, 10), date(2023, 1, 30)),
    )
    assert result.conclusion == Conclusion.INCONSISTENT.value
    assert result.summary_code == "TRAVEL_RECORDS_OVERLAP"


def test_uncertain_date_is_incomplete() -> None:
    result = _consistency(_trip(date(2023, 1, 1), date(2023, 1, 20), confidence="ESTIMATED"))
    assert result.conclusion == Conclusion.INCOMPLETE.value
    assert result.summary_code == "TRAVEL_RECORDS_UNCERTAIN"


def test_out_of_window_conflict_is_not_flagged() -> None:
    # A CONFLICTING trip wholly before the qualifying window (starts 2022-04-16 for this app
    # date) is informational only: window-scoped like UNCERTAIN, it is not surfaced (§7.8).
    result = _consistency(_trip(date(2019, 1, 1), date(2019, 1, 20), confidence="CONFLICTING"))
    assert result.conclusion == Conclusion.SUPPORTED.value
    assert result.summary_code == "TRAVEL_RECORDS_CONSISTENT"




def test_boundary_trip_is_flagged_but_stays_consistent() -> None:
    # A trip whose absent set contains the anchor 2022-04-16 raises a boundary note, but
    # a single clean-confidence trip is not itself an inconsistency.
    result = _consistency(_trip(date(2022, 4, 14), date(2022, 4, 26)))
    assert result.conclusion == Conclusion.SUPPORTED.value
    assert any(limitation.code == "NEAR_STANDARD_THRESHOLD" for limitation in result.limitations)
