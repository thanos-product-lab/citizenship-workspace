"""The travel history as a list to hand over: the trips in a period, in order (ADR-0035).

Someone applying may have more trips than the online form has room for, and upload the full
list at the documents step instead. This builds that list from the case, for a CSV and for
the print page the browser saves as PDF.

**Every active trip in the period is listed, including ones no assessment would trust.** On
a list someone hands to the Home Office, leaving a trip out is the dangerous direction: an
under-declared history is false reassurance in its plainest form (CLAUDE.md §2.7). A trip
the assessment holds back is listed and marked in words instead. A value a document proposed
and nobody confirmed is not a trip at all, and cannot appear (directive 1): only travel
records are read.

**A trip is in the period when its dates overlap it**, not when it has counted days in it.
A same-day trip is zero days absent (RULES_SPEC §5) and still a trip the form asks about.

**No day counts.** A figure in a file handed to a caseworker reads as an official count,
and this workspace's figures are not that.

Pure: no session and no clock. `service.get_travel_export` gathers the inputs.
"""

import csv
import io
import uuid
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import date
from enum import StrEnum

from app.requirements.rules_core import Window, absent_dates, qualifying_window


class ExportScope(StrEnum):
    #: The five years before the application date (the qualifying period).
    WINDOW = "WINDOW"
    ALL = "ALL"


class TripMarker(StrEnum):
    """Why the assessment would not count a listed trip, most serious first."""

    DISPUTED = "DISPUTED"
    NOT_CONFIRMED = "NOT_CONFIRMED"
    ESTIMATED = "ESTIMATED"


class ExportCaution(StrEnum):
    """Something to know before relying on the list."""

    NO_APPLICATION_DATE = "NO_APPLICATION_DATE"
    OVERLAPPING_TRIPS = "OVERLAPPING_TRIPS"
    DOCUMENTS_AWAITING_REVIEW = "DOCUMENTS_AWAITING_REVIEW"


@dataclass(frozen=True)
class ExportTripInput:
    travel_record_id: uuid.UUID
    destination_label: str
    reason: str | None
    departure_date: date
    return_date: date
    review_state: str
    #: With the conflict overlay already applied: `CONFLICTING` for a trip a confirmed
    #: document disputes, from `gather_trips`, so the export and the assessment agree.
    date_confidence: str


@dataclass(frozen=True)
class ExportTrip:
    travel_record_id: uuid.UUID
    destination_label: str
    reason: str | None
    departure_date: date
    return_date: date
    markers: tuple[TripMarker, ...]


@dataclass(frozen=True)
class CautionItem:
    code: ExportCaution
    count: int


@dataclass(frozen=True)
class TravelExport:
    #: What was asked for may differ: with no application date there is no period, so
    #: `ALL` is what was built, and a caution says why.
    scope: ExportScope
    application_date: date | None
    window: Window | None
    trips: tuple[ExportTrip, ...]
    cautions: tuple[CautionItem, ...]
    prepared_on: date


def markers_for(trip: ExportTripInput) -> tuple[TripMarker, ...]:
    """The reasons a trip would be held back from a trusted total (RULES_SPEC §6.1), in
    words the list can carry. Empty for a trip the assessment counts."""
    markers: list[TripMarker] = []
    if trip.date_confidence == "CONFLICTING":
        markers.append(TripMarker.DISPUTED)
    if trip.review_state != "CONFIRMED":
        markers.append(TripMarker.NOT_CONFIRMED)
    if trip.date_confidence in ("ESTIMATED", "UNKNOWN"):
        markers.append(TripMarker.ESTIMATED)
    return tuple(markers)


def overlaps(trip: ExportTripInput, window: Window) -> bool:
    """Calendar overlap with the period, both ends inclusive."""
    return trip.departure_date <= window.end and trip.return_date >= window.start


def build_export(
    *,
    trips: Sequence[ExportTripInput],
    application_date: date | None,
    scope: ExportScope,
    documents_awaiting_review: int,
    prepared_on: date,
) -> TravelExport:
    window = qualifying_window(application_date) if application_date is not None else None
    effective = scope if window is not None else ExportScope.ALL

    included = sorted(
        (
            trip
            for trip in trips
            if effective is ExportScope.ALL or (window is not None and overlaps(trip, window))
        ),
        key=lambda trip: (trip.departure_date, trip.return_date, trip.destination_label),
    )

    cautions: list[CautionItem] = []
    if window is None:
        cautions.append(CautionItem(ExportCaution.NO_APPLICATION_DATE, 0))
    overlapping = _overlapping_count(included)
    if overlapping:
        cautions.append(CautionItem(ExportCaution.OVERLAPPING_TRIPS, overlapping))
    if documents_awaiting_review:
        cautions.append(
            CautionItem(ExportCaution.DOCUMENTS_AWAITING_REVIEW, documents_awaiting_review)
        )

    return TravelExport(
        scope=effective,
        application_date=application_date,
        window=window,
        trips=tuple(
            ExportTrip(
                travel_record_id=trip.travel_record_id,
                destination_label=trip.destination_label,
                reason=trip.reason,
                departure_date=trip.departure_date,
                return_date=trip.return_date,
                markers=markers_for(trip),
            )
            for trip in included
        ),
        cautions=tuple(cautions),
        prepared_on=prepared_on,
    )


def _overlapping_count(trips: Sequence[ExportTripInput]) -> int:
    """Trips sharing a day abroad with another listed trip: the same test the timeline's
    `overlaps_with` uses. One of each pair is probably wrong, and a caseworker reading two
    trips abroad at once will ask."""
    days = [absent_dates(trip.departure_date, trip.return_date) for trip in trips]
    return sum(
        1
        for index, mine in enumerate(days)
        if any(mine & other for other_index, other in enumerate(days) if other_index != index)
    )


# --- CSV ---------------------------------------------------------------------------------

CSV_HEADERS = ("Country visited", "Reason for trip", "Departure date", "Return date", "Note")

#: A spreadsheet treats a cell starting with one of these as a formula. Destinations and
#: reasons are text the user typed, and "=HYPERLINK(...)" opened in Excel would run.
_FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")


def _cell(value: str) -> str:
    """OWASP's CSV-injection guard: a leading apostrophe makes the cell text."""
    return f"'{value}" if value.startswith(_FORMULA_PREFIXES) else value


def to_csv(export: TravelExport, render_marker: Callable[[TripMarker], str]) -> str:
    """The list as CSV, shaped like the form's own table.

    ISO dates, because the import refuses anything else for the same reason: `04/05/2023`
    is two different days depending on who opens it. A UTF-8 byte-order mark leads, without
    which Excel opens "Côte d'Ivoire" as mojibake. RFC 4180 line endings.
    """
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\r\n")
    writer.writerow(CSV_HEADERS)
    for trip in export.trips:
        writer.writerow(
            (
                _cell(trip.destination_label),
                _cell(trip.reason or ""),
                trip.departure_date.isoformat(),
                trip.return_date.isoformat(),
                "; ".join(render_marker(marker) for marker in trip.markers),
            )
        )
    return "﻿" + buffer.getvalue()
