"""Group summarisation, as a table.

A group summary compresses several results into one tile, and the tests that matter are
the ones pinning what the compression must not lose: the weakest member's currency, and
the fact that some members have not been assessed at all.
"""

import pytest

from app.assessments.groups import GroupMember, GroupSummary, summarise_group, summarise_groups
from app.requirements.domain import Conclusion, Currency


def _counts(summary: GroupSummary) -> dict[str, int]:
    """The ordered count list as a mapping, for assertions that do not care about order."""
    return {c.conclusion: c.count for c in summary.conclusion_counts}


ORDER = iter(range(1, 1000))


def _member(
    conclusion: Conclusion,
    currency: Currency | None = Currency.CURRENT,
    *,
    group: str = "RESIDENCE",
) -> GroupMember:
    return GroupMember(
        requirement_key=f"{group.lower()}.r{next(ORDER)}",
        group_key=group,
        title="A requirement",
        conclusion=conclusion.value,
        currency=currency.value if currency else None,
        display_order=next(ORDER),
    )


# --- currency: inherit-weakest (ADR-0010) -----------------------------------


def test_one_stale_member_makes_the_group_stale() -> None:
    """The whole point. A tile reading "4 supported" while one member is stale would
    present superseded arithmetic as current — ADR-0001's failure at the aggregate level."""
    summary = summarise_group(
        "RESIDENCE",
        [
            _member(Conclusion.SUPPORTED),
            _member(Conclusion.SUPPORTED),
            _member(Conclusion.SUPPORTED, Currency.STALE),
        ],
    )
    assert summary.currency == Currency.STALE.value
    assert summary.stale == 1
    # And the conclusions are untouched: staleness never rewrites what was concluded.
    assert _counts(summary) == {Conclusion.SUPPORTED.value: 3}


def test_a_group_with_every_member_current_is_current() -> None:
    summary = summarise_group("RESIDENCE", [_member(Conclusion.SUPPORTED) for _ in range(3)])
    assert summary.currency == Currency.CURRENT.value
    assert summary.stale == 0


def test_provisional_is_weaker_than_current_but_stronger_than_stale() -> None:
    provisional = summarise_group(
        "RESIDENCE",
        [_member(Conclusion.SUPPORTED), _member(Conclusion.SUPPORTED, Currency.PROVISIONAL)],
    )
    assert provisional.currency == Currency.PROVISIONAL.value

    both = summarise_group(
        "RESIDENCE",
        [
            _member(Conclusion.SUPPORTED, Currency.PROVISIONAL),
            _member(Conclusion.SUPPORTED, Currency.STALE),
        ],
    )
    assert both.currency == Currency.STALE.value


def test_a_group_with_no_results_has_no_currency() -> None:
    """Null, not CURRENT. Reporting a group of unassessed requirements as current would
    claim they had been assessed and found up to date."""
    summary = summarise_group(
        "REFEREES", [_member(Conclusion.NOT_YET_ASSESSED, None) for _ in range(2)]
    )
    assert summary.currency is None
    assert summary.not_yet_assessed == 2


# --- the unassessed are never absorbed --------------------------------------


def test_not_yet_assessed_is_counted_apart_from_conclusions() -> None:
    summary = summarise_group(
        "KNOWLEDGE_AND_LANGUAGE",
        [_member(Conclusion.SUPPORTED), _member(Conclusion.NOT_YET_ASSESSED, None)],
    )
    assert _counts(summary) == {Conclusion.SUPPORTED.value: 1}
    assert Conclusion.NOT_YET_ASSESSED.value not in _counts(summary)
    assert summary.not_yet_assessed == 1
    assert summary.total == 2


def test_a_group_containing_an_unassessed_requirement_is_not_fully_concluded() -> None:
    """The guard against a group reading as complete on the strength of requirements
    nothing has decided."""
    summary = summarise_group(
        "REFEREES",
        [_member(Conclusion.SUPPORTED), _member(Conclusion.NOT_YET_ASSESSED, None)],
    )
    assert summary.is_fully_concluded is False


def test_a_stored_not_yet_assessed_result_still_counts_as_unassessed() -> None:
    """The route rules persist NOT_YET_ASSESSED placeholders. Having a row does not make
    it a conclusion."""
    summary = summarise_group(
        "ROUTE_AND_STATUS", [_member(Conclusion.NOT_YET_ASSESSED, Currency.CURRENT)]
    )
    assert summary.not_yet_assessed == 1
    assert _counts(summary) == {}
    assert summary.is_fully_concluded is False


def test_a_fully_concluded_group_says_so() -> None:
    summary = summarise_group("RESIDENCE", [_member(Conclusion.SUPPORTED) for _ in range(3)])
    assert summary.is_fully_concluded is True


def test_an_empty_group_is_not_fully_concluded() -> None:
    """Vacuous truth is the wrong answer here: a group with no members has not been
    completed, it is unpopulated."""
    assert summarise_group("RESIDENCE", []).is_fully_concluded is False


# --- attention ---------------------------------------------------------------


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
def test_severe_conclusions_count_as_needing_attention(conclusion: Conclusion) -> None:
    summary = summarise_group("RESIDENCE", [_member(Conclusion.SUPPORTED), _member(conclusion)])
    assert summary.needs_attention == 1


@pytest.mark.parametrize("conclusion", [Conclusion.SUPPORTED, Conclusion.NEAR_THRESHOLD])
def test_supported_and_near_threshold_do_not_need_attention(conclusion: Conclusion) -> None:
    """NEAR_THRESHOLD is a caution, not a task — the same boundary the case phase uses."""
    assert summarise_group("RESIDENCE", [_member(conclusion)]).needs_attention == 0


def test_an_unrecognised_conclusion_counts_as_needing_attention() -> None:
    member = GroupMember(
        requirement_key="residence.x",
        group_key="RESIDENCE",
        title="A requirement",
        conclusion="SOMETHING_NEW",
        currency=Currency.CURRENT.value,
        display_order=1,
    )
    assert summarise_group("RESIDENCE", [member]).needs_attention == 1


# --- grouping ----------------------------------------------------------------


def test_groups_come_out_in_catalogue_display_order() -> None:
    members = [
        GroupMember("b.1", "SECOND", "B", Conclusion.SUPPORTED.value, "CURRENT", 10),
        GroupMember("a.1", "FIRST", "A", Conclusion.SUPPORTED.value, "CURRENT", 1),
        GroupMember("b.2", "SECOND", "B2", Conclusion.SUPPORTED.value, "CURRENT", 11),
    ]
    summaries = summarise_groups(members)
    assert [s.group_key for s in summaries] == ["FIRST", "SECOND"]
    assert [s.total for s in summaries] == [1, 2]


def test_the_canonical_case_group_shape() -> None:
    """The M3B oracle as groups: residence holds five members, one not currently satisfied
    and one near threshold, all current; referees holds two with no result at all."""
    residence = summarise_group(
        "RESIDENCE",
        [
            _member(Conclusion.SUPPORTED),
            _member(Conclusion.NOT_CURRENTLY_SATISFIED),
            _member(Conclusion.NEAR_THRESHOLD),
            _member(Conclusion.SUPPORTED),
            _member(Conclusion.SUPPORTED),
        ],
    )
    assert residence.total == 5
    assert residence.needs_attention == 1
    assert residence.not_yet_assessed == 0
    assert residence.currency == Currency.CURRENT.value

    referees = summarise_group(
        "REFEREES", [_member(Conclusion.NOT_YET_ASSESSED, None) for _ in range(2)]
    )
    assert referees.not_yet_assessed == 2
    assert _counts(referees) == {}
    assert referees.currency is None


# --- ordering and unknown currency (slice-3 review) --------------------------


def test_counts_are_ordered_most_severe_first() -> None:
    """Severity owns the ordering (RULES_SPEC §7.13), not magnitude. Sorting by count would
    put the most reassuring state first on the screen a user most often reads only."""
    summary = summarise_group(
        "RESIDENCE",
        [
            *[_member(Conclusion.SUPPORTED) for _ in range(7)],
            _member(Conclusion.NOT_CURRENTLY_SATISFIED),
            _member(Conclusion.NEAR_THRESHOLD),
        ],
    )
    assert [c.conclusion for c in summary.conclusion_counts] == [
        Conclusion.NOT_CURRENTLY_SATISFIED.value,
        Conclusion.NEAR_THRESHOLD.value,
        Conclusion.SUPPORTED.value,
    ]


def test_an_unrecognised_currency_is_treated_as_weaker_than_any_known_one() -> None:
    """Skipping it would let a group whose only non-current member carries an unreadable
    currency report as CURRENT — describing itself as up to date on the strength of a value
    the code could not interpret. That is the strongest-member reading ADR-0010 rejects."""
    summary = summarise_group(
        "RESIDENCE",
        [
            _member(Conclusion.SUPPORTED),
            GroupMember(
                requirement_key="residence.x",
                group_key="RESIDENCE",
                title="A requirement",
                conclusion=Conclusion.SUPPORTED.value,
                currency="SOMETHING_NEW",
                display_order=99,
            ),
        ],
    )
    assert summary.currency == "SOMETHING_NEW"
    assert summary.currency != Currency.CURRENT.value
