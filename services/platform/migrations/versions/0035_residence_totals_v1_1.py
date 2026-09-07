"""The three residence rules that read trip trust declare CASE_FACT and EVIDENCE_SUPPORT

`0034` gave `residence.travel_consistency` the `CASE_FACT` dependency and stopped there. It
was one rule short of the truth by three.

M8 slice 4's §6.1 half — a trip whose derived confidence is `CONFLICTING` is excluded from
the **trusted total** — is applied in `_gather_trips`, which builds the `trips` tuple that
*every* residence rule reads. Three of them consume `is_trusted`:
`residence.total_absences`, `residence.final_year_absences`, and
`residence.physical_presence_start_date`. Confirming a document date that disagrees with a
trip changes what all three compute, and none of them declared an input that would restale
them for it.

**What that produced, on the canonical demo case.** Confirming the amended booking's return
date left `residence.total_absences` standing `CURRENT` at 439 days. The next recalculation
— for any reason at all — moved it to 434. Between the two, a figure the product presented as
current had been computed from a date the product itself was about to report as disputed.
That is the invariant in CLAUDE.md §9: *every current trusted assessment references current
relevant input versions*.

**`EVIDENCE_SUPPORT` for the same reason.** A conflict needs a link; detaching the document
dissolves it and moves the totals back. Before slice 4 evidence links reached only
`travel_consistency`'s unevidenced detection, so these three rightly did not declare them.
Slice 4 is what made an evidence link able to move an absence total.

**1.1.0, not 2.0.0.** Following `0024` and `0034`: additive input classes, no change to
guidance, conclusion vocabulary, limitation codes, or banding. §12 reserves a new rule *set*
for `[GUIDANCE]` changes and the rule set does not move.

Revision ID: 0035_residence_totals_v1_1
Revises: 0034_travel_consistency_v2_2
Create Date: 2026-09-07
"""

import uuid
from collections.abc import Sequence
from datetime import UTC, datetime

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0035_residence_totals_v1_1"
down_revision: str | None = "0034_travel_consistency_v2_2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_RULE_SET = "2026.07.0"
_SEMVER = "1.1.0"
_NS = uuid.UUID("6f1d2c3b-0a11-4e22-9c33-000000000035")

#: The three rules whose evaluators read `TripInput.is_trusted`.
#: `residence.qualifying_period` is deliberately absent: it reads the application date and
#: nothing else (ADR-0014), so a conflict cannot reach it and declaring one would restale it
#: for an input it never sees.
_KEYS = (
    "residence.total_absences",
    "residence.final_year_absences",
    "residence.physical_presence_start_date",
)

#: Their existing two, plus the two slice 4 made reachable.
_DEPENDENCIES: list[tuple[str, str | None, str, bool]] = [
    ("PROPOSED_APPLICATION_DATE", None, "ANY_CURRENT_VERSION", True),
    ("TRAVEL_RECORD", None, "ALL_ACTIVE_TRAVEL_RECORDS", False),
    ("EVIDENCE_SUPPORT", None, "ALL_ACTIVE_EVIDENCE_LINKS", False),
    ("CASE_FACT", None, "ANY_CURRENT_VERSION", False),
]

#: Identical to `0034`'s, and exported for the same reason: a test executes this statement
#: rather than a transcription of it, so gutting the sweep cannot leave the test green.
SWEEP_SQL = """
WITH RECURSIVE retired_keys AS (
    SELECT rd.requirement_key
    FROM assessment_results ar
    JOIN requirement_definitions rd ON rd.id = ar.requirement_id
    WHERE ar.rule_version_id = :retired AND ar.currency = 'CURRENT'
  UNION
    SELECT edges.downstream
    FROM (
        SELECT down.requirement_key AS downstream, rce.upstream_requirement_key AS upstream
        FROM rule_composition_edges rce
        JOIN rule_versions rv ON rv.id = rce.rule_version_id
        JOIN requirement_definitions down ON down.id = rv.requirement_id
        WHERE rv.lifecycle_status = 'ACTIVE'
    ) AS edges
    JOIN retired_keys ON retired_keys.requirement_key = edges.upstream
)
UPDATE assessment_results
SET currency = 'STALE',
    stale_reason_code = 'RULE_VERSION_CHANGED',
    marked_stale_at = :now
WHERE currency = 'CURRENT'
  AND requirement_id IN (
      SELECT id FROM requirement_definitions
      WHERE requirement_key IN (SELECT requirement_key FROM retired_keys)
  )
"""


def _new_version_id(key: str) -> uuid.UUID:
    return uuid.uuid5(_NS, f"rule_version:{key}")


def _dependency_id(key: str, kind: str) -> uuid.UUID:
    return uuid.uuid5(_NS, f"dependency:{key}:{kind}")


def upgrade() -> None:
    bind = op.get_bind()
    now = datetime.now(UTC)

    for key in _KEYS:
        requirement_id = bind.execute(
            sa.text("SELECT id FROM requirement_definitions WHERE requirement_key = :key"),
            {"key": key},
        ).scalar_one()
        # Whichever version is active *now*, rather than an id transcribed from an earlier
        # migration: these three have been at 1.0.0 since the requirement catalog was
        # seeded, and reading it keeps this correct if that stops being true.
        previous_id, guidance = bind.execute(
            sa.text(
                "SELECT id, configuration -> 'guidance' FROM rule_versions "
                "WHERE requirement_id = :rid AND lifecycle_status = 'ACTIVE'"
            ),
            {"rid": requirement_id},
        ).one()
        new_id = _new_version_id(key)

        op.bulk_insert(
            sa.table(
                "rule_versions",
                sa.column("id", sa.Uuid),
                sa.column("requirement_id", sa.Uuid),
                sa.column("semantic_version", sa.String),
                sa.column("rule_set", sa.String),
                sa.column("evaluator_key", sa.String),
                sa.column("configuration", postgresql.JSONB),
                sa.column("effective_from", sa.DateTime),
                sa.column("lifecycle_status", sa.String),
            ),
            [
                {
                    "id": new_id,
                    "requirement_id": requirement_id,
                    "semantic_version": _SEMVER,
                    "rule_set": _RULE_SET,
                    "evaluator_key": key,
                    # Carried, not restated, so a guidance correction made in a later
                    # migration is not silently reverted here.
                    "configuration": {"guidance": guidance},
                    "effective_from": now,
                    "lifecycle_status": "ACTIVE",
                }
            ],
        )
        op.bulk_insert(
            sa.table(
                "rule_dependency_definitions",
                sa.column("id", sa.Uuid),
                sa.column("rule_version_id", sa.Uuid),
                sa.column("input_kind", sa.String),
                sa.column("input_key", sa.String),
                sa.column("dependency_scope", sa.String),
                sa.column("required", sa.Boolean),
            ),
            [
                {
                    "id": _dependency_id(key, kind),
                    "rule_version_id": new_id,
                    "input_kind": kind,
                    "input_key": input_key,
                    "dependency_scope": scope,
                    "required": required,
                }
                for kind, input_key, scope, required in _DEPENDENCIES
            ],
        )
        bind.execute(
            sa.text(
                "UPDATE rule_versions SET lifecycle_status = 'RETIRED', effective_to = :now "
                "WHERE id = :id"
            ),
            {"now": now, "id": previous_id},
        )
        bind.execute(sa.text(SWEEP_SQL), {"now": now, "retired": previous_id})


def downgrade() -> None:
    bind = op.get_bind()
    for key in _KEYS:
        new_id = _new_version_id(key)
        bind.execute(
            sa.text("DELETE FROM rule_dependency_definitions WHERE rule_version_id = :id"),
            {"id": new_id},
        )
        bind.execute(sa.text("DELETE FROM rule_versions WHERE id = :id"), {"id": new_id})
        bind.execute(
            sa.text(
                "UPDATE rule_versions SET lifecycle_status = 'ACTIVE', effective_to = NULL "
                "WHERE evaluator_key = :key AND semantic_version = '1.0.0'"
            ),
            {"key": key},
        )
    # Swept results stay stale, as in `0022`, `0024` and `0034`: marking something stale says
    # it needs rechecking, and rolling the catalog back does not make that untrue.
