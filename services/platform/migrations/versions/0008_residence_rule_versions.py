"""residence rule versions and their dependencies, plus result limitation/next-action columns

Seeds the four residence rule versions that M3B slice 2 implements —
`residence.qualifying_period`, `residence.physical_presence_start_date`,
`residence.total_absences`, `residence.final_year_absences` — with their guidance
citations (source-id strings until M5, ADR-0007) and their dependency rows per the
RULES_SPEC §8 matrix (the application date, and for the absence/presence rules every
active travel record). Their `RequirementDefinition` catalog rows already exist from 0007.

Also adds `limitations` and `next_actions` JSONB columns to `assessment_results`. These are
the structured child values a result carries (Domain §33-34) — the §6.2 sensitivity
limitation and the presence rule's resolving-date next action — stored as structured lists,
never prose. They default to an empty list so existing route results are unaffected.

The definition ids are looked up by requirement_key rather than recomputed, so this
migration does not couple to 0007's id scheme.

Revision ID: 0008_residence_rule_versions
Revises: 0007_requirements_assessments
Create Date: 2026-08-12
"""

import uuid
from collections.abc import Sequence
from datetime import UTC, datetime

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0008_residence_rule_versions"
down_revision: str | None = "0007_requirements_assessments"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_RULE_SET = "2026.07.0"
_SEMVER = "1.0.0"
_NS = uuid.UUID("6f1d2c3b-0a11-4e22-9c33-000000000008")

_RESIDENCE_KEYS = (
    "residence.qualifying_period",
    "residence.physical_presence_start_date",
    "residence.total_absences",
    "residence.final_year_absences",
)

# key → guidance citations carried on the seeded RuleVersion.
_GUIDANCE: dict[str, list[dict[str, str]]] = {
    "residence.qualifying_period": [
        {
            "source": "BNA_1981_SCH1",
            "section": "Schedule 1, para 1(2)(a) — five-year period ending with the application",
        },
        {"source": "GUIDE_AN", "section": "The qualifying period"},
    ],
    "residence.physical_presence_start_date": [
        {
            "source": "GUIDE_AN",
            "section": "Requirement to have been in the UK on the first day of the period",
        },
    ],
    "residence.total_absences": [
        {"source": "GUIDE_AN", "section": "Absences from the UK"},
        {"source": "DISCRETION", "section": "Permitted absences and the exercise of discretion"},
    ],
    "residence.final_year_absences": [
        {"source": "GUIDE_AN", "section": "Absences in the final 12 months"},
        {"source": "DISCRETION", "section": "Final-year absences and the exercise of discretion"},
    ],
}

# key → dependency rows (input_kind, input_key|None, dependency_scope, required), per the
# RULES_SPEC §8 matrix. The absence/presence rules read every active travel record; that
# set may be empty (a case with no trips is valid), so the travel dependency is not required.
_APP_DATE_DEP = ("PROPOSED_APPLICATION_DATE", None, "ANY_CURRENT_VERSION", True)
_TRAVEL_DEP = ("TRAVEL_RECORD", None, "ALL_ACTIVE_TRAVEL_RECORDS", False)
_DEPENDENCIES: dict[str, list[tuple[str, str | None, str, bool]]] = {
    "residence.qualifying_period": [_APP_DATE_DEP],
    "residence.physical_presence_start_date": [_APP_DATE_DEP, _TRAVEL_DEP],
    "residence.total_absences": [_APP_DATE_DEP, _TRAVEL_DEP],
    "residence.final_year_absences": [_APP_DATE_DEP, _TRAVEL_DEP],
}


def _rule_version_id(key: str) -> uuid.UUID:
    return uuid.uuid5(_NS, f"rule_version:{key}")


def _dependency_id(key: str, kind: str, input_key: str | None) -> uuid.UUID:
    return uuid.uuid5(_NS, f"dependency:{key}:{kind}:{input_key or ''}")


def upgrade() -> None:
    op.add_column(
        "assessment_results",
        sa.Column(
            "limitations",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )
    op.add_column(
        "assessment_results",
        sa.Column(
            "next_actions",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )

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
    for key in _RESIDENCE_KEYS:
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
    version_ids = tuple(str(_rule_version_id(key)) for key in _RESIDENCE_KEYS)
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
    op.drop_column("assessment_results", "next_actions")
    op.drop_column("assessment_results", "limitations")
