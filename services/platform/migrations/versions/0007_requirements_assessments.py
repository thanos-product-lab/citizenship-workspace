"""requirements catalog and immutable assessments

Migration 3 of Domain Model §55 ("Requirements and Assessments"): the code-controlled
requirement catalog (`requirement_definitions` · `rule_versions` ·
`rule_dependency_definitions`) and the immutable assessment graph
(`assessment_runs` · `assessment_results` · `assessment_input_links`).

Two table families with deliberately different security postures:

- **Catalog tables are global reference data**, not case-scoped. They carry no
  personal data and are identical for every tenant, so they get no RLS policy; the
  app role is granted SELECT only and the rows are seeded here, at owner privilege,
  so the catalog ships with the schema (§23 "code-controlled and database-seeded").
  A new rule set is a new migration (RULES_SPEC §12), so binding catalog data to a
  revision is correct, not a smell. The app (`app/requirements/evaluation.py`) owns the
  *evaluator* logic by key and looks these rows up by key; a drift test keeps the two
  in step.
- **Assessment tables are case-scoped** and get the full 0004/0005 RLS treatment:
  ENABLE + FORCE row-level security, a per-tenant policy, and DML grants. Results
  reach the case directly (`case_id`); input links reach it through their result.

Immutability and the "at most one current trusted result per case + requirement"
invariant (Domain §30.5) are enforced structurally: results are insert-only and a
partial unique index forbids a second CURRENT row for the same case + requirement.

Only the three `route.*` rule versions are seeded now (M3B slice 1). The residence
and status rule versions land with their evaluators in later slices; their
`RequirementDefinition` catalog rows seed now so the requirement keys are stable
public identifiers from the outset.

Revision ID: 0007_requirements_assessments
Revises: 0006_residence_input_constraints
Create Date: 2026-08-11
"""

import uuid
from collections.abc import Sequence
from datetime import UTC, datetime

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0007_requirements_assessments"
down_revision: str | None = "0006_residence_input_constraints"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

APP_ROLE = "app_rls"
_TENANT = "current_setting('app.user_id', true)"
_DML = "SELECT, INSERT, UPDATE, DELETE"

_RULE_SET = "2026.07.0"
_SEMVER = "1.0.0"
_ROUTE_KEY = "SECTION_6_1_STANDARD"
# Deterministic ids so a seeded row has the same id in every environment — nicer to
# trace, and lets tests assert stable identity. The app never derives ids this way;
# it looks catalog rows up by their natural key.
_NS = uuid.UUID("6f1d2c3b-0a11-4e22-9c33-000000000007")


def _id(*parts: str) -> uuid.UUID:
    return uuid.uuid5(_NS, ":".join(parts))


# (requirement_key, group_key, title, short_description, display_order)
_DEFINITIONS: list[tuple[str, str, str, str, int]] = [
    (
        "route.adult_applicant",
        "ROUTE_AND_STATUS",
        "Adult applicant",
        "Aged 18 or over at the date of application.",
        1,
    ),
    (
        "route.supported_status",
        "ROUTE_AND_STATUS",
        "Settled status",
        "Holds ILR, indefinite leave to enter, or EU settled status.",
        2,
    ),
    (
        "route.standard_section_6_1",
        "ROUTE_AND_STATUS",
        "Standard five-year route",
        "The case fits the standard Section 6(1) five-year route.",
        3,
    ),
    (
        "status.holding_period",
        "ROUTE_AND_STATUS",
        "Settled-status holding period",
        "Free from immigration time restrictions for the 12 months before applying.",
        4,
    ),
    (
        "residence.qualifying_period",
        "RESIDENCE",
        "Qualifying period",
        "The five-year qualifying period and its key dates.",
        5,
    ),
    (
        "residence.physical_presence_start_date",
        "RESIDENCE",
        "Presence on the first day",
        "Physically present in the UK exactly five years before the application date.",
        6,
    ),
    (
        "residence.total_absences",
        "RESIDENCE",
        "Total absences",
        "No more than 450 days outside the UK across the five-year period.",
        7,
    ),
    (
        "residence.final_year_absences",
        "RESIDENCE",
        "Final-year absences",
        "No more than 90 days outside the UK in the final 12 months.",
        8,
    ),
    (
        "residence.travel_consistency",
        "RESIDENCE",
        "Travel record consistency",
        "Travel records are consistent, evidenced, and free of conflicts.",
        9,
    ),
    (
        "knowledge.life_in_uk",
        "KNOWLEDGE_AND_LANGUAGE",
        "Life in the UK test",
        "Passed the Life in the UK test.",
        10,
    ),
    (
        "knowledge.english_language",
        "KNOWLEDGE_AND_LANGUAGE",
        "English language",
        "Meets the knowledge-of-language requirement.",
        11,
    ),
    ("referees.first", "REFEREES", "First referee", "A qualifying first referee.", 12),
    ("referees.second", "REFEREES", "Second referee", "A qualifying second referee.", 13),
    (
        "character.review",
        "CHARACTER_AND_DECLARATIONS",
        "Good character",
        "Good-character declarations acknowledged.",
        14,
    ),
    (
        "preparation.case_complete",
        "PREPARATION",
        "Case readiness",
        "Overall preparation state, derived from the other requirements.",
        15,
    ),
]

# requirement_key → guidance citation carried on the seeded RuleVersion. At M3B there
# is no GuidanceSection table yet (Migration 5), so the citation is a stable source-id
# string here; ADR-0007 records that M5 adds the RuleGuidanceLink FK and backfills from
# these. Only the in-scope (route.*) rules get a seeded rule version in this slice.
_ROUTE_RULES: dict[str, list[dict[str, str]]] = {
    "route.adult_applicant": [{"source": "GUIDE_AN", "section": "Requirements — aged 18 or over"}],
    "route.supported_status": [
        {"source": "GUIDE_AN", "section": "Lawful Residence and Immigration time restrictions"}
    ],
    "route.standard_section_6_1": [
        {"source": "GUIDE_AN", "section": "Naturalisation under Section 6(1), five-year route"}
    ],
}

# rule requirement_key → (input_kind, input_key|None, dependency_scope, required). The
# composite's dependency on the adult/status *conclusions* is rule composition, not an
# input_kind (§25.1 has no result kind), so it is not a row here.
_ROUTE_DEPENDENCIES: dict[str, list[tuple[str, str | None, str, bool]]] = {
    "route.adult_applicant": [
        ("ROUTE_PROFILE", "date_of_birth", "ANY_CURRENT_VERSION", True),
        ("PROPOSED_APPLICATION_DATE", None, "ANY_CURRENT_VERSION", True),
    ],
    "route.supported_status": [
        ("ROUTE_PROFILE", "status_type", "ANY_CURRENT_VERSION", True),
    ],
    "route.standard_section_6_1": [
        ("ROUTE_PROFILE", None, "ANY_CURRENT_VERSION", True),
    ],
}


def _catalog_tables() -> tuple[sa.Table, sa.Table, sa.Table]:
    metadata = sa.MetaData()
    definitions = sa.table(
        "requirement_definitions",
        sa.column("id", sa.Uuid),
        sa.column("requirement_key", sa.String),
        sa.column("route_key", sa.String),
        sa.column("group_key", sa.String),
        sa.column("title", sa.String),
        sa.column("short_description", sa.Text),
        sa.column("evaluator_key", sa.String),
        sa.column("display_order", sa.Integer),
        sa.column("enabled", sa.Boolean),
        sa.column("introduced_at", sa.DateTime),
    )
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
    del metadata
    return definitions, rule_versions, dependencies


def _seed_catalog() -> None:
    definitions, rule_versions, dependencies = _catalog_tables()
    now = datetime.now(UTC)

    op.bulk_insert(
        definitions,
        [
            {
                "id": _id("definition", key),
                "requirement_key": key,
                "route_key": _ROUTE_KEY,
                "group_key": group,
                "title": title,
                "short_description": description,
                "evaluator_key": key,
                "display_order": order,
                "enabled": True,
                "introduced_at": now,
            }
            for key, group, title, description, order in _DEFINITIONS
        ],
    )

    op.bulk_insert(
        rule_versions,
        [
            {
                "id": _id("rule_version", key),
                "requirement_id": _id("definition", key),
                "semantic_version": _SEMVER,
                "rule_set": _RULE_SET,
                "evaluator_key": key,
                "configuration": {"guidance": guidance},
                "effective_from": now,
                "lifecycle_status": "ACTIVE",
            }
            for key, guidance in _ROUTE_RULES.items()
        ],
    )

    op.bulk_insert(
        dependencies,
        [
            {
                "id": _id("dependency", key, kind, input_key or ""),
                "rule_version_id": _id("rule_version", key),
                "input_kind": kind,
                "input_key": input_key,
                "dependency_scope": scope,
                "required": required,
            }
            for key, rows in _ROUTE_DEPENDENCIES.items()
            for kind, input_key, scope, required in rows
        ],
    )


def upgrade() -> None:
    # --- catalog (global reference data) -----------------------------------
    op.create_table(
        "requirement_definitions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("requirement_key", sa.String(length=60), nullable=False),
        sa.Column("route_key", sa.String(length=40), nullable=False),
        sa.Column("group_key", sa.String(length=40), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("short_description", sa.Text(), nullable=True),
        sa.Column("evaluator_key", sa.String(length=60), nullable=False),
        sa.Column("display_order", sa.Integer(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column(
            "introduced_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("retired_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("requirement_key", name="uq_requirement_definition_key"),
    )

    op.create_table(
        "rule_versions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "requirement_id",
            sa.Uuid(),
            sa.ForeignKey("requirement_definitions.id"),
            nullable=False,
        ),
        sa.Column("semantic_version", sa.String(length=20), nullable=False),
        sa.Column("rule_set", sa.String(length=20), nullable=False),
        sa.Column("evaluator_key", sa.String(length=60), nullable=False),
        sa.Column(
            "configuration",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("effective_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("effective_to", sa.DateTime(timezone=True), nullable=True),
        sa.Column("lifecycle_status", sa.String(length=20), nullable=False),
        sa.Column("implementation_hash", sa.String(length=64), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint(
            "requirement_id", "semantic_version", "rule_set", name="uq_rule_version_natural_key"
        ),
    )
    op.create_index("ix_rule_versions_requirement_id", "rule_versions", ["requirement_id"])

    op.create_table(
        "rule_dependency_definitions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("rule_version_id", sa.Uuid(), sa.ForeignKey("rule_versions.id"), nullable=False),
        sa.Column("input_kind", sa.String(length=40), nullable=False),
        sa.Column("input_key", sa.String(length=60), nullable=True),
        sa.Column("dependency_scope", sa.String(length=40), nullable=False),
        sa.Column("required", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.create_index(
        "ix_rule_dependency_definitions_rule_version_id",
        "rule_dependency_definitions",
        ["rule_version_id"],
    )

    # --- assessments (case-scoped) -----------------------------------------
    op.create_table(
        "assessment_runs",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("case_id", sa.Uuid(), sa.ForeignKey("cases.id"), nullable=False),
        sa.Column("trigger_type", sa.String(length=40), nullable=False),
        sa.Column("trigger_event_id", sa.Uuid(), nullable=True),
        sa.Column("mode", sa.String(length=20), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("rule_set_hash", sa.String(length=64), nullable=True),
        sa.Column("input_snapshot_hash", sa.String(length=64), nullable=True),
        sa.Column(
            "started_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("initiated_by", sa.String(length=255), nullable=False),
        sa.Column("trace_id", sa.String(length=64), nullable=True),
        sa.Column("failure_summary", sa.Text(), nullable=True),
    )
    op.create_index("ix_assessment_runs_case_id", "assessment_runs", ["case_id"])

    op.create_table(
        "assessment_results",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "assessment_run_id", sa.Uuid(), sa.ForeignKey("assessment_runs.id"), nullable=False
        ),
        sa.Column("case_id", sa.Uuid(), sa.ForeignKey("cases.id"), nullable=False),
        sa.Column(
            "requirement_id",
            sa.Uuid(),
            sa.ForeignKey("requirement_definitions.id"),
            nullable=False,
        ),
        sa.Column("rule_version_id", sa.Uuid(), sa.ForeignKey("rule_versions.id"), nullable=False),
        sa.Column("conclusion", sa.String(length=40), nullable=False),
        sa.Column("currency", sa.String(length=20), nullable=False),
        sa.Column("summary_code", sa.String(length=60), nullable=True),
        sa.Column(
            "summary_parameters",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "calculation_breakdown",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("input_snapshot_hash", sa.String(length=64), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("marked_stale_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("stale_reason_code", sa.String(length=60), nullable=True),
        sa.Column("superseded_by_result_id", sa.Uuid(), nullable=True),
    )
    op.create_index("ix_assessment_results_case_id", "assessment_results", ["case_id"])
    op.create_index("ix_assessment_results_run_id", "assessment_results", ["assessment_run_id"])
    # At most one CURRENT result per case + requirement (Domain §30.5), enforced in
    # the DB: a recalculation must supersede the prior current row before/at inserting
    # the new one, never leave two current.
    op.create_index(
        "uq_assessment_result_one_current",
        "assessment_results",
        ["case_id", "requirement_id"],
        unique=True,
        postgresql_where=sa.text("currency = 'CURRENT'"),
    )

    op.create_table(
        "assessment_input_links",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "assessment_result_id",
            sa.Uuid(),
            sa.ForeignKey("assessment_results.id"),
            nullable=False,
        ),
        sa.Column("input_kind", sa.String(length=40), nullable=False),
        sa.Column("input_version_id", sa.Uuid(), nullable=False),
        sa.Column("input_key", sa.String(length=60), nullable=True),
        sa.Column("contribution_role", sa.String(length=20), nullable=False),
        sa.Column("snapshot_value_hash", sa.String(length=64), nullable=True),
    )
    op.create_index(
        "ix_assessment_input_links_result_id",
        "assessment_input_links",
        ["assessment_result_id"],
    )

    _seed_catalog()

    # Catalog tables are global reference data: SELECT for the app role, no RLS.
    for table in ("requirement_definitions", "rule_versions", "rule_dependency_definitions"):
        op.execute(f"GRANT SELECT ON {table} TO {APP_ROLE}")

    # Assessment tables are case-scoped: full RLS (0005 pattern).
    assessment_policies = {
        "assessment_runs": (
            "EXISTS (SELECT 1 FROM cases c "
            f"WHERE c.id = assessment_runs.case_id AND c.owner_user_id = {_TENANT})"
        ),
        "assessment_results": (
            "EXISTS (SELECT 1 FROM cases c "
            f"WHERE c.id = assessment_results.case_id AND c.owner_user_id = {_TENANT})"
        ),
        "assessment_input_links": (
            "EXISTS (SELECT 1 FROM assessment_results ar JOIN cases c ON c.id = ar.case_id "
            "WHERE ar.id = assessment_input_links.assessment_result_id "
            f"AND c.owner_user_id = {_TENANT})"
        ),
    }
    for table, predicate in assessment_policies.items():
        op.execute(f"GRANT {_DML} ON {table} TO {APP_ROLE}")
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY {table}_tenant ON {table} "
            f"FOR ALL USING ({predicate}) WITH CHECK ({predicate})"
        )


def downgrade() -> None:
    for table in ("assessment_input_links", "assessment_results", "assessment_runs"):
        op.execute(f"DROP POLICY IF EXISTS {table}_tenant ON {table}")
        op.execute(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")
        op.execute(f"REVOKE {_DML} ON {table} FROM {APP_ROLE}")
    for table in ("requirement_definitions", "rule_versions", "rule_dependency_definitions"):
        op.execute(f"REVOKE SELECT ON {table} FROM {APP_ROLE}")

    op.drop_table("assessment_input_links")
    op.drop_table("assessment_results")
    op.drop_table("assessment_runs")
    op.drop_table("rule_dependency_definitions")
    op.drop_table("rule_versions")
    op.drop_table("requirement_definitions")
