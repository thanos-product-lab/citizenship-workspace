"""status.holding_period and residence.travel_consistency rule versions and dependencies

Seeds the two remaining M3B rule versions (slice 3): `status.holding_period` (§7.3) and
`residence.travel_consistency` (§7.8), with guidance citations and their dependency rows
per the RULES_SPEC §8 matrix. Their `RequirementDefinition` catalog rows already exist from
0007. Mirrors 0008: definition ids are looked up by requirement_key.

Revision ID: 0009_status_and_consistency
Revises: 0008_residence_rule_versions
Create Date: 2026-08-13
"""

import uuid
from collections.abc import Sequence
from datetime import UTC, datetime

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0009_status_and_consistency"
down_revision: str | None = "0008_residence_rule_versions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_RULE_SET = "2026.07.0"
_SEMVER = "1.0.0"
_NS = uuid.UUID("6f1d2c3b-0a11-4e22-9c33-000000000009")

_KEYS = ("status.holding_period", "residence.travel_consistency")

_GUIDANCE: dict[str, list[dict[str, str]]] = {
    "status.holding_period": [
        {
            "source": "GUIDE_AN",
            "section": "Free from immigration time restrictions in the 12 months before applying",
        },
    ],
    "residence.travel_consistency": [
        {
            "source": "GUIDE_AN",
            "section": "Absences from the UK (data quality over travel records)",
        },
    ],
}

_APP_DATE_DEP = ("PROPOSED_APPLICATION_DATE", None, "ANY_CURRENT_VERSION", True)
_TRAVEL_DEP = ("TRAVEL_RECORD", None, "ALL_ACTIVE_TRAVEL_RECORDS", False)
_DEPENDENCIES: dict[str, list[tuple[str, str | None, str, bool]]] = {
    "status.holding_period": [
        ("ROUTE_PROFILE", "status_granted_on", "ANY_CURRENT_VERSION", True),
        _APP_DATE_DEP,
    ],
    "residence.travel_consistency": [_APP_DATE_DEP, _TRAVEL_DEP],
}


def _rule_version_id(key: str) -> uuid.UUID:
    return uuid.uuid5(_NS, f"rule_version:{key}")


def _dependency_id(key: str, kind: str, input_key: str | None) -> uuid.UUID:
    return uuid.uuid5(_NS, f"dependency:{key}:{kind}:{input_key or ''}")


def upgrade() -> None:
    bind = op.get_bind()
    now = datetime.now(UTC)

    rule_versions = sa.table(
        "rule_versions",
        sa.column("id", sa.Uuid),
        sa.column("requirement_id", sa.Uuid),
        sa.column("semantic_version", sa.String),
        sa.column("rule_set", sa.String),
        sa.column("evaluator_key", sa.String),
        sa.column("configuration", postgresql.JSONB),
        sa.column("effective_from", sa.DateTime),
        sa.column("lifecycle_status", sa.String),
    )
    dependencies = sa.table(
        "rule_dependency_definitions",
        sa.column("id", sa.Uuid),
        sa.column("rule_version_id", sa.Uuid),
        sa.column("input_kind", sa.String),
        sa.column("input_key", sa.String),
        sa.column("dependency_scope", sa.String),
        sa.column("required", sa.Boolean),
    )

    version_rows = []
    dependency_rows = []
    for key in _KEYS:
        requirement_id = bind.execute(
            sa.text("SELECT id FROM requirement_definitions WHERE requirement_key = :key"),
            {"key": key},
        ).scalar_one()
        version_rows.append(
            {
                "id": _rule_version_id(key),
                "requirement_id": requirement_id,
                "semantic_version": _SEMVER,
                "rule_set": _RULE_SET,
                "evaluator_key": key,
                "configuration": {"guidance": _GUIDANCE[key]},
                "effective_from": now,
                "lifecycle_status": "ACTIVE",
            }
        )
        for kind, input_key, scope, required in _DEPENDENCIES[key]:
            dependency_rows.append(
                {
                    "id": _dependency_id(key, kind, input_key),
                    "rule_version_id": _rule_version_id(key),
                    "input_kind": kind,
                    "input_key": input_key,
                    "dependency_scope": scope,
                    "required": required,
                }
            )

    op.bulk_insert(rule_versions, version_rows)
    op.bulk_insert(dependencies, dependency_rows)


def downgrade() -> None:
    version_ids = tuple(str(_rule_version_id(key)) for key in _KEYS)
    op.execute(
        sa.text("DELETE FROM rule_dependency_definitions WHERE rule_version_id IN :ids").bindparams(
            sa.bindparam("ids", value=version_ids, expanding=True)
        )
    )
    op.execute(
        sa.text("DELETE FROM rule_versions WHERE id IN :ids").bindparams(
            sa.bindparam("ids", value=version_ids, expanding=True)
        )
    )
