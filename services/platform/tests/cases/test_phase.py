"""The case-phase derivation ladder (Domain §7.5, ADR-0009), as a table.

`derive_phase` is pure, so these are plain unit tests over synthetic states — including
the two phases an M4 case cannot actually reach, which are covered here precisely because
no integration test can produce them.
"""

import pytest

from app.cases.domain import CasePhase, LifecycleStatus
from app.cases.phase import RequirementState, derive_phase
from app.requirements.domain import Conclusion, Currency

CATALOGUE = 15


def _state(conclusion: Conclusion, currency: Currency = Currency.CURRENT) -> RequirementState:
    return RequirementState(conclusion=conclusion.value, currency=currency.value)


def _all_supported(n: int = CATALOGUE) -> list[RequirementState]:
    return [_state(Conclusion.SUPPORTED) for _ in range(n)]


def _derive(
    states: list[RequirementState],
    *,
    lifecycle: LifecycleStatus = LifecycleStatus.ACTIVE,
    catalogue_size: int = CATALOGUE,
) -> CasePhase:
    return derive_phase(lifecycle_status=lifecycle, states=states, catalogue_size=catalogue_size)


# --- lifecycle gate ---------------------------------------------------------


@pytest.mark.parametrize(
    "lifecycle",
    [LifecycleStatus.DRAFT, LifecycleStatus.DELETION_PENDING, LifecycleStatus.DELETED],
)
def test_a_case_that_is_not_active_is_always_setting_up(lifecycle: LifecycleStatus) -> None:
    """Even with a full set of supported results, a non-ACTIVE case reports SETTING_UP:
    the phase describes progress through an active case and is not meaningful otherwise."""
    assert _derive(_all_supported(), lifecycle=lifecycle) is CasePhase.SETTING_UP


def test_an_active_case_with_no_results_is_setting_up() -> None:
    assert _derive([]) is CasePhase.SETTING_UP


# --- the ladder -------------------------------------------------------------


def test_all_requirements_concluded_and_clean_is_nearly_prepared() -> None:
    """Unreachable in an M4 case — six requirements have no evaluator — so this is the
    only place the branch is exercised."""
    assert _derive(_all_supported()) is CasePhase.NEARLY_PREPARED


def test_unassessed_requirements_leave_the_case_building() -> None:
    assert _derive(_all_supported(9)) is CasePhase.BUILDING_CASE


def test_a_stored_not_yet_assessed_result_does_not_count_as_concluded() -> None:
    """A placeholder result (e.g. the adult rule before a date of birth exists) must not
    push a case towards "prepared" — nothing was decided."""
    states = [*_all_supported(14), _state(Conclusion.NOT_YET_ASSESSED)]
    assert _derive(states) is CasePhase.BUILDING_CASE


@pytest.mark.parametrize(
    "conclusion",
    [
        Conclusion.REQUIRES_JUDGEMENT,
        Conclusion.INCOMPLETE,
        Conclusion.INCONSISTENT,
        Conclusion.PROFESSIONAL_REVIEW_RECOMMENDED,
        Conclusion.NOT_CURRENTLY_SATISFIED,
    ],
)
def test_a_conclusion_needing_attention_moves_the_case_to_resolving_issues(
    conclusion: Conclusion,
) -> None:
    states = [*_all_supported(14), _state(conclusion)]
    assert _derive(states) is CasePhase.RESOLVING_ISSUES


@pytest.mark.parametrize("conclusion", [Conclusion.SUPPORTED, Conclusion.NEAR_THRESHOLD])
def test_supported_and_near_threshold_do_not_move_the_case_to_resolving_issues(
    conclusion: Conclusion,
) -> None:
    """NEAR_THRESHOLD is a caution, not a task. It is rendered distinctly from SUPPORTED
    on the requirement itself, but it is not something the user can act on, so it must not
    make the whole case read as having issues."""
    states = [*_all_supported(14), _state(conclusion)]
    assert _derive(states) is CasePhase.NEARLY_PREPARED


def test_a_stale_result_moves_the_case_to_resolving_issues() -> None:
    """Currency alone is enough (ADR-0001): a SUPPORTED conclusion whose inputs have since
    changed is still something the user needs to deal with, and the phase must not report
    a clean case on the strength of arithmetic that is out of date."""
    states = [*_all_supported(14), _state(Conclusion.SUPPORTED, Currency.STALE)]
    assert _derive(states) is CasePhase.RESOLVING_ISSUES


def test_problems_take_precedence_over_incompleteness() -> None:
    """A case with both an unmet requirement and unassessed ones is resolving issues, not
    building: the problem is the more useful thing to tell the user."""
    states = [_state(Conclusion.SUPPORTED), _state(Conclusion.NOT_CURRENTLY_SATISFIED)]
    assert _derive(states) is CasePhase.RESOLVING_ISSUES


def test_an_unrecognised_conclusion_is_treated_as_needing_attention() -> None:
    """Fail towards visible uncertainty (CLAUDE.md §2.7): a conclusion this code does not
    know must never be silently counted as fine."""
    states = [*_all_supported(14), RequirementState("SOMETHING_NEW", Currency.CURRENT.value)]
    assert _derive(states) is CasePhase.RESOLVING_ISSUES


def test_final_review_is_not_reachable() -> None:
    """FINAL_REVIEW depends on evidence and issue state that does not exist until M6/M7.
    The ladder must never produce it, in any combination of states, at M4."""
    combinations = [
        [],
        _all_supported(),
        _all_supported(9),
        [*_all_supported(14), _state(Conclusion.NOT_CURRENTLY_SATISFIED)],
        [*_all_supported(14), _state(Conclusion.SUPPORTED, Currency.STALE)],
    ]
    for states in combinations:
        for lifecycle in LifecycleStatus:
            assert _derive(states, lifecycle=lifecycle) is not CasePhase.FINAL_REVIEW


# --- the canonical case -----------------------------------------------------


def test_the_canonical_case_reads_as_resolving_issues() -> None:
    """The M3B oracle: nine assessed requirements, six with no result, and physical
    presence NOT_CURRENTLY_SATISFIED. The honest phase is RESOLVING_ISSUES — the stored
    column would have said SETTING_UP."""
    states = [
        _state(Conclusion.SUPPORTED),  # route.adult_applicant
        _state(Conclusion.SUPPORTED),  # route.supported_status
        _state(Conclusion.SUPPORTED),  # route.standard_section_6_1
        _state(Conclusion.SUPPORTED),  # status.holding_period
        _state(Conclusion.SUPPORTED),  # residence.qualifying_period
        _state(Conclusion.NOT_CURRENTLY_SATISFIED),  # residence.physical_presence_start_date
        _state(Conclusion.NEAR_THRESHOLD),  # residence.total_absences
        _state(Conclusion.SUPPORTED),  # residence.final_year_absences
        _state(Conclusion.SUPPORTED),  # residence.travel_consistency
    ]
    assert _derive(states) is CasePhase.RESOLVING_ISSUES
