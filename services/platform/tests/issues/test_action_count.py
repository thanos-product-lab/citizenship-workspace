"""What the Issues count counts (Domain §36.3, ADR-0033).

The badge in the case navigation is the user's answer to "how much is there for me to do".
An INFORMATION note is not something to do, and eight stale conclusions are one thing to
do, because one command clears them. The stored issues are untouched by any of this: the
rule is applied when counting.
"""

from hypothesis import given
from hypothesis import strategies as st

from app.issues.domain import RECHECK_TYPES, IssueSeverity, IssueType, count_actions

STALE = IssueType.STALE_ASSESSMENT.value
FAILED = IssueType.PROCESSING_FAILURE.value
INFO = IssueSeverity.INFORMATION.value
ACTION = IssueSeverity.ACTION_REQUIRED.value
REVIEW = IssueSeverity.REVIEW_REQUIRED.value
BLOCKING = IssueSeverity.BLOCKING.value


def test_an_information_note_is_not_an_action() -> None:
    counts = count_actions([(IssueType.MISSING_EVIDENCE.value, INFO)] * 3)
    assert (counts.actions, counts.awareness) == (0, 3)


def test_every_recheck_together_is_one_action() -> None:
    assert count_actions([(STALE, ACTION)] * 4).actions == 1
    # A failed run is cleared by the same command, so it does not add a second.
    assert count_actions([(STALE, ACTION)] * 4 + [(FAILED, ACTION)]).actions == 1
    assert count_actions([(FAILED, ACTION)]).actions == 1


def test_a_review_item_is_counted() -> None:
    # Near-threshold and overlapping trips are what §2.7 says must not be under-stated.
    assert count_actions([(IssueType.NEAR_THRESHOLD.value, REVIEW)]).actions == 1


def test_the_parts_add_up() -> None:
    counts = count_actions(
        [
            (STALE, ACTION),
            (STALE, ACTION),
            (IssueType.OVERLAPPING_TRAVEL.value, REVIEW),
            (IssueType.CONFLICTING_CLAIMS.value, ACTION),
            (IssueType.UNSUPPORTED_COMPLEXITY.value, BLOCKING),
            (IssueType.MISSING_EVIDENCE.value, INFO),
            (IssueType.DUPLICATE_EVIDENCE.value, INFO),
        ]
    )
    assert (counts.actions, counts.awareness) == (4, 2)


def test_nothing_open_is_nothing_to_do() -> None:
    counts = count_actions([])
    assert (counts.actions, counts.awareness) == (0, 0)


_types = st.sampled_from([t.value for t in IssueType])
_severities = st.sampled_from([s.value for s in IssueSeverity])
_queues = st.lists(st.tuples(_types, _severities), max_size=30)


@given(queue=_queues, note_type=_types.filter(lambda t: t not in RECHECK_TYPES))
def test_adding_a_note_never_changes_the_action_count(queue, note_type) -> None:  # type: ignore[no-untyped-def]
    before = count_actions(queue)
    after = count_actions([*queue, (note_type, INFO)])
    assert after.actions == before.actions
    assert after.awareness == before.awareness + 1


@given(queue=_queues, extra=st.lists(st.sampled_from(sorted(RECHECK_TYPES)), min_size=1))
def test_more_rechecks_never_add_a_second_action(queue, extra) -> None:  # type: ignore[no-untyped-def]
    with_one = [*queue, (STALE, ACTION)]
    with_more = with_one + [(t, ACTION) for t in extra]
    assert count_actions(with_more).actions == count_actions(with_one).actions


@given(queue=_queues)
def test_every_open_issue_is_counted_somewhere_or_folded_into_the_recheck(queue) -> None:  # type: ignore[no-untyped-def]
    counts = count_actions(queue)
    rechecks = sum(1 for t, _ in queue if t in RECHECK_TYPES)
    folded = rechecks - (1 if rechecks else 0)
    assert counts.actions + counts.awareness + folded == len(queue)
