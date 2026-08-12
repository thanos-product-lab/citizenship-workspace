"""The four residence evaluators: banding, the §6.2 sensitivity rule, the presence 3-way,
and the resolving date. Pure — built from `TripInput`s directly, no DB.

Day counts are taken as given (RULES_SPEC §5 counting is proved in `test_rules_core`); these
tests exercise the *evaluator* layer — which band, which conclusion, which limitation, and
that provisional data only ever makes the answer more cautious.
"""

import uuid
from datetime import date, timedelta

import pytest
from hypothesis import given
from hypothesis import strategies as st

from app.requirements.domain import Conclusion
from app.requirements.evaluation import (
    KEY_FINAL_YEAR_ABSENCES,
    KEY_PHYSICAL_PRESENCE,
    KEY_QUALIFYING_PERIOD,
    KEY_TOTAL_ABSENCES,
    EvaluatedResult,
    ResidenceAssessmentInputs,
    TripInput,
    evaluate_residence_requirements,
)
from app.requirements.rules_core import band_total_absences, severity

_APP = date(2027, 4, 15)


def _trip(dep: date, absent_days: int, *, trusted: bool = True) -> TripInput:
    # A trip with exactly `absent_days` whole days abroad: return = departure + days + 1.
    return TripInput(
        departure_date=dep,
        return_date=dep + timedelta(days=absent_days + 1),
        travel_record_version_id=uuid.uuid4(),
        is_trusted=trusted,
    )


def _evaluate(*trips: TripInput, app: date = _APP) -> dict[str, EvaluatedResult]:
    inputs = ResidenceAssessmentInputs(
        application_date=app, application_date_version_id=uuid.uuid4(), trips=tuple(trips)
    )
    return {r.requirement_key: r for r in evaluate_residence_requirements(inputs)}


def test_qualifying_period_is_derived_and_supported() -> None:
    result = _evaluate()[KEY_QUALIFYING_PERIOD]
    assert result.conclusion == Conclusion.SUPPORTED.value
    assert result.summary_code == "QUALIFYING_PERIOD_DERIVED"
    breakdown = result.calculation_breakdown
    assert breakdown["qualifying_period_start"] == "2022-04-16"
    assert breakdown["physical_presence_date"] == "2022-04-16"
    assert breakdown["final_year_start"] == "2026-04-16"


def test_presence_supported_when_no_trip_covers_the_anchor() -> None:
    result = _evaluate(_trip(date(2023, 1, 1), 30))[KEY_PHYSICAL_PRESENCE]
    assert result.conclusion == Conclusion.SUPPORTED.value
    assert result.summary_code == "PRESENCE_CONFIRMED"


def test_presence_not_satisfied_offers_the_resolving_date() -> None:
    # A trusted trip 14→26 Apr 2022 covers the anchor 16 Apr 2022 → confirmed absent.
    result = _evaluate(TripInput(date(2022, 4, 14), date(2022, 4, 26), uuid.uuid4(), True))[
        KEY_PHYSICAL_PRESENCE
    ]
    assert result.conclusion == Conclusion.NOT_CURRENTLY_SATISFIED.value
    assert result.summary_code == "PRESENCE_NOT_SUPPORTED"
    assert result.summary_parameters["resolving_application_date"] == "2027-04-25"
    assert result.next_actions[0].code == "SELECT_APPLICATION_DATE"
    assert result.next_actions[0].blocking is True


def test_presence_uncertain_when_only_an_unconfirmed_trip_covers_the_anchor() -> None:
    # Same covering trip, but ESTIMATED (not trusted): the anchor is only provisionally absent.
    result = _evaluate(TripInput(date(2022, 4, 14), date(2022, 4, 26), uuid.uuid4(), False))[
        KEY_PHYSICAL_PRESENCE
    ]
    assert result.conclusion == Conclusion.INCOMPLETE.value
    assert result.summary_code == "PRESENCE_UNCERTAIN"
    assert result.limitations[0].code == "UNCONFIRMED_RECORDS_AFFECT_CONCLUSION"


def test_total_absences_bands_the_trusted_total() -> None:
    result = _evaluate(_trip(date(2023, 1, 1), 430))[KEY_TOTAL_ABSENCES]
    assert result.conclusion == Conclusion.NEAR_THRESHOLD.value  # 430 → 421-450
    assert result.summary_parameters["days"] == 430
    assert result.summary_parameters["threshold"] == 450


def test_sensitivity_downgrades_but_does_not_upgrade() -> None:
    # Trusted 400 (SUPPORTED); an ESTIMATED 60-day trip pushes provisional to 460
    # (REQUIRES_JUDGEMENT). The conclusion downgrades and carries the review limitation.
    result = _evaluate(
        _trip(date(2023, 1, 1), 400, trusted=True),
        _trip(date(2024, 6, 1), 60, trusted=False),
    )[KEY_TOTAL_ABSENCES]
    assert result.summary_parameters["days"] == 400
    assert result.summary_parameters["provisional_days"] == 460
    assert result.conclusion == Conclusion.REQUIRES_JUDGEMENT.value
    assert result.limitations[0].code == "UNCONFIRMED_RECORDS_AFFECT_CONCLUSION"
    assert result.limitations[0].severity.value == "REVIEW_REQUIRED"


def test_sensitivity_is_capped_at_incomplete() -> None:
    # Trusted 70 in the final year (SUPPORTED); an ESTIMATED 60-day trip pushes provisional to
    # 130 (PROFESSIONAL_REVIEW_RECOMMENDED), which is capped to INCOMPLETE — never asserted
    # as a professional-review conclusion off unconfirmed data.
    result = _evaluate(
        _trip(date(2026, 6, 1), 70, trusted=True),
        _trip(date(2026, 9, 1), 60, trusted=False),
    )[KEY_FINAL_YEAR_ABSENCES]
    assert result.summary_parameters["provisional_days"] == 130
    assert result.conclusion == Conclusion.INCOMPLETE.value
    # Capped: the summary code is the sensitivity-specific one, not the provisional failure
    # band's code — an INCOMPLETE conclusion must not carry an "...EXCEEDED" headline.
    assert result.summary_code == "FINAL_YEAR_UNCONFIRMED_REVIEW"
    assert result.limitations[0].code == "UNCONFIRMED_RECORDS_AFFECT_CONCLUSION"


def test_input_links_cover_the_application_date_and_every_trip() -> None:
    trips = (_trip(date(2023, 1, 1), 30), _trip(date(2024, 1, 1), 20, trusted=False))
    result = _evaluate(*trips)[KEY_TOTAL_ABSENCES]
    kinds = sorted(link.input_kind.value for link in result.input_links)
    assert kinds == ["APPLICATION_DATE_VERSION", "TRAVEL_RECORD_VERSION", "TRAVEL_RECORD_VERSION"]


@given(
    st.lists(st.integers(min_value=0, max_value=200), min_size=0, max_size=5),
    st.lists(st.integers(min_value=0, max_value=200), min_size=0, max_size=5),
)
@pytest.mark.property
def test_provisional_records_never_upgrade_the_conclusion(
    trusted_days: list[int], uncertain_days: list[int]
) -> None:
    # Space trips out so they do not overlap, keeping the arithmetic simple.
    def _spread(days_list: list[int], start: date, trusted: bool) -> list[TripInput]:
        trips, cursor = [], start
        for days in days_list:
            trips.append(_trip(cursor, days, trusted=trusted))
            cursor = cursor + timedelta(days=days + 30)
        return trips

    trusted_trips = _spread(trusted_days, date(2022, 6, 1), True)
    uncertain_trips = _spread(uncertain_days, date(2025, 1, 1), False)

    trusted_only = _evaluate(*trusted_trips)[KEY_TOTAL_ABSENCES]
    with_uncertain = _evaluate(*trusted_trips, *uncertain_trips)[KEY_TOTAL_ABSENCES]

    # The trusted total is unchanged, and adding unconfirmed records only ever makes the
    # conclusion the same or more severe — never less (RULES_SPEC §6.2, §10).
    trusted_total = trusted_only.summary_parameters["days"]
    provisional_total = with_uncertain.summary_parameters["provisional_days"]
    assert isinstance(trusted_total, int)
    assert isinstance(provisional_total, int)
    assert with_uncertain.summary_parameters["days"] == trusted_total
    assert trusted_total <= provisional_total  # RULES_SPEC §10: trusted <= provisional, always
    assert severity(Conclusion(with_uncertain.conclusion)) >= severity(
        band_total_absences(trusted_total).conclusion
    )
