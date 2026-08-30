"""Pure CSV parsing and per-row validation for the travel-history import.

No database, no HTTP — just text in, diagnostics out — so the same logic backs both
the dry-run `validate` endpoint and the atomic `import` commit, and cannot diverge
between them. Structural problems (missing columns, empty file) raise `CsvImportMalformed`
(the whole file is unusable); per-row problems are returned as `RowDiagnostic`s carrying
the exact 1-based file line and stable field/error codes so the UI can bind each error to
its cell (MVP §8.4: "import errors identify the exact affected rows").

Dates are parsed strictly as `YYYY-MM-DD` (`%Y-%m-%d`), so an ambiguous `14/04/2022` is
rejected rather than guessed — date ambiguity is exactly the kind of silent error this
product exists to surface.
"""

import csv
import io
from dataclasses import dataclass
from datetime import date, datetime

from app.residence.domain import (
    DESTINATION_LABEL_MAX_LENGTH,
    DateConfidence,
    TravelRecordFields,
    TravelReviewState,
)
from app.shared.dates import MAX_ENTERED_DATE, MIN_ENTERED_DATE
from app.shared.errors import CsvImportMalformed

REQUIRED_HEADERS = ("destination_label", "departure_date", "return_date", "date_confidence")
OPTIONAL_HEADERS = ("destination_country_code", "review_state", "notes")

# Bounds so one import cannot do unbounded work in a single transaction (holding the case
# row lock). Generous for a five-year travel history; both fail closed as CsvImportMalformed.
CONTENT_MAX_LENGTH = 1_000_000  # ~1 MB of CSV text
MAX_IMPORT_ROWS = 1000

# review_state is not in the CSV required set (§8.4); an imported trip is an assertion,
# so it defaults to CONFIRMED and can be downgraded per row.
_DEFAULT_REVIEW_STATE = TravelReviewState.CONFIRMED


@dataclass(frozen=True)
class RowError:
    field: str
    code: str
    message: str


@dataclass(frozen=True)
class RowDiagnostic:
    row_number: int  # 1-based line in the file; the header is line 1
    errors: tuple[RowError, ...]
    fields: TravelRecordFields | None  # parsed values when the row is valid, else None

    @property
    def valid(self) -> bool:
        return not self.errors


@dataclass(frozen=True)
class ParsedImport:
    rows: tuple[RowDiagnostic, ...]

    @property
    def valid_count(self) -> int:
        return sum(1 for r in self.rows if r.valid)

    @property
    def error_count(self) -> int:
        return sum(1 for r in self.rows if not r.valid)

    @property
    def all_valid(self) -> bool:
        return all(r.valid for r in self.rows)

    @property
    def valid_fields(self) -> list[TravelRecordFields]:
        return [r.fields for r in self.rows if r.fields is not None]


def parse_import(content: str) -> ParsedImport:
    """Parse and validate every row. Raises `CsvImportMalformed` for a structurally
    unusable file (no header, missing required columns, no data rows)."""
    reader = csv.DictReader(io.StringIO(content))
    headers = reader.fieldnames
    if not headers:
        raise CsvImportMalformed("the CSV is empty or has no header row")
    missing = [h for h in REQUIRED_HEADERS if h not in headers]
    if missing:
        raise CsvImportMalformed(f"missing required columns: {', '.join(missing)}")

    raw_rows = list(reader)
    if not raw_rows:
        raise CsvImportMalformed("the CSV has a header but no data rows")
    if len(raw_rows) > MAX_IMPORT_ROWS:
        raise CsvImportMalformed(f"too many rows: at most {MAX_IMPORT_ROWS} per import")

    rows = tuple(
        _validate_row(raw, row_number=index + 2)  # +2: header is line 1, data starts at 2
        for index, raw in enumerate(raw_rows)
    )
    return ParsedImport(rows=rows)


def _validate_row(raw: dict[str, str | None], *, row_number: int) -> RowDiagnostic:
    errors: list[RowError] = []

    label = _clean(raw.get("destination_label"))
    if not label:
        errors.append(
            RowError("destination_label", "DESTINATION_REQUIRED", "destination is required")
        )
    elif len(label) > DESTINATION_LABEL_MAX_LENGTH:
        # Mirror the manual cap so validate and commit agree — an over-long label was
        # previously "valid" on the dry-run then 500'd at the varchar(120) boundary.
        errors.append(
            RowError(
                "destination_label",
                "DESTINATION_TOO_LONG",
                f"must be at most {DESTINATION_LABEL_MAX_LENGTH} characters",
            )
        )

    departure = _parse_date(raw.get("departure_date"), "departure_date", errors)
    return_ = _parse_date(raw.get("return_date"), "return_date", errors)
    if departure is not None and return_ is not None and departure > return_:
        errors.append(
            RowError("return_date", "DATE_ORDER_INVALID", "departure_date is after return_date")
        )

    confidence = _parse_confidence(raw.get("date_confidence"), errors)
    review = _parse_review(raw.get("review_state"), errors)

    code = _clean(raw.get("destination_country_code")) or None
    if code is not None and len(code) != 2:
        errors.append(
            RowError("destination_country_code", "COUNTRY_CODE_INVALID", "expected a 2-letter code")
        )

    if errors:
        return RowDiagnostic(row_number=row_number, errors=tuple(errors), fields=None)

    assert label and departure is not None and return_ is not None and confidence is not None
    fields = TravelRecordFields(
        destination_label=label,
        departure_date=departure,
        return_date=return_,
        date_confidence=confidence,
        review_state=review or _DEFAULT_REVIEW_STATE,
        destination_country_code=code.upper() if code else None,
        notes=_clean(raw.get("notes")) or None,
    )
    return RowDiagnostic(row_number=row_number, errors=(), fields=fields)


def _clean(value: str | None) -> str:
    return (value or "").strip()


def _parse_date(value: str | None, field: str, errors: list[RowError]) -> date | None:
    text = _clean(value)
    if not text:
        errors.append(RowError(field, "DATE_REQUIRED", f"{field} is required"))
        return None
    try:
        parsed = datetime.strptime(text, "%Y-%m-%d").date()
    except ValueError:
        errors.append(RowError(field, "DATE_INVALID_FORMAT", "expected YYYY-MM-DD"))
        return None
    # The same calendar bound the typed form applies. A row is a *diagnostic* here rather
    # than a 422 — the importer reports every bad row at once instead of failing the file
    # on the first — but the range has to match, or a date the form refuses could be
    # imported from a spreadsheet and the two paths would disagree about what a date is.
    if not MIN_ENTERED_DATE <= parsed <= MAX_ENTERED_DATE:
        errors.append(
            RowError(
                field,
                "DATE_OUT_OF_RANGE",
                f"expected a date between {MIN_ENTERED_DATE.year} and {MAX_ENTERED_DATE.year}",
            )
        )
        return None
    return parsed


def _parse_confidence(value: str | None, errors: list[RowError]) -> DateConfidence | None:
    text = _clean(value)
    if not text:
        errors.append(
            RowError("date_confidence", "DATE_CONFIDENCE_INVALID", "date_confidence is required")
        )
        return None
    try:
        return DateConfidence(text)
    except ValueError:
        allowed = ", ".join(m.value for m in DateConfidence)
        errors.append(
            RowError("date_confidence", "DATE_CONFIDENCE_INVALID", f"expected one of: {allowed}")
        )
        return None


def _parse_review(value: str | None, errors: list[RowError]) -> TravelReviewState | None:
    text = _clean(value)
    if not text:
        return None  # optional; the caller substitutes the default
    try:
        return TravelReviewState(text)
    except ValueError:
        allowed = ", ".join(m.value for m in TravelReviewState)
        errors.append(
            RowError("review_state", "REVIEW_STATE_INVALID", f"expected one of: {allowed}")
        )
        return None
