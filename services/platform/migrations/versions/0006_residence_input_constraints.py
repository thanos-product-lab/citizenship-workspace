"""storage-layer backstops on the residence input tables

Follow-up hardening for the residence tables created in 0005, added as a new
forward-only migration because 0005 has already shipped and run (never mutate a
migration that has run — CLAUDE.md §8):

- Unique `(root_id, version_number)` on both version tables: a record cannot hold two
  versions with the same number, even if a future path appended one without bumping the
  parent aggregate's optimistic revision.
- CHECK constraints pinning every enum-backed string column to its domain. This keeps
  the M3B trust gate (`CONFIRMED + EXACT + ACTIVE`) tamper-proof at the storage layer:
  a future non-HTTP writer (CSV import in Slice 3, claim confirmation in M5) cannot
  persist an out-of-domain value that a `CONFIRMED` comparison would silently miss.

Values are hardcoded on purpose — a migration is a point-in-time snapshot and must not
import the evolving domain enums. They mirror the residence enums at rule set
2026.07.0; a domain-enum change needs a further migration.

Revision ID: 0006_residence_input_constraints
Revises: 0005_residence_inputs
Create Date: 2026-07-30
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0006_residence_input_constraints"
down_revision: str | None = "0005_residence_inputs"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# (table, constraint_name, column, allowed values) for each enum-backed column.
_ENUM_CHECKS: list[tuple[str, str, str, tuple[str, ...]]] = [
    ("travel_records", "ck_travel_record_lifecycle", "lifecycle_status", ("ACTIVE", "REMOVED")),
    (
        "travel_record_versions",
        "ck_travel_version_date_confidence",
        "date_confidence",
        ("EXACT", "ESTIMATED", "CONFLICTING", "UNKNOWN"),
    ),
    (
        "travel_record_versions",
        "ck_travel_version_review_state",
        "review_state",
        ("DRAFT", "CONFIRMED", "UNCERTAIN"),
    ),
    (
        "travel_record_versions",
        "ck_travel_version_entry_source",
        "entry_source",
        ("MANUAL", "CSV_IMPORT", "CONFIRMED_CLAIM", "CORRECTED_CLAIM"),
    ),
    (
        "proposed_application_date_versions",
        "ck_proposed_date_review_state",
        "review_state",
        ("DRAFT", "CONFIRMED"),
    ),
    (
        "proposed_application_date_versions",
        "ck_proposed_date_source",
        "source",
        ("USER_ENTERED", "SYSTEM_SUGGESTED"),
    ),
]

# (constraint_name, table, columns) for each unique version-number constraint.
_UNIQUES: list[tuple[str, str, list[str]]] = [
    (
        "uq_travel_version_number",
        "travel_record_versions",
        ["travel_record_id", "version_number"],
    ),
    (
        "uq_proposed_date_version_number",
        "proposed_application_date_versions",
        ["proposed_application_date_id", "version_number"],
    ),
]


def upgrade() -> None:
    for name, table, columns in _UNIQUES:
        op.create_unique_constraint(name, table, columns)
    for table, name, column, values in _ENUM_CHECKS:
        rendered = ", ".join(f"'{v}'" for v in values)
        op.create_check_constraint(name, table, f"{column} IN ({rendered})")


def downgrade() -> None:
    for _table, name, _column, _values in _ENUM_CHECKS:
        op.drop_constraint(name, _table, type_="check")
    for name, table, _columns in _UNIQUES:
        op.drop_constraint(name, table, type_="unique")
