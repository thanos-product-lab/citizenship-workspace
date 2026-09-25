"""The case's next steps (ADR-0034).

Pure rules over a snapshot, so each condition and the order between them is pinned here
without a database. The properties below are the promises the panel makes: never more than
three steps, never an empty answer, never "nothing left" beside something that is left, and
never a tally of progress (CLAUDE.md §2.6).
"""

import re
from dataclasses import replace
from datetime import date

import pytest
from hypothesis import given
from hypothesis import strategies as st

from app.assessments.next_steps import (
    MAX_STEPS,
    Destination,
    DoneCode,
    NextStepInputs,
    StepCode,
    derive_next_steps,
)
from app.requirements.messages import (
    render_next_step_body,
    render_next_step_done,
    render_next_step_title,
)

NEW_CASE = NextStepInputs(
    application_date=None,
    trip_count=0,
    documents_awaiting_review=0,
    assessed=False,
    last_assessed_on=None,
    stale_count=0,
    priority_action_count=0,
    issue_actions_excluding_recheck=0,
    trips_without_document=0,
)

ASSESSED = replace(
    NEW_CASE,
    application_date=date(2027, 4, 15),
    trip_count=5,
    assessed=True,
    last_assessed_on=date(2026, 9, 23),
)


def _codes(inputs: NextStepInputs) -> list[StepCode]:
    return [step.code for step in derive_next_steps(inputs).steps]


def test_a_new_case_starts_with_the_date_then_the_trips() -> None:
    assert _codes(NEW_CASE) == [StepCode.SET_APPLICATION_DATE, StepCode.ADD_TRIPS]


def test_with_a_date_set_the_trips_come_before_the_first_assessment() -> None:
    inputs = replace(NEW_CASE, application_date=date(2027, 4, 15))
    assert _codes(inputs) == [StepCode.ADD_TRIPS, StepCode.RUN_ASSESSMENT]


def test_with_date_and_trips_the_first_assessment_is_primary() -> None:
    inputs = replace(NEW_CASE, application_date=date(2027, 4, 15), trip_count=5)
    assert _codes(inputs) == [StepCode.RUN_ASSESSMENT]


def test_no_trips_is_not_asked_again_after_an_assessment() -> None:
    """Zero trips after an assessment is an answer the totals already reflect. Asking again
    would nag someone who never left the UK, forever."""
    assert StepCode.ADD_TRIPS not in _codes(replace(ASSESSED, trip_count=0))


def test_documents_awaiting_review_come_before_the_assessment() -> None:
    """A document's proposals count for nothing until reviewed, so assessing first would
    measure a case the user is about to change."""
    inputs = replace(
        NEW_CASE, application_date=date(2027, 4, 15), trip_count=2, documents_awaiting_review=2
    )
    steps = derive_next_steps(inputs).steps
    assert [s.code for s in steps] == [StepCode.REVIEW_DOCUMENTS, StepCode.RUN_ASSESSMENT]
    assert steps[0].parameters == {"count": 2}
    assert steps[0].destination is Destination.EVIDENCE


def test_a_stale_assessment_asks_for_an_update() -> None:
    steps = derive_next_steps(replace(ASSESSED, stale_count=8)).steps
    assert steps[0].code is StepCode.UPDATE_ASSESSMENT
    assert steps[0].parameters == {"count": 8}


def test_run_assessment_is_never_offered_once_assessed() -> None:
    assert StepCode.RUN_ASSESSMENT not in _codes(replace(ASSESSED, stale_count=3))


def test_update_comes_before_the_requirements_own_asks_and_the_issues() -> None:
    inputs = replace(
        ASSESSED, stale_count=1, priority_action_count=2, issue_actions_excluding_recheck=1
    )
    assert _codes(inputs) == [
        StepCode.UPDATE_ASSESSMENT,
        StepCode.RESOLVE_REQUIREMENTS,
        StepCode.OPEN_ISSUES,
    ]


def test_the_cap_drops_the_last_steps_never_the_first() -> None:
    inputs = replace(
        ASSESSED,
        documents_awaiting_review=1,
        stale_count=1,
        priority_action_count=1,
        issue_actions_excluding_recheck=1,
        trips_without_document=1,
    )
    assert _codes(inputs) == [
        StepCode.REVIEW_DOCUMENTS,
        StepCode.UPDATE_ASSESSMENT,
        StepCode.RESOLVE_REQUIREMENTS,
    ]


def test_trip_evidence_is_the_one_optional_step() -> None:
    steps = derive_next_steps(replace(ASSESSED, trips_without_document=3)).steps
    assert [(s.code, s.optional) for s in steps] == [
        (StepCode.NOTHING_LEFT, False),
        (StepCode.ATTACH_TRIP_EVIDENCE, True),
    ]


def test_nothing_left_when_nothing_applies() -> None:
    steps = derive_next_steps(ASSESSED).steps
    assert [s.code for s in steps] == [StepCode.NOTHING_LEFT]
    assert steps[0].destination is Destination.REQUIREMENTS


def test_done_items_say_what_the_case_holds() -> None:
    done = derive_next_steps(ASSESSED).done
    assert [(d.code, d.parameters) for d in done] == [
        (DoneCode.DATE_SET, {"date": "2027-04-15"}),
        (DoneCode.TRIPS_RECORDED, {"count": 5}),
        (DoneCode.ASSESSED, {"date": "2026-09-23"}),
    ]


def test_a_new_case_has_nothing_done() -> None:
    assert derive_next_steps(NEW_CASE).done == []


def test_nothing_left_never_claims_readiness() -> None:
    """The one place a finish line could creep in (CLAUDE.md §2.7)."""
    text = f"{render_next_step_title('NOTHING_LEFT')} {render_next_step_body('NOTHING_LEFT')}"
    for word in ("ready", "complete", "done", "eligible", "all set"):
        assert word not in text.lower()


def test_counts_are_pluralised() -> None:
    assert render_next_step_title("REVIEW_DOCUMENTS", {"count": 1}) == (
        "Review 1 document waiting for you"
    )
    assert render_next_step_title("REVIEW_DOCUMENTS", {"count": 3}) == (
        "Review 3 documents waiting for you"
    )
    assert render_next_step_done("TRIPS_RECORDED", {"count": 1}) == "1 trip recorded"
    assert render_next_step_body("UPDATE_ASSESSMENT", {"count": 1}) == (
        "One result is out of date because something it depends on changed."
    )


_inputs = st.builds(
    NextStepInputs,
    application_date=st.none() | st.dates(date(2020, 1, 1), date(2035, 12, 31)),
    trip_count=st.integers(0, 40),
    documents_awaiting_review=st.integers(0, 5),
    assessed=st.booleans(),
    last_assessed_on=st.none() | st.dates(date(2024, 1, 1), date(2030, 12, 31)),
    stale_count=st.integers(0, 15),
    priority_action_count=st.integers(0, 6),
    issue_actions_excluding_recheck=st.integers(0, 10),
    trips_without_document=st.integers(0, 40),
)

_TALLY = re.compile(r"%|\b\d+\s+(of|out of)\s+\d+\b", re.IGNORECASE)


@pytest.mark.property
@given(_inputs)
def test_there_is_always_an_answer_and_never_more_than_three(inputs: NextStepInputs) -> None:
    steps = derive_next_steps(inputs).steps
    assert 1 <= len(steps) <= MAX_STEPS
    assert not steps[0].optional, "an optional step is never the primary one"


@pytest.mark.property
@given(_inputs)
def test_nothing_left_never_sits_beside_a_required_step(inputs: NextStepInputs) -> None:
    steps = derive_next_steps(inputs).steps
    if any(s.code is StepCode.NOTHING_LEFT for s in steps):
        assert all(s.optional for s in steps if s.code is not StepCode.NOTHING_LEFT)


@pytest.mark.property
@given(_inputs)
def test_no_step_or_done_item_is_a_tally(inputs: NextStepInputs) -> None:
    """CLAUDE.md §2.6: no percentage and no "2 of 3", anywhere the panel reads from."""
    result = derive_next_steps(inputs)
    texts = [render_next_step_done(d.code, d.parameters) or "" for d in result.done]
    for step in result.steps:
        texts.append(render_next_step_title(step.code, step.parameters) or "")
        texts.append(render_next_step_body(step.code, step.parameters) or "")
    for text in texts:
        assert text and not _TALLY.search(text), text


@pytest.mark.property
@given(_inputs)
def test_the_steps_are_deterministic(inputs: NextStepInputs) -> None:
    assert derive_next_steps(inputs) == derive_next_steps(inputs)
