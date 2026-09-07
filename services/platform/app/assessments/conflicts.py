"""When a confirmed document date disagrees with the trip the user recorded.

**Derived, never stored** (EVIDENCE_AND_CLAIM_LIFECYCLE_RFC §42). A conflict is a
relationship between three things that already exist — a confirmed `FactVersion`, an
`EvidenceTravelLink`, and a `TravelRecordVersion` — so it is recomputed wherever it is
needed and has no row of its own. §42.2 records what that gives up.

Three properties this module is shaped to hold, in the order they matter:

**Only confirmed values reach it.** The parameters below are dates and ids. There is no
type here that an `ExtractedClaim` could be passed as, so a pending proposal cannot
influence an assessment through this path — prime directive 1, enforced by the signature
rather than by a check inside the function.

**The link is the authority.** Two dates only conflict if something says they describe the
same trip, and the only thing entitled to say so is the user attaching the document to it
(Domain §11.9). Without an `EvidenceTravelLink` there is no conflict — just a document and
a trip that mention different dates.

**Pure.** No session, no ORM, no clock. The caller reads the rows; this decides what they
mean, which is what makes it testable directly and by Hypothesis.
"""

import uuid
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date

#: The two claim types this compares, and the `TripInput` field each answers.
#:
#: A dict rather than a pair of `if`s so that adding a third travel date is a line here
#: rather than a branch to find. The keys are `ClaimType` values; they are strings because
#: this module takes primitives — importing the enum would drag `app.facts.domain`, and
#: with it `ExtractedClaim`, into a module whose whole claim is that it cannot see one.
TRAVEL_DATE_CLAIM_TYPES: dict[str, str] = {
    "travel.departure_date": "departure_date",
    "travel.return_date": "return_date",
}


@dataclass(frozen=True)
class ConfirmedDocumentDate:
    """One confirmed date a document proposes, and where it came from.

    `fact_version_id` is carried because the result becomes an `AssessmentInputLink`: a
    conclusion that depends on a fact has to say which version of it (directive 5).
    """

    fact_version_id: uuid.UUID
    evidence_item_id: uuid.UUID
    #: `travel.departure_date` or `travel.return_date`.
    claim_type: str
    value: date


@dataclass(frozen=True)
class RecordedTrip:
    """The trip as the user recorded it, flattened to what a comparison needs."""

    travel_record_id: uuid.UUID
    departure_date: date
    return_date: date


@dataclass(frozen=True)
class DateConflict:
    """One field of one trip, where the document and the record disagree."""

    travel_record_id: uuid.UUID
    #: `departure_date` or `return_date` — the `TripInput` field, not the claim type.
    field: str
    #: What the user recorded.
    recorded: date
    #: What the document says, confirmed by a person.
    documented: date
    fact_version_id: uuid.UUID
    evidence_item_id: uuid.UUID


def detect(
    *,
    trips: Iterable[RecordedTrip],
    documented: Iterable[ConfirmedDocumentDate],
    attachments: Iterable[tuple[uuid.UUID, uuid.UUID]],
) -> list[DateConflict]:
    """Every disagreement between a recorded trip and a document attached to it.

    `attachments` is `(evidence_item_id, travel_record_id)` for every **live** link. A
    document attached to no trip produces nothing, which is the case that keeps a booking
    the user has not filed from silently arguing with a trip it may not be about.

    A document attached to two trips is compared against both. That is not a mistake to
    guard against here: the user said both, and a booking that genuinely covers two legs
    is exactly the shape `journey_index` exists for. If one of those is wrong, the remedy
    is detaching it — which is a command they already have.

    Ordered by record and then field, so two runs over the same inputs produce the same
    `AssessmentInputLink` rows. Unordered provenance would differ between identical runs.
    """
    trips_by_id = {trip.travel_record_id: trip for trip in trips}
    linked: dict[uuid.UUID, list[uuid.UUID]] = {}
    for evidence_item_id, travel_record_id in attachments:
        linked.setdefault(evidence_item_id, []).append(travel_record_id)

    conflicts: list[DateConflict] = []
    for entry in documented:
        field = TRAVEL_DATE_CLAIM_TYPES.get(entry.claim_type)
        if field is None:
            # Not a travel date. `immigration.status_granted_on` is a confirmed fact too,
            # and it has nothing to disagree with here — silently ignoring it is right,
            # because this function's question is only about trips.
            continue
        for travel_record_id in linked.get(entry.evidence_item_id, ()):
            trip = trips_by_id.get(travel_record_id)
            if trip is None:
                # Linked to a trip that is no longer active. A removed trip is a
                # tombstone and cannot be in conflict with anything.
                continue
            recorded = getattr(trip, field)
            if recorded == entry.value:
                # Agreement. RFC §16 calls this a corroborating claim: it does not create a
                # conflict, and §41.5 decided it creates no automatic provenance either.
                continue
            conflicts.append(
                DateConflict(
                    travel_record_id=travel_record_id,
                    field=field,
                    recorded=recorded,
                    documented=entry.value,
                    fact_version_id=entry.fact_version_id,
                    evidence_item_id=entry.evidence_item_id,
                )
            )

    return sorted(conflicts, key=lambda c: (str(c.travel_record_id), c.field))


def conflicted_record_ids(conflicts: Iterable[DateConflict]) -> frozenset[uuid.UUID]:
    """The trips a caller must treat as `CONFLICTING`.

    Separate from `detect` because the two answer different questions and one of them is
    load-bearing twice: RULES_SPEC §6.1 excludes a `CONFLICTING` trip from the **trusted
    total**, and §7.8 turns it into an `INCONSISTENT` consistency verdict. Applying one
    without the other is the mutation this slice's table exists to catch.
    """
    return frozenset(conflict.travel_record_id for conflict in conflicts)
