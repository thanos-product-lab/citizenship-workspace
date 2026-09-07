"""Detecting that a confirmed document date disagrees with the trip the user recorded.

The comparison itself is a pure function over primitives, so most of this file needs no
database. The one thing that does is the half most easily lost: RULES_SPEC §6.1 excludes a
`CONFLICTING` trip from the **trusted total**, and a conflict that only changed the
consistency verdict would leave a figure built from a disputed date while telling the user
the date is disputed.
"""

import uuid
from datetime import date

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from app.assessments.conflicts import (
    ConfirmedDocumentDate,
    DateConflict,
    RecordedTrip,
    conflicted_record_ids,
    detect,
)

TRIP = uuid.uuid4()
OTHER_TRIP = uuid.uuid4()
DOCUMENT = uuid.uuid4()
FACT = uuid.uuid4()


def _trip(record_id: uuid.UUID = TRIP, *, returns: str = "2026-05-10") -> RecordedTrip:
    return RecordedTrip(
        travel_record_id=record_id,
        departure_date=date(2026, 5, 4),
        return_date=date.fromisoformat(returns),
    )


def _documented(
    value: str = "2026-05-11",
    *,
    claim_type: str = "travel.return_date",
    item: uuid.UUID = DOCUMENT,
) -> ConfirmedDocumentDate:
    return ConfirmedDocumentDate(
        fact_version_id=FACT,
        evidence_item_id=item,
        claim_type=claim_type,
        value=date.fromisoformat(value),
    )


def test_a_document_attached_to_the_trip_it_disagrees_with_is_a_conflict() -> None:
    """The canonical demo case: the booking says 11 May, the record says 10 May."""
    conflicts = detect(
        trips=[_trip()],
        documented=[_documented()],
        attachments=[(DOCUMENT, TRIP)],
    )

    assert conflicts == [
        DateConflict(
            travel_record_id=TRIP,
            field="return_date",
            recorded=date(2026, 5, 10),
            documented=date(2026, 5, 11),
            fact_version_id=FACT,
            evidence_item_id=DOCUMENT,
        )
    ]


def test_a_document_attached_to_nothing_conflicts_with_nothing() -> None:
    """**Mutation-table row 16.** The link is what gives the comparison its authority.

    Two dates only conflict if something says they describe the same trip, and the only
    thing entitled to say so is the user attaching the document (Domain §11.9). Comparing
    against every trip instead would have a booking the user has not filed silently arguing
    with a trip it may have nothing to do with — and on a case with a dozen trips, one
    unfiled booking would produce a dozen conflicts.
    """
    assert detect(trips=[_trip()], documented=[_documented()], attachments=[]) == []


def test_a_document_conflicts_only_with_the_trip_it_is_attached_to() -> None:
    """The other half of row 16: a case with two trips and a document filed against one."""
    conflicts = detect(
        trips=[_trip(TRIP), _trip(OTHER_TRIP, returns="2026-05-11")],
        documented=[_documented()],
        attachments=[(DOCUMENT, TRIP)],
    )

    assert [c.travel_record_id for c in conflicts] == [TRIP]


def test_agreement_is_not_a_conflict() -> None:
    """RFC §16 calls this a corroborating claim. It creates no conflict, and §41.5 decided
    it creates no automatic provenance either — so the honest output is nothing at all."""
    assert (
        detect(
            trips=[_trip(returns="2026-05-11")],
            documented=[_documented("2026-05-11")],
            attachments=[(DOCUMENT, TRIP)],
        )
        == []
    )


def test_a_fact_that_is_not_a_travel_date_is_ignored() -> None:
    """`immigration.status_granted_on` is a confirmed fact too, and it has nothing here to
    disagree with. Silently ignoring it is right: this function's question is about trips."""
    assert (
        detect(
            trips=[_trip()],
            documented=[_documented(claim_type="immigration.status_granted_on")],
            attachments=[(DOCUMENT, TRIP)],
        )
        == []
    )


def test_a_document_attached_to_a_removed_trip_conflicts_with_nothing() -> None:
    """A removed trip is a tombstone. It cannot be in conflict, and a link to it survives
    removal by design (`withdraw_links_for_travel_record` sets availability, not deletion)."""
    assert detect(trips=[], documented=[_documented()], attachments=[(DOCUMENT, TRIP)]) == []


def test_both_dates_of_one_journey_can_conflict_independently() -> None:
    conflicts = detect(
        trips=[_trip()],
        documented=[
            _documented("2026-05-05", claim_type="travel.departure_date"),
            _documented("2026-05-11"),
        ],
        attachments=[(DOCUMENT, TRIP)],
    )

    assert [c.field for c in conflicts] == ["departure_date", "return_date"]


def test_the_order_is_stable_across_runs() -> None:
    """One `AssessmentInputLink` is written per conflict, so an unordered result would make
    provenance rows differ between two runs over identical inputs — and a diff of two
    results would then show a change nobody made."""
    trips = [_trip(TRIP), _trip(OTHER_TRIP)]
    documented = [_documented("2026-05-05", claim_type="travel.departure_date"), _documented()]
    attachments = [(DOCUMENT, OTHER_TRIP), (DOCUMENT, TRIP)]

    first = detect(trips=trips, documented=documented, attachments=attachments)
    second = detect(
        trips=list(reversed(trips)),
        documented=list(reversed(documented)),
        attachments=list(reversed(attachments)),
    )

    assert first == second


@settings(max_examples=200, deadline=None)
@given(
    recorded=st.dates(min_value=date(2020, 1, 1), max_value=date(2030, 1, 1)),
    documented=st.dates(min_value=date(2020, 1, 1), max_value=date(2030, 1, 1)),
)
def test_a_conflict_is_exactly_a_disagreement(recorded: date, documented: date) -> None:
    """The whole rule, over every pair of dates: conflict if and only if they differ.

    Worth stating as a property rather than as examples, because the failure it rules out
    is a comparison that is *nearly* right — off by a day at a month boundary, or
    order-dependent, or true only for dates in the past.
    """
    conflicts = detect(
        trips=[
            RecordedTrip(
                travel_record_id=TRIP,
                departure_date=date(2020, 1, 1),
                return_date=recorded,
            )
        ],
        documented=[
            ConfirmedDocumentDate(
                fact_version_id=FACT,
                evidence_item_id=DOCUMENT,
                claim_type="travel.return_date",
                value=documented,
            )
        ],
        attachments=[(DOCUMENT, TRIP)],
    )

    assert bool(conflicts) is (recorded != documented)


def test_conflicted_record_ids_is_the_set_a_caller_must_hold_back() -> None:
    """Separate from `detect` because it is used twice and both uses are load-bearing:
    §6.1 excludes these from the trusted total, §7.8 turns them INCONSISTENT."""
    conflicts = detect(
        trips=[_trip(TRIP), _trip(OTHER_TRIP)],
        documented=[_documented()],
        attachments=[(DOCUMENT, TRIP), (DOCUMENT, OTHER_TRIP)],
    )

    assert conflicted_record_ids(conflicts) == frozenset({TRIP, OTHER_TRIP})
    assert conflicted_record_ids([]) == frozenset()


@pytest.mark.parametrize("scope_key", ["", "not-a-uuid", "::", "abc:0"])
def test_a_scope_key_without_an_evidence_item_is_skipped(scope_key: str) -> None:
    """A case-level fact (`""`) has no document behind it, and a malformed key is a bug
    somewhere else. Neither should take a whole recalculation down."""
    from app.assessments.service import _evidence_item_of

    assert _evidence_item_of(scope_key) is None


def test_a_journey_scoped_key_yields_its_evidence_item() -> None:
    from app.assessments.service import _evidence_item_of

    item = uuid.uuid4()
    assert _evidence_item_of(f"{item}:1") == item
