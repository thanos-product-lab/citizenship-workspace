"""The downloadable travel-history template must stay in step with the parser.

The template is a static file the web app serves, so nothing else ties its header row to
`REQUIRED_HEADERS`. A column renamed here and not there would hand every user a template
the importer refuses as malformed.
"""

from pathlib import Path

import pytest

from app.residence.csv_import import OPTIONAL_HEADERS, REQUIRED_HEADERS, parse_import
from app.shared.errors import CsvImportMalformed

TEMPLATE = Path(__file__).resolve().parents[4] / "apps/web/public/templates/travel-history.csv"


def test_the_template_names_every_column_the_importer_reads() -> None:
    header = TEMPLATE.read_text().splitlines()[0].split(",")
    assert header == [*REQUIRED_HEADERS, *OPTIONAL_HEADERS]


def test_the_template_carries_no_example_trip() -> None:
    # An example row left in by a user would be imported as a real trip. The header is
    # accepted, so the only refusal is the one for having nothing to import.
    with pytest.raises(CsvImportMalformed, match="no data rows"):
        parse_import(TEMPLATE.read_text())
