"""Priority-action selection.

The cap at three is a promise about attention, so the tests pin two things: the order is
deterministic and explainable, and the cap never silently hides work or merges two
different asks into one.
"""

from typing import Any

from app.assessments.priority import CandidateAction, select_priority_actions
from app.requirements.domain import Conclusion


def _action(
    *,
    code: str = "SELECT_APPLICATION_DATE",
    parameters: dict[str, Any] | None = None,
    conclusion: Conclusion = Conclusion.INCOMPLETE,
    priority: int = 1,
    blocking: bool = False,
    display_order: int = 1,
    key: str = "residence.total_absences",
) -> CandidateAction:
    return CandidateAction(
        requirement_key=key,
        requirement_title="A requirement",
        conclusion=conclusion.value,
        display_order=display_order,
        code=code,
        parameters=parameters or {},
        priority=priority,
        blocking=blocking,
    )


def test_blocking_actions_come_first() -> None:
    result = select_priority_actions(
        [
            _action(code="A", blocking=False, conclusion=Conclusion.NOT_CURRENTLY_SATISFIED),
            _action(code="B", blocking=True, conclusion=Conclusion.INCOMPLETE),
        ]
    )
    assert [a.code for a in result.shown] == ["B", "A"]


def test_a_more_severe_conclusion_outranks_a_less_severe_one() -> None:
    result = select_priority_actions(
        [
            _action(code="NEAR", conclusion=Conclusion.NEAR_THRESHOLD),
            _action(code="UNMET", conclusion=Conclusion.NOT_CURRENTLY_SATISFIED),
            _action(code="INCOMPLETE", conclusion=Conclusion.INCOMPLETE),
        ]
    )
    assert [a.code for a in result.shown] == ["UNMET", "INCOMPLETE", "NEAR"]


def test_ties_resolve_by_catalogue_display_order() -> None:
    result = select_priority_actions(
        [
            _action(code="LATER", display_order=9),
            _action(code="EARLIER", display_order=2),
        ]
    )
    assert [a.code for a in result.shown] == ["EARLIER", "LATER"]


def test_no_more_than_three_are_shown_and_the_rest_are_counted() -> None:
    """A cap that silently hides work misleads. The count of what was left out travels
    with the list so the UI can say so."""
    result = select_priority_actions([_action(code=f"A{i}", display_order=i) for i in range(6)])
    assert len(result.shown) == 3
    assert result.total == 6
    assert result.hidden == 3


def test_two_application_date_actions_proposing_different_dates_both_survive() -> None:
    """The §5.7 case. Physical presence may propose 25 April while the holding period
    proposes its own earliest date. Merging them would invent a date neither rule produced;
    dropping one would hide a real constraint."""
    result = select_priority_actions(
        [
            _action(
                parameters={"resolving_application_date": "2027-04-25"},
                conclusion=Conclusion.NOT_CURRENTLY_SATISFIED,
                blocking=True,
                key="residence.physical_presence_start_date",
                display_order=6,
            ),
            _action(
                parameters={"earliest_application_date": "2026-03-01"},
                conclusion=Conclusion.NOT_CURRENTLY_SATISFIED,
                blocking=True,
                key="status.holding_period",
                display_order=4,
            ),
        ]
    )
    assert result.total == 2
    assert len(result.shown) == 2
    # Both dates reach the user, and the catalogue order decides which reads first.
    dates = [a.parameters for a in result.shown]
    assert {"earliest_application_date": "2026-03-01"} in dates
    assert {"resolving_application_date": "2027-04-25"} in dates


def test_genuinely_identical_actions_are_deduplicated() -> None:
    same = {"resolving_application_date": "2027-04-25"}
    result = select_priority_actions(
        [
            _action(parameters=dict(same), key="residence.physical_presence_start_date"),
            _action(parameters=dict(same), key="residence.total_absences"),
        ]
    )
    assert result.total == 1
    assert result.hidden == 0


def test_no_actions_yields_an_empty_selection() -> None:
    result = select_priority_actions([])
    assert result.shown == []
    assert result.total == 0
    assert result.hidden == 0


def test_an_unrecognised_conclusion_sorts_as_most_urgent() -> None:
    """Fail towards visibility: an action this build cannot rank should surface for a human
    rather than sink below the cap."""
    result = select_priority_actions(
        [
            _action(code="KNOWN", conclusion=Conclusion.NOT_CURRENTLY_SATISFIED),
            CandidateAction(
                requirement_key="x.y",
                requirement_title="X",
                conclusion="SOMETHING_NEW",
                display_order=1,
                code="UNKNOWN",
                parameters={},
                priority=1,
                blocking=False,
            ),
        ]
    )
    assert result.shown[0].code == "UNKNOWN"


def test_the_canonical_case_surfaces_the_presence_date_action() -> None:
    """The M3B oracle: physical presence is the only requirement emitting a next action,
    and it is blocking."""
    result = select_priority_actions(
        [
            _action(
                parameters={"resolving_application_date": "2027-04-25"},
                conclusion=Conclusion.NOT_CURRENTLY_SATISFIED,
                blocking=True,
                key="residence.physical_presence_start_date",
                display_order=6,
            )
        ]
    )
    assert len(result.shown) == 1
    assert result.hidden == 0
    assert result.shown[0].parameters == {"resolving_application_date": "2027-04-25"}
