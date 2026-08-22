"""The residence timeline projection — Domain §44.3.

A read model over the case's *inputs*, not over its conclusions. It answers "what do my
travel records say, measured against my application date", and it deliberately carries no
`Conclusion` enum and no currency: those belong to `AssessmentResult`, which is the single
source of truth for what was concluded (ADR-0007), and a second surface publishing its own
conclusions would be a second answer to the same question.

That distinction is what lets this be computed live. Every figure comes from `rules_core`,
the same functions the evaluators call, so the arithmetic cannot fork — but the figures
describe the records **as they stand now**, which after an edit is ahead of the last
assessment. Rather than hide that, the projection reports whether the residence results are
stale, so the view can say plainly that the last assessment was run before these records
changed. Showing a total silently ahead of the conclusions drawn from it is the shape of
false reassurance this product exists to prevent (CLAUDE.md §2.7).

What is deliberately absent: evidence coverage. Domain §44.3 lists it, and there is no
evidence model until M7 — a coverage column that could only ever read "none" would make a
promise the product cannot keep.
"""

import uuid
from dataclasses import dataclass
from datetime import date

from sqlalchemy.orm import Session

from app.assessments.repository import AssessmentRepository
from app.cases.domain import ApplicationCase
from app.requirements.domain import Currency
from app.requirements.evaluation import RESIDENCE_REQUIREMENT_KEYS
from app.requirements.rules_core import (
    Window,
    absence_union,
    absent_dates,
    count_in_window,
    final_year_window,
    physical_presence_date,
    qualifying_window,
)
from app.residence.domain import (
    TravelRecord,
    TravelRecordVersion,
    counts_toward_trusted_total,
)
from app.residence.repository import (
    ProposedApplicationDateRepository,
    TravelRecordRepository,
)


@dataclass(frozen=True)
class TimelineTrip:
    """One travel record as the timeline sees it.

    `counted_days` is the figure that matters and the one a user cannot derive: a trip's
    absent set intersected with the qualifying window. It differs from `absent_days` for
    any trip straddling a boundary — the canonical case's trip 1 is abroad for 11 days and
    contributes 10, because the window starts a day after it departs. Both are published so
    the difference can be *explained* rather than silently applied (RULES_SPEC §5.3).
    """

    travel_record_id: uuid.UUID
    destination_label: str
    departure_date: date
    return_date: date
    date_confidence: str
    review_state: str
    #: The §6.1 trust gate — ACTIVE and CONFIRMED and EXACT. Decided here from the same
    #: predicate the evaluators use, never re-derived from the fields.
    is_trusted: bool
    absent_days: int
    counted_days: int
    #: Wholly outside the qualifying window: kept for the record, counts towards nothing.
    is_outside_window: bool
    #: Its absent set contains the presence anchor — the single day presence is tested on.
    covers_presence_anchor: bool
    #: Other trips whose absent days this one shares. Overlaps never double-count (the
    #: totals are a union), but they mean one of the records is likely wrong.
    overlaps_with: tuple[uuid.UUID, ...]


@dataclass(frozen=True)
class TimelineTotals:
    qualifying_period_days: int
    final_year_days: int
    #: Counting unconfirmed records too (RULES_SPEC §6.2). Equal to the trusted figure
    #: when every record is confirmed and exact, which is the canonical case.
    qualifying_period_days_including_unconfirmed: int
    final_year_days_including_unconfirmed: int
    trip_count: int
    unconfirmed_trip_count: int


@dataclass(frozen=True)
class TimelineProjection:
    application_date: date
    qualifying_period: Window
    final_year: Window
    presence_anchor: date
    #: Whether the anchor falls inside the *trusted* absent set — the fact the whole
    #: date-simulation interaction exists to move.
    presence_anchor_is_absent: bool
    trips: tuple[TimelineTrip, ...]
    totals: TimelineTotals
    #: The residence conclusions were reached before the records now shown. The figures
    #: here are current; the conclusions on the Requirements destination are not.
    assessment_is_stale: bool


def _spans(
    records: list[tuple[TravelRecord, TravelRecordVersion]],
) -> list[tuple[date, date]]:
    return [(version.departure_date, version.return_date) for _, version in records]


def _residence_results_are_stale(session: Session, case_id: uuid.UUID) -> bool:
    """Whether any residence conclusion is flagged for recalculation.

    Scoped to the residence keys rather than the whole case: a stale referee requirement
    says nothing about whether these figures match the conclusions drawn from them.
    """
    return any(
        result is not None
        and result.currency == Currency.STALE.value
        and definition.requirement_key in RESIDENCE_REQUIREMENT_KEYS
        for definition, result in AssessmentRepository.list_requirements_with_active_result(
            session, case_id
        )
    )


def get_timeline(session: Session, *, case: ApplicationCase) -> TimelineProjection | None:
    """The case's residence timeline, or `None` when no application date is selected.

    `None` rather than an error: without a date there is no window, so every counted figure
    would be undefined — but the trips themselves are perfectly real and the view can still
    list them. That is a decision for the view, and an exception would take it away.
    """
    root = ProposedApplicationDateRepository.get_current_for_case(session, case.id)
    version = (
        ProposedApplicationDateRepository.get_version(session, root.current_version_id)
        if root is not None and root.current_version_id is not None
        else None
    )
    if version is None:
        return None

    application_date = version.application_date
    qualifying = qualifying_window(application_date)
    final_year = final_year_window(application_date)
    anchor = physical_presence_date(application_date)

    records = TravelRecordRepository.list_active_with_current_version(session, case.id)
    trusted_spans = [
        (v.departure_date, v.return_date) for r, v in records if counts_toward_trusted_total(r, v)
    ]
    trusted_absent = absence_union(trusted_spans)
    all_absent = absence_union(_spans(records))

    absent_by_record = {
        record.id: absent_dates(version_.departure_date, version_.return_date)
        for record, version_ in records
    }

    trips = tuple(
        TimelineTrip(
            travel_record_id=record.id,
            destination_label=version_.destination_label,
            departure_date=version_.departure_date,
            return_date=version_.return_date,
            date_confidence=version_.date_confidence,
            review_state=version_.review_state,
            is_trusted=counts_toward_trusted_total(record, version_),
            absent_days=len(absent_by_record[record.id]),
            counted_days=count_in_window(absent_by_record[record.id], qualifying),
            is_outside_window=count_in_window(absent_by_record[record.id], qualifying) == 0,
            covers_presence_anchor=anchor in absent_by_record[record.id],
            overlaps_with=tuple(
                other.id
                for other, _ in records
                if other.id != record.id
                and absent_by_record[record.id] & absent_by_record[other.id]
            ),
        )
        for record, version_ in records
    )

    return TimelineProjection(
        application_date=application_date,
        qualifying_period=qualifying,
        final_year=final_year,
        presence_anchor=anchor,
        presence_anchor_is_absent=anchor in trusted_absent,
        trips=trips,
        totals=TimelineTotals(
            qualifying_period_days=count_in_window(trusted_absent, qualifying),
            final_year_days=count_in_window(trusted_absent, final_year),
            qualifying_period_days_including_unconfirmed=count_in_window(all_absent, qualifying),
            final_year_days_including_unconfirmed=count_in_window(all_absent, final_year),
            trip_count=len(trips),
            unconfirmed_trip_count=sum(1 for trip in trips if not trip.is_trusted),
        ),
        assessment_is_stale=_residence_results_are_stale(session, case.id),
    )
