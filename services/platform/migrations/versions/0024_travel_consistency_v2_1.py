"""residence.travel_consistency v2.1.0: the duplicate-record detection

M7 slice 4b changed what this rule emits — a new `DUPLICATE_TRAVEL_RECORD` limitation, and
an `OVERLAPPING_TRAVEL` limitation that no longer names a pair whose overlap is fully
explained by duplication. RULES_SPEC §7.8 is entirely **[PRODUCT]**, and §12 is explicit:
*"A change to any [PRODUCT] item requires a new rule version for the affected requirement
only."* The slice shipped without one, which two reviews caught.

The defect that creates, in the product's own terms: two `AssessmentResult` rows would carry
`rule_version_id` = v2.0.0 while having been produced by different logic. CLAUDE.md §9's
"every historical assessment preserves its exact rule and input versions" would be true of
the identifier and false of the substance — and `implementation_hash` is never populated, so
nothing would detect the drift. A case containing a duplicate would also keep a CURRENT
result the shipped rules can no longer produce, showing `OVERLAPPING_TRAVEL` until some
unrelated edit happened to trigger a recalculation.

**2.1.0, not 3.0.0.** The rule set does not move: no guidance changed, and §12 reserves a new
rule *set* for [GUIDANCE] changes. Within the requirement this is additive — a new detection
and a narrower limitation, no dependency change, no banding change — so the minor version.

**This sweep closes over composition edges**, which `0022`'s did not. ADR-0022 recorded that
as the obligation on every future activation: a requirement composing a retired rule's
conclusion stands CURRENT over an upstream that is not. Nothing composes
`residence.travel_consistency` today, so the closure selects nothing — it is written now
because the day `preparation.case_complete` gets an evaluator is not the day to remember it.

Revision ID: 0024_travel_consistency_v2_1
Revises: 0023_travel_consistency_citation
Create Date: 2026-08-26
"""

import uuid
from collections.abc import Sequence
from datetime import UTC, datetime

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0024_travel_consistency_v2_1"
down_revision: str | None = "0023_travel_consistency_citation"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_KEY = "residence.travel_consistency"
_RULE_SET = "2026.07.0"
_SEMVER = "2.1.0"
_NS = uuid.UUID("6f1d2c3b-0a11-4e22-9c33-000000000024")

_V2_ID = uuid.uuid5(uuid.UUID("6f1d2c3b-0a11-4e22-9c33-000000000022"), f"rule_version:{_KEY}")
_V21_ID = uuid.uuid5(_NS, f"rule_version:{_KEY}")

#: Carried forward unchanged from v2.0.0. The detection reads `destination_country_code` and
#: `destination_label` off `TravelRecordVersion`, which the travel dependency already covers,
#: so nothing new is declared — and `0023` already removed the citation that did not describe
#: what this rule adjudicates.
_DEPENDENCIES: list[tuple[str, str | None, str, bool]] = [
    ("PROPOSED_APPLICATION_DATE", None, "ANY_CURRENT_VERSION", True),
    ("TRAVEL_RECORD", None, "ALL_ACTIVE_TRAVEL_RECORDS", False),
    ("EVIDENCE_SUPPORT", None, "ALL_ACTIVE_EVIDENCE_LINKS", False),
]

#: Every requirement whose current result was produced by the retired version, **plus every
#: requirement that transitively composes one of those** — the closure `0022` omitted.
#:
#: Exported so a test can execute this statement rather than a transcription of it. `0022`
#: learned that the hard way: while its test held a copy, gutting the sweep left the test
#: green and the ADR asserting a mutation that did not exist.
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


def _dependency_id(kind: str) -> uuid.UUID:
    return uuid.uuid5(_NS, f"dependency:{_KEY}:{kind}")


def upgrade() -> None:
    bind = op.get_bind()
    now = datetime.now(UTC)

    requirement_id = bind.execute(
        sa.text("SELECT id FROM requirement_definitions WHERE requirement_key = :key"),
        {"key": _KEY},
    ).scalar_one()
    guidance = bind.execute(
        sa.text("SELECT configuration -> 'guidance' FROM rule_versions WHERE id = :id"),
        {"id": _V2_ID},
    ).scalar_one()

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
                "id": _V21_ID,
                "requirement_id": requirement_id,
                "semantic_version": _SEMVER,
                "rule_set": _RULE_SET,
                "evaluator_key": _KEY,
                # Carried from v2.0.0 as it stands *after* `0023`, rather than restated —
                # a literal here would silently revert that correction.
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
                "id": _dependency_id(kind),
                "rule_version_id": _V21_ID,
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
        {"now": now, "id": _V2_ID},
    )
    bind.execute(sa.text(SWEEP_SQL), {"now": now, "retired": _V2_ID})


def downgrade() -> None:
    bind = op.get_bind()
    op.execute(
        sa.text("DELETE FROM rule_dependency_definitions WHERE rule_version_id = :id").bindparams(
            sa.bindparam("id", value=_V21_ID)
        )
    )
    op.execute(
        sa.text("DELETE FROM rule_versions WHERE id = :id").bindparams(
            sa.bindparam("id", value=_V21_ID)
        )
    )
    bind.execute(
        sa.text(
            "UPDATE rule_versions SET lifecycle_status = 'ACTIVE', effective_to = NULL "
            "WHERE id = :id"
        ),
        {"id": _V2_ID},
    )
    # Swept results stay stale, as in `0022`: marking something stale says it needs
    # rechecking, and rolling the catalog back does not make that untrue.
