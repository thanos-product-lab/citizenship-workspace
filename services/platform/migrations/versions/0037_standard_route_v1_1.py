"""`route.standard_section_6_1` tells an undetermined prerequisite apart from a failed one

The composite asked one question — *are adult and status both `SUPPORTED`?* — and called
everything else failure. `NOT_YET_ASSESSED` is everything else.

§7.2 has always concluded `NOT_YET_ASSESSED` for an `UNKNOWN` or absent status, and
`applicants.service._SUPPORT_BY_CONCLUSION` maps that to `NOT_EVALUATED` under a comment
saying missing data must "never" become a definitive negative. The composite sat between
the two and undid it: an applicant who answered *"I'm not sure"* about their immigration
status was told their status is not supported.

Nobody had seen it, because `_missing_required_fields` counted `UNKNOWN` as no answer at
all and refused the confirmation before any rule ran. Removing that gate — so the offered
answer is actually accepted — is what makes this row reachable, and reaching it with the
old logic would have shipped the false negative. The two changes belong together.

**1.1.0, not 2.0.0.** Following `0024`, `0034` and `0035`: no change to guidance, to the
conclusion vocabulary, or to any threshold. One new summary code,
`ROUTE_PREREQUISITES_UNDETERMINED`, on a conclusion that already existed. §12 reserves a
new rule *set* for `[GUIDANCE]` changes and the rule set does not move.

**Composition edges are carried, not re-derived.** The composite is the one rule with
`rule_composition_edges`, and a new version with none would silently drop the selective
invalidation that restales it when `route.adult_applicant` moves — the exact edge ADR-0007
and `test_a_date_move_that_flips_an_upstream_conclusion_stales_the_composite` exist to
protect.

Revision ID: 0037_standard_route_v1_1
Revises: 0036_case_owner_function
Create Date: 2026-09-22
"""

import uuid
from collections.abc import Sequence
from datetime import UTC, datetime

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0037_standard_route_v1_1"
down_revision: str | None = "0036_case_owner_function"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_RULE_SET = "2026.07.0"
_SEMVER = "1.1.0"
_KEY = "route.standard_section_6_1"
_NS = uuid.UUID("6f1d2c3b-0a11-4e22-9c33-000000000037")

#: Unchanged by this version: the composite reads the route profile directly and its two
#: upstream *conclusions* through `rule_composition_edges` below.
_DEPENDENCIES: list[tuple[str, str | None, str, bool]] = [
    ("ROUTE_PROFILE", None, "ANY_CURRENT_VERSION", True),
]

#: Identical to `0035`'s, and executed rather than transcribed for the same reason: a test
#: runs this statement, so gutting the sweep cannot leave the test green.
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


def _new_version_id() -> uuid.UUID:
    return uuid.uuid5(_NS, f"rule_version:{_KEY}")


def upgrade() -> None:
    bind = op.get_bind()
    now = datetime.now(UTC)

    requirement_id = bind.execute(
        sa.text("SELECT id FROM requirement_definitions WHERE requirement_key = :key"),
        {"key": _KEY},
    ).scalar_one()
    previous_id, guidance = bind.execute(
        sa.text(
            "SELECT id, configuration -> 'guidance' FROM rule_versions "
            "WHERE requirement_id = :rid AND lifecycle_status = 'ACTIVE'"
        ),
        {"rid": requirement_id},
    ).one()
    # Read from the version being retired rather than restated, so a later correction to
    # either is not silently reverted here.
    edges = bind.execute(
        sa.text(
            "SELECT upstream_requirement_key, required FROM rule_composition_edges "
            "WHERE rule_version_id = :id ORDER BY upstream_requirement_key"
        ),
        {"id": previous_id},
    ).all()
    assert edges, "the composite must carry its upstream edges forward"

    new_id = _new_version_id()
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
                "evaluator_key": _KEY,
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
                "id": uuid.uuid5(_NS, f"dependency:{_KEY}:{kind}"),
                "rule_version_id": new_id,
                "input_kind": kind,
                "input_key": input_key,
                "dependency_scope": scope,
                "required": required,
            }
            for kind, input_key, scope, required in _DEPENDENCIES
        ],
    )
    op.bulk_insert(
        sa.table(
            "rule_composition_edges",
            sa.column("id", sa.Uuid),
            sa.column("rule_version_id", sa.Uuid),
            sa.column("upstream_requirement_key", sa.String),
            sa.column("required", sa.Boolean),
        ),
        [
            {
                "id": uuid.uuid5(_NS, f"edge:{_KEY}:{upstream}"),
                "rule_version_id": new_id,
                "upstream_requirement_key": upstream,
                "required": required,
            }
            for upstream, required in edges
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
    new_id = _new_version_id()
    bind.execute(
        sa.text("DELETE FROM rule_composition_edges WHERE rule_version_id = :id"),
        {"id": new_id},
    )
    bind.execute(
        sa.text("DELETE FROM rule_dependency_definitions WHERE rule_version_id = :id"),
        {"id": new_id},
    )
    requirement_id = bind.execute(
        sa.text("SELECT id FROM requirement_definitions WHERE requirement_key = :key"),
        {"key": _KEY},
    ).scalar_one()
    bind.execute(sa.text("DELETE FROM rule_versions WHERE id = :id"), {"id": new_id})
    bind.execute(
        sa.text(
            "UPDATE rule_versions SET lifecycle_status = 'ACTIVE', effective_to = NULL "
            "WHERE requirement_id = :rid AND semantic_version = '1.0.0'"
        ),
        {"rid": requirement_id},
    )
