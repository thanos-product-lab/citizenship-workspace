"""residence.travel_consistency v2.2.0: the CASE_FACT dependency

M8 slice 4 gave `DateConfidence.CONFLICTING` its first producer. From M3B to M8 this rule's
conflict detection was reachable only by a test — nothing in the product ever set that
confidence — and it is now derived at assessment time when a **confirmed** fact from a
document disagrees with the trip that document is attached to
(EVIDENCE_AND_CLAIM_LIFECYCLE_RFC §42).

**The rule's own logic did not change.** `_evaluate_travel_consistency` detects
`CONFLICTING` exactly as it has since M3B. What changed is that the evaluation now reads a
new *class of input* to decide which trips carry it, and RULES_SPEC §12 requires the rule to
say so: a dependency it does not declare is one nothing will restale it for. Without this,
confirming a value on a document would leave every dependent result standing `CURRENT` over
an input it had never seen.

**2.2.0, not 3.0.0.** The rule set does not move — no guidance changed, and §12 reserves a
new rule *set* for [GUIDANCE] changes. Within the requirement this is additive: a new input
class and a detection that already existed, with no change to the conclusion vocabulary, the
limitation codes, or the banding. `0024` made the same call for the same reason and is worth
reading beside this one.

**The §6.1 half travels with it.** A trip whose derived confidence is `CONFLICTING` is
excluded from the trusted total, which is the clause most easily dropped when someone
implements only the visible half of a conflict. That is enforced in `_gather_trips` and
guarded by the slice's mutation table, not here — but a reader arriving at this migration to
ask what v2.2.0 does should know it is part of the same change.

**The sweep closes over composition edges**, as `0024`'s does. Nothing composes
`residence.travel_consistency` today, so the closure selects nothing; it is written because
the day something does compose it is not the day to remember this.

Revision ID: 0034_travel_consistency_v2_2
Revises: 0033_fact_scope
Create Date: 2026-09-07
"""

import uuid
from collections.abc import Sequence
from datetime import UTC, datetime

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0034_travel_consistency_v2_2"
down_revision: str | None = "0033_fact_scope"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_KEY = "residence.travel_consistency"
_RULE_SET = "2026.07.0"
_SEMVER = "2.2.0"
_NS = uuid.UUID("6f1d2c3b-0a11-4e22-9c33-000000000034")

_V21_ID = uuid.uuid5(uuid.UUID("6f1d2c3b-0a11-4e22-9c33-000000000024"), f"rule_version:{_KEY}")
_V22_ID = uuid.uuid5(_NS, f"rule_version:{_KEY}")

#: v2.1.0's four, plus `CASE_FACT`.
#:
#: `ANY_CURRENT_VERSION` rather than a per-fact scope: the rule reads whichever confirmed
#: travel facts the case holds, and there is no single version it depends on. `required` is
#: False — a case with no documents has no facts, and the rule is expected to run and find
#: nothing rather than refuse to evaluate.
_DEPENDENCIES: list[tuple[str, str | None, str, bool]] = [
    ("PROPOSED_APPLICATION_DATE", None, "ANY_CURRENT_VERSION", True),
    ("TRAVEL_RECORD", None, "ALL_ACTIVE_TRAVEL_RECORDS", False),
    ("EVIDENCE_SUPPORT", None, "ALL_ACTIVE_EVIDENCE_LINKS", False),
    ("CASE_FACT", None, "ANY_CURRENT_VERSION", False),
]

#: Identical to `0024`'s, and exported for the same reason: a test executes this statement
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
        {"id": _V21_ID},
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
                "id": _V22_ID,
                "requirement_id": requirement_id,
                "semantic_version": _SEMVER,
                "rule_set": _RULE_SET,
                "evaluator_key": _KEY,
                # Carried from v2.1.0 rather than restated, so a guidance correction made
                # in a later migration is not silently reverted here.
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
                "rule_version_id": _V22_ID,
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
        {"now": now, "id": _V21_ID},
    )
    bind.execute(sa.text(SWEEP_SQL), {"now": now, "retired": _V21_ID})


def downgrade() -> None:
    bind = op.get_bind()
    op.execute(
        sa.text("DELETE FROM rule_dependency_definitions WHERE rule_version_id = :id").bindparams(
            sa.bindparam("id", value=_V22_ID)
        )
    )
    op.execute(
        sa.text("DELETE FROM rule_versions WHERE id = :id").bindparams(
            sa.bindparam("id", value=_V22_ID)
        )
    )
    bind.execute(
        sa.text(
            "UPDATE rule_versions SET lifecycle_status = 'ACTIVE', effective_to = NULL "
            "WHERE id = :id"
        ),
        {"id": _V21_ID},
    )
    # Swept results stay stale, as in `0022` and `0024`: marking something stale says it
    # needs rechecking, and rolling the catalog back does not make that untrue.
