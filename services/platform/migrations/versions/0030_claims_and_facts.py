"""The claim→fact path: claims, review decisions, facts, versions and evidence links

`EVIDENCE_AND_CLAIM_LIFECYCLE_RFC.md` §9-§12, with the claim types and value schemas
§41 defines. Five tables, all case-scoped, all with a tenant policy.

**The constraint that carries prime directive 1** is on `fact_versions`:

    (source_method IN ('USER_CONFIRMED_AI_CLAIM','USER_CORRECTED_AI_CLAIM'))
      = (claim_review_decision_id IS NOT NULL)

An AI-derived fact cannot exist in this database without a decision row to point at,
and a user-entered one cannot pretend to have had a review. This is defence in depth,
not the primary guarantee — `app/facts/values.py` makes it a type error first — but it
is the half that survives someone reaching for the ORM directly, and the half a reviewer
can check without reading Python.

**Duplicate claims are impossible rather than merely unlikely.** `uq_extracted_claims_
run_type_journey` is `(extraction_run_id, claim_type, journey_index)`: one extraction
proposing the same field for the same journey twice is a duplicate by definition, and a
redelivered task that somehow reached this far collides here rather than doubling a
user's review queue. CLAUDE.md §9: *"a duplicate worker delivery cannot create duplicate
claims or results."*

**`journey_index` is why the key has three columns** (RFC §41.2). A booking describing
an outbound and a return leg to two destinations yields two `travel.departure_date`
claims that are about different trips, and a two-column key would reject the second.

Revision ID: 0030_claims_and_facts
Revises: 0029_refusal_statuses
Create Date: 2026-09-05
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0030_claims_and_facts"
down_revision: str | None = "0029_refusal_statuses"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

APP_ROLE = "app_rls"
_TENANT = "current_setting('app.user_id', true)"
_DML = "SELECT, INSERT, UPDATE, DELETE"

_CLAIM_STATUSES = (
    "PENDING_REVIEW",
    "CONFIRMED",
    "CORRECTED",
    "REJECTED",
    "SUPERSEDED",
    "INVALIDATED",
)
_SCHEMAS = ("date.v1", "text.v1")
_DECISIONS = ("CONFIRM", "CORRECT", "REJECT")
_REVIEW_MODES = ("BLIND_ENTRY", "PREFILLED")
_SOURCE_METHODS = (
    "USER_ENTERED",
    "USER_CONFIRMED_AI_CLAIM",
    "USER_CORRECTED_AI_CLAIM",
    "DETERMINISTIC_DERIVATION",
)
#: The two that require a human decision behind them. Mirrors `REVIEW_DERIVED` in
#: `app/facts/values.py`; `tests/facts/test_boundary.py` asserts the two agree.
_REVIEW_DERIVED = ("USER_CONFIRMED_AI_CLAIM", "USER_CORRECTED_AI_CLAIM")
_SUPPORT_TYPES = ("PRIMARY", "SUPPORTING", "CONFLICTING", "USER_ASSERTED")
_AVAILABILITY = ("AVAILABLE", "UNAVAILABLE", "DELETED")

#: Tables carrying their own `case_id`, so each policy predicates on it directly — the
#: shape `0021_evidence_travel_links` uses and `0028` corrected `extraction_runs` to.
#: Predicating through a parent would guard a different column than the queries filter on.
_DIRECT = (
    "extracted_claims",
    "claim_review_decisions",
    "case_facts",
    "fact_evidence_links",
)

#: `fact_versions` has no `case_id` and deliberately so: it hangs off `case_facts`, which
#: has one, and every query for a version goes through its fact. Denormalising the case
#: onto it would create a second column that could disagree with the first — which is the
#: defect `0028` had to correct on `extraction_runs`, in the other direction.
_GRANDCHILD = "fact_versions"

_ALL_TABLES = (*_DIRECT, _GRANDCHILD)


def _policy(table: str) -> str:
    return (
        f"EXISTS (SELECT 1 FROM cases c WHERE c.id = {table}.case_id "
        f"AND c.owner_user_id = {_TENANT})"
    )


def upgrade() -> None:
    op.create_table(
        "extracted_claims",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("case_id", sa.Uuid(), sa.ForeignKey("cases.id"), nullable=False),
        sa.Column(
            "evidence_item_id", sa.Uuid(), sa.ForeignKey("evidence_items.id"), nullable=False
        ),
        sa.Column(
            "evidence_file_id", sa.Uuid(), sa.ForeignKey("evidence_files.id"), nullable=False
        ),
        sa.Column(
            "extraction_run_id", sa.Uuid(), sa.ForeignKey("extraction_runs.id"), nullable=False
        ),
        sa.Column("claim_type", sa.String(60), nullable=False),
        sa.Column("journey_index", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("value_schema_version", sa.String(20), nullable=False),
        sa.Column("proposed_raw", sa.String(500), nullable=False),
        sa.Column("proposed_iso", sa.String(40), nullable=True),
        sa.Column("normalised_value", sa.String(200), nullable=True),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("model_confidence", sa.Float(), nullable=True),
        sa.Column("source_locator", sa.dialects.postgresql.JSONB(), nullable=True),
        sa.Column(
            "superseded_by_claim_id", sa.Uuid(), sa.ForeignKey("extracted_claims.id"), nullable=True
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.CheckConstraint(f"status IN {_CLAIM_STATUSES}", name="ck_claims_status"),
        sa.CheckConstraint(f"value_schema_version IN {_SCHEMAS}", name="ck_claims_schema"),
        sa.CheckConstraint("journey_index >= 0", name="ck_claims_journey_index"),
        sa.CheckConstraint(
            "model_confidence IS NULL OR (model_confidence >= 0 AND model_confidence <= 1)",
            name="ck_claims_confidence_range",
        ),
        sa.UniqueConstraint(
            "extraction_run_id",
            "claim_type",
            "journey_index",
            name="uq_extracted_claims_run_type_journey",
        ),
    )
    op.create_index("ix_claims_case_id", "extracted_claims", ["case_id"])
    op.create_index("ix_claims_evidence_item_id", "extracted_claims", ["evidence_item_id"])
    op.create_index("ix_claims_status", "extracted_claims", ["status"])

    op.create_table(
        "claim_review_decisions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("case_id", sa.Uuid(), sa.ForeignKey("cases.id"), nullable=False),
        sa.Column("claim_id", sa.Uuid(), sa.ForeignKey("extracted_claims.id"), nullable=False),
        sa.Column("decision", sa.String(20), nullable=False),
        sa.Column("review_mode", sa.String(20), nullable=False),
        sa.Column("corrected_raw", sa.String(500), nullable=True),
        sa.Column("corrected_normalised", sa.String(200), nullable=True),
        sa.Column("reason_code", sa.String(30), nullable=True),
        sa.Column("reviewed_by", sa.String(255), nullable=False),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("claim_revision", sa.Integer(), nullable=False, server_default="0"),
        sa.CheckConstraint(f"decision IN {_DECISIONS}", name="ck_decisions_decision"),
        sa.CheckConstraint(f"review_mode IN {_REVIEW_MODES}", name="ck_decisions_review_mode"),
        # A confirm or a correct authorises a value, so it must carry one. A reject
        # authorises nothing and must not — a rejected claim with a value sitting on its
        # decision is a fact waiting for someone to read the wrong column.
        sa.CheckConstraint(
            "(decision = 'REJECT') = (corrected_raw IS NULL)",
            name="ck_decisions_value_matches_decision",
        ),
        # A rejection says why (RFC §10). "Wrong" with no reason is unanalysable, and
        # §15 wants these outcomes as evaluation signal.
        sa.CheckConstraint(
            "(decision = 'REJECT') = (reason_code IS NOT NULL)",
            name="ck_decisions_reason_matches_decision",
        ),
    )
    op.create_index("ix_decisions_case_id", "claim_review_decisions", ["case_id"])
    op.create_index("ix_decisions_claim_id", "claim_review_decisions", ["claim_id"])

    op.create_table(
        "case_facts",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("case_id", sa.Uuid(), sa.ForeignKey("cases.id"), nullable=False),
        sa.Column("fact_type", sa.String(60), nullable=False),
        sa.Column("current_version_id", sa.Uuid(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="0"),
    )
    op.create_index("ix_case_facts_case_id", "case_facts", ["case_id"])
    op.create_index("ix_case_facts_fact_type", "case_facts", ["fact_type"])

    op.create_table(
        "fact_versions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("case_fact_id", sa.Uuid(), sa.ForeignKey("case_facts.id"), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("value_schema_version", sa.String(20), nullable=False),
        sa.Column("raw_value", sa.String(500), nullable=False),
        sa.Column("normalised_value", sa.String(200), nullable=True),
        sa.Column("source_method", sa.String(40), nullable=False),
        sa.Column(
            "claim_review_decision_id",
            sa.Uuid(),
            sa.ForeignKey("claim_review_decisions.id"),
            nullable=True,
        ),
        sa.Column(
            "supersedes_fact_version_id",
            sa.Uuid(),
            sa.ForeignKey("fact_versions.id"),
            nullable=True,
        ),
        sa.Column("created_by", sa.String(255), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.CheckConstraint(
            f"source_method IN {_SOURCE_METHODS}", name="ck_fact_versions_source"
        ),
        sa.CheckConstraint(f"value_schema_version IN {_SCHEMAS}", name="ck_fact_versions_schema"),
        # **The one that matters.** An AI-derived fact requires a decision row; anything
        # else must not carry one. Prime directive 1, in SQL — defence in depth behind
        # the type boundary in `app/facts/values.py`, and the half that survives someone
        # reaching for the ORM directly.
        sa.CheckConstraint(
            f"(source_method IN {_REVIEW_DERIVED}) = (claim_review_decision_id IS NOT NULL)",
            name="ck_fact_versions_ai_requires_decision",
        ),
        sa.CheckConstraint("version_number >= 1", name="ck_fact_versions_version_number"),
        sa.UniqueConstraint(
            "case_fact_id", "version_number", name="uq_fact_versions_fact_version"
        ),
    )
    op.create_index("ix_fact_versions_case_fact_id", "fact_versions", ["case_fact_id"])

    op.create_table(
        "fact_evidence_links",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("case_id", sa.Uuid(), sa.ForeignKey("cases.id"), nullable=False),
        sa.Column(
            "fact_version_id", sa.Uuid(), sa.ForeignKey("fact_versions.id"), nullable=False
        ),
        sa.Column(
            "evidence_item_id", sa.Uuid(), sa.ForeignKey("evidence_items.id"), nullable=False
        ),
        sa.Column(
            "evidence_file_id", sa.Uuid(), sa.ForeignKey("evidence_files.id"), nullable=False
        ),
        sa.Column("claim_id", sa.Uuid(), sa.ForeignKey("extracted_claims.id"), nullable=True),
        sa.Column("support_type", sa.String(20), nullable=False),
        sa.Column("availability_status", sa.String(20), nullable=False),
        sa.Column("withdrawn_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.CheckConstraint(f"support_type IN {_SUPPORT_TYPES}", name="ck_fact_links_support_type"),
        sa.CheckConstraint(
            f"availability_status IN {_AVAILABILITY}", name="ck_fact_links_availability"
        ),
        # A live link has not been withdrawn, and a withdrawn one says when. The pair
        # disagreeing is how a fact comes to look supported by a document that is gone.
        sa.CheckConstraint(
            "(availability_status = 'AVAILABLE') = (withdrawn_at IS NULL)",
            name="ck_fact_links_withdrawn_matches_availability",
        ),
    )
    op.create_index("ix_fact_links_case_id", "fact_evidence_links", ["case_id"])
    op.create_index("ix_fact_links_fact_version_id", "fact_evidence_links", ["fact_version_id"])
    op.create_index("ix_fact_links_evidence_item_id", "fact_evidence_links", ["evidence_item_id"])

    predicates = {table: _policy(table) for table in _DIRECT}
    predicates[_GRANDCHILD] = (
        "EXISTS (SELECT 1 FROM case_facts f JOIN cases c ON c.id = f.case_id "
        f"WHERE f.id = {_GRANDCHILD}.case_fact_id AND c.owner_user_id = {_TENANT})"
    )

    for table in _ALL_TABLES:
        op.execute(f"GRANT {_DML} ON {table} TO {APP_ROLE}")
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        predicate = predicates[table]
        op.execute(
            f"CREATE POLICY {table}_tenant ON {table} "
            f"FOR ALL USING ({predicate}) WITH CHECK ({predicate})"
        )


def downgrade() -> None:
    for table in reversed(_ALL_TABLES):
        op.execute(f"DROP POLICY IF EXISTS {table}_tenant ON {table}")
        op.execute(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")
    op.drop_table("fact_evidence_links")
    op.drop_table("fact_versions")
    op.drop_table("case_facts")
    op.drop_table("claim_review_decisions")
    op.drop_table("extracted_claims")
