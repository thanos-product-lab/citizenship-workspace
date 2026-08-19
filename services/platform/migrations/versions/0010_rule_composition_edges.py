"""rule_composition_edges: the result-to-result edges selective invalidation needs

`route.standard_section_6_1` composes the *conclusions* of `route.adult_applicant` and
`route.supported_status` rather than reading raw inputs. Domain §25.1's `input_kind` list
deliberately has no result kind, so that edge cannot be a `rule_dependency_definition` row
and until now was declared nowhere at all.

That absence is a live under-invalidation bug. `route.adult_applicant` depends on the
proposed application date; the composite does not. Resolving invalidation from input-version
dependencies alone therefore stales the upstream rule and leaves the composite reading
CURRENT while the conclusion it composes has moved — silent false reassurance, with nothing
failing (ADR-0008's documented gap, ADR-0014's closure).

Composition is a property of the *rule implementation*, so like a dependency row it is
versioned with the rule version (§25.3) and a historical result stays re-derivable. The
table is global reference data alongside the rest of the catalog: no case data, no RLS,
SELECT only for the app role.

Revision ID: 0010_rule_composition_edges
Revises: 0009_status_and_consistency
Create Date: 2026-08-19
"""

import uuid
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0010_rule_composition_edges"
down_revision: str | None = "0009_status_and_consistency"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

APP_ROLE = "app_rls"

_NS = uuid.UUID("6f1d2c3b-0a11-4e22-9c33-000000000010")

_COMPOSITE = "route.standard_section_6_1"

# downstream requirement_key -> the upstream requirement keys whose conclusions it composes.
# `required` is True: the composite cannot be evaluated without both upstream conclusions.
_EDGES: dict[str, tuple[str, ...]] = {
    _COMPOSITE: ("route.adult_applicant", "route.supported_status"),
}


def _edge_id(downstream: str, upstream: str) -> uuid.UUID:
    return uuid.uuid5(_NS, f"composition:{downstream}:{upstream}")


def _active_rule_version_id(bind: sa.engine.Connection, requirement_key: str) -> uuid.UUID:
    return bind.execute(
        sa.text(
            "SELECT rv.id FROM rule_versions rv "
            "JOIN requirement_definitions rd ON rd.id = rv.requirement_id "
            "WHERE rd.requirement_key = :key AND rv.lifecycle_status = 'ACTIVE' "
            "ORDER BY rv.effective_from DESC LIMIT 1"
        ),
        {"key": requirement_key},
    ).scalar_one()


def upgrade() -> None:
    op.create_table(
        "rule_composition_edges",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("rule_version_id", sa.Uuid(), sa.ForeignKey("rule_versions.id"), nullable=False),
        sa.Column("upstream_requirement_key", sa.String(length=60), nullable=False),
        sa.Column("required", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.UniqueConstraint(
            "rule_version_id",
            "upstream_requirement_key",
            name="uq_rule_composition_edge",
        ),
    )
    op.create_index(
        "ix_rule_composition_edges_rule_version_id",
        "rule_composition_edges",
        ["rule_version_id"],
    )

    bind = op.get_bind()
    edges = sa.table(
        "rule_composition_edges",
        sa.column("id", sa.Uuid),
        sa.column("rule_version_id", sa.Uuid),
        sa.column("upstream_requirement_key", sa.String),
        sa.column("required", sa.Boolean),
    )
    rows = []
    for downstream, upstreams in _EDGES.items():
        rule_version_id = _active_rule_version_id(bind, downstream)
        for upstream in upstreams:
            # Fail the migration rather than seed an edge to a key that does not exist:
            # a typo here would silently drop the composite from every invalidation set.
            bind.execute(
                sa.text("SELECT id FROM requirement_definitions WHERE requirement_key = :key"),
                {"key": upstream},
            ).scalar_one()
            rows.append(
                {
                    "id": _edge_id(downstream, upstream),
                    "rule_version_id": rule_version_id,
                    "upstream_requirement_key": upstream,
                    "required": True,
                }
            )
    op.bulk_insert(edges, rows)

    op.execute(f"GRANT SELECT ON rule_composition_edges TO {APP_ROLE}")


def downgrade() -> None:
    op.drop_index("ix_rule_composition_edges_rule_version_id", "rule_composition_edges")
    op.drop_table("rule_composition_edges")
